from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import media_metadata as metadata
import scan_media


def process(data: object, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["metadata-tool"], returncode, json.dumps(data), stderr)


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = self.root / "clip.mp4"
        self.media.write_bytes(b"test fixture; deliberately not a real media file")

    def inspect(self, probe: dict | None = None, *, exif: object | None = None, media: Path | None = None) -> dict:
        results = [process(probe if probe is not None else {})]
        if exif is not None:
            results.append(process(exif))
        with patch.object(metadata.subprocess, "run", side_effect=results), patch.object(metadata.shutil, "which", return_value=None):
            return metadata.inspect_media(media or self.media, "video", exiftool_executable="exiftool" if exif is not None else None)

    def test_missing_device_does_not_guess_from_filename_or_codec(self) -> None:
        source = self.root / "SONY_A7S3_SLOG3.mp4"
        source.write_bytes(b"fixture")
        result = self.inspect({"streams": [{"codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160}]}, media=source)
        self.assertEqual(result["camera"]["model"]["status"], "unknown")
        self.assertIsNone(result["camera"]["make"]["value"])
        self.assertEqual(result["color"]["input_gamma"]["status"], "unknown")

    def test_direct_device_tags_keep_field_evidence(self) -> None:
        result = self.inspect({"format": {"tags": {"com.apple.quicktime.make": "Apple", "com.apple.quicktime.model": "iPhone 16 Pro", "camera_serial_number": "BODY-001"}}})
        self.assertEqual(result["camera"]["make"]["value"], "Apple")
        self.assertEqual(result["camera"]["model"]["status"], "confirmed")
        self.assertEqual(result["camera"]["body_id"]["value"], "BODY-001")
        self.assertEqual(result["camera"]["model"]["evidence"][0]["field"], "format.tags.com.apple.quicktime.model")

    def test_conflicting_tools_do_not_choose_a_model(self) -> None:
        result = self.inspect({"format": {"tags": {"make": "Sony", "model": "ILCE-7M4"}}}, exif=[{"QuickTime:Make": "SONY Corporation", "QuickTime:Model": "ILCE-7SM3"}])
        self.assertEqual(result["camera"]["make"]["status"], "confirmed")
        self.assertEqual(result["camera"]["model"]["status"], "conflicting")
        self.assertIsNone(result["camera"]["model"]["value"])
        self.assertEqual(len(result["camera"]["model"]["evidence"]), 2)

    def test_unicode_device_names_are_preserved(self) -> None:
        result = self.inspect({"format": {"tags": {"make": "佳能", "model": "佳能 EOS R6"}}})
        self.assertEqual(result["camera"]["make"]["value"], "佳能")
        self.assertEqual(result["camera"]["model"]["status"], "confirmed")

    def test_conflicting_capture_gamma_is_not_defaulted(self) -> None:
        (self.root / "clip.xml").write_text('<Metadata><CaptureGammaEquation value="S-Log3"/></Metadata>', encoding="utf-8")
        result = self.inspect({"format": {"tags": {"capture_gamma": "Rec.709"}}})
        self.assertEqual(result["color"]["input_gamma"]["status"], "conflicting")
        self.assertIsNone(result["color"]["input_gamma"]["value"])

    def test_same_camera_model_can_have_different_capture_gamma(self) -> None:
        first = self.inspect({"format": {"tags": {"model": "Same Camera", "capture_gamma": "S-Log3"}}})
        second = self.inspect({"format": {"tags": {"model": "Same Camera", "capture_gamma": "Rec.709"}}})
        self.assertEqual(first["camera"]["model"], second["camera"]["model"])
        self.assertEqual(first["color"]["input_gamma"]["value"], "S-Log3")
        self.assertEqual(second["color"]["input_gamma"]["value"], "Rec.709")
        self.assertEqual(first["color"]["input_gamut"]["status"], "unknown")

    def test_encoding_primaries_and_transfer_do_not_confirm_capture_profile(self) -> None:
        result = self.inspect({"streams": [{"index": 0, "codec_type": "video", "color_primaries": "bt709", "color_transfer": "bt709", "color_range": "tv", "pix_fmt": "yuv420p10le"}]}, exif=[{"EXIF:ColorSpace": "sRGB", "QuickTime:Gamma": 2.2}])
        self.assertEqual(result["color"]["encoded"]["streams"][0]["color_transfer"], "bt709")
        self.assertEqual(result["color"]["input_gamut"]["status"], "unknown")
        self.assertEqual(result["color"]["input_gamma"]["status"], "candidate")

    def test_same_name_sidecar_with_wrong_explicit_reference_is_rejected(self) -> None:
        (self.root / "clip.xml").write_text("<Metadata><FileName>different.mp4</FileName><Camera><Model>Wrong Camera</Model></Camera></Metadata>", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["camera"]["model"]["status"], "unknown")
        self.assertEqual(result["camera"]["coverage"]["sidecars"][0]["status"], "rejected")

    def test_different_name_sidecar_requires_explicit_matching_clip(self) -> None:
        (self.root / "recording_metadata.xml").write_text('<Metadata><FileName>clip.mp4</FileName><Device manufacturer="Sony" modelName="ILCE-7M4"/><CaptureGammaEquation value="S-Log3"/><CaptureColorPrimaries value="S-Gamut3.Cine"/></Metadata>', encoding="utf-8")
        (self.root / "unrelated.xml").write_text("<Metadata><Camera><Model>Unrelated Camera</Model></Camera></Metadata>", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["camera"]["model"]["value"], "ILCE-7M4")
        self.assertEqual(result["color"]["input_gamma"]["value"], "S-Log3")
        self.assertEqual(result["color"]["input_gamma"]["status"], "confirmed")
        self.assertEqual(result["color"]["input_gamut"]["value"], "S-Gamut3.Cine")

    def test_same_stem_sidecar_is_ambiguous_when_two_media_extensions_exist(self) -> None:
        (self.root / "clip.mov").write_bytes(b"other source")
        (self.root / "clip.xml").write_text("<Camera><Model>Ambiguous Camera</Model></Camera>", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["camera"]["model"]["status"], "unknown")
        self.assertEqual(result["camera"]["coverage"]["sidecars"][0]["status"], "rejected")

    def test_same_stem_sidecar_is_ambiguous_across_supported_media_types(self) -> None:
        (self.root / "clip.xml").write_text("<Camera><Model>Ambiguous Camera</Model></Camera>", encoding="utf-8")
        for suffix in (".webp", ".bmp", ".flac", ".ogg", ".opus", ".aiff", ".wma"):
            with self.subTest(suffix=suffix):
                sibling = self.root / f"clip{suffix}"
                sibling.write_bytes(b"different media type")
                try:
                    self.assertIn(sibling.resolve(), scan_media.collect([sibling]))
                    result = self.inspect()
                    self.assertEqual(result["camera"]["model"]["status"], "unknown")
                    self.assertEqual(result["camera"]["coverage"]["sidecars"][0]["status"], "rejected")
                finally:
                    sibling.unlink()

    def test_sourcefile_reference_to_other_image_or_audio_rejects_same_name_sidecar(self) -> None:
        sidecar = self.root / "clip.xml"
        for suffix in (".webp", ".flac", ".WEBP", ".FLAC"):
            with self.subTest(suffix=suffix):
                sidecar.write_text(f"<Metadata><SourceFile>different{suffix}</SourceFile><Camera><Model>Wrong Camera</Model></Camera></Metadata>", encoding="utf-8")
                result = self.inspect()
                self.assertEqual(result["camera"]["model"]["status"], "unknown")
                self.assertEqual(result["camera"]["coverage"]["sidecars"][0]["status"], "rejected")

    def test_same_name_sidecar_with_multiple_clip_references_is_rejected(self) -> None:
        (self.root / "clip.xml").write_text("<Metadata><FileName>clip.mp4</FileName><FileName>other.mp4</FileName><Camera><Model>Wrong</Model></Camera></Metadata>", encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["camera"]["model"]["status"], "unknown")

    def test_lens_identity_is_not_camera_identity(self) -> None:
        (self.root / "clip.xml").write_text('<Metadata><Lens><Model>Lens model</Model><SerialNumber>LENS001</SerialNumber></Lens></Metadata>', encoding="utf-8")
        result = self.inspect(exif=[{"EXIF:LensModel": "Other lens", "EXIF:LensSerialNumber": "LENS002"}])
        self.assertEqual(result["camera"]["model"]["status"], "unknown")
        self.assertEqual(result["camera"]["body_id"]["status"], "unknown")

    def test_dtd_entity_sidecar_is_not_processed(self) -> None:
        (self.root / "clip.xml").write_text('<!DOCTYPE Camera [<!ENTITY camera "Injected">]><Camera><Model>&camera;</Model></Camera>', encoding="utf-8")
        result = self.inspect()
        self.assertEqual(result["camera"]["model"]["status"], "unknown")
        self.assertIn("DTD/entity", result["camera"]["coverage"]["errors"][0]["error"])

    def test_exiftool_missing_is_partial_coverage_not_missing_metadata_claim(self) -> None:
        result = self.inspect({"format": {"tags": {"model": "Documented Camera"}}})
        self.assertEqual(result["camera"]["model"]["status"], "confirmed")
        self.assertEqual(result["camera"]["coverage"]["level"], "partial")
        self.assertEqual(result["camera"]["coverage"]["tools"]["exiftool"]["status"], "unavailable")

    def test_exiftool_warning_retains_metadata_but_marks_partial_coverage(self) -> None:
        result = self.inspect(exif=[{"EXIF:Model": "Documented Camera", "ExifTool:Warning": "Truncated metadata"}])
        self.assertEqual(result["camera"]["model"]["value"], "Documented Camera")
        self.assertEqual(result["camera"]["coverage"]["level"], "partial")
        self.assertIn("Truncated metadata", result["camera"]["coverage"]["tools"]["exiftool"]["warnings"])

    def test_ffprobe_errors_timeouts_missing_binary_and_bad_json_are_retained(self) -> None:
        cases = [
            (process({}, 1, "unsupported file"), "error"),
            (subprocess.TimeoutExpired("ffprobe", 20), "timeout"),
            (FileNotFoundError("ffprobe"), "unavailable"),
            (subprocess.CompletedProcess([], 0, "not json", ""), "parse_error"),
            (process([]), "parse_error"),
            (process({"streams": None}), "parse_error"),
        ]
        for response, status in cases:
            with self.subTest(status=status, response=type(response).__name__), patch.object(metadata.subprocess, "run", side_effect=[response]), patch.object(metadata.shutil, "which", return_value=None):
                result = metadata.inspect_media(self.media, "video")
            self.assertIn("error", result["probe"])
            self.assertEqual(result["camera"]["coverage"]["tools"]["ffprobe"]["status"], status)
            self.assertEqual(result["camera"]["model"]["status"], "unknown")

    def test_raw_clip_requires_resolve_backfill_on_probe_failure(self) -> None:
        source = self.root / "clip.braw"
        source.write_bytes(b"raw fixture")
        with patch.object(metadata.subprocess, "run", return_value=process({}, 1, "unsupported")):
            result = metadata.inspect_media(source, "video", exiftool_executable="")
        self.assertTrue(result["camera"]["coverage"]["resolve_backfill_recommended"])
        self.assertIn(source.resolve(), scan_media.collect([source]))

    def test_scanner_preserves_manifest_array_and_failed_media_row(self) -> None:
        output = self.root / "scan"
        before = self.media.read_bytes()
        argv = ["scan_media.py", "--input", str(self.media), "--output", str(output), "--no-exiftool"]
        with patch.object(sys, "argv", argv), patch.object(metadata.subprocess, "run", return_value=process({}, 1, "not supported")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scan_media.main(), 0)
        rows = json.loads((output / "media-manifest.json").read_text(encoding="utf-8"))
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], str(self.media.resolve()))
        self.assertTrue({"media_type", "extension", "size_bytes", "quick_hash", "probe", "camera", "color"}.issubset(rows[0]))
        self.assertEqual(rows[0]["probe"]["error"], "not supported")
        self.assertEqual(self.media.read_bytes(), before)
        expected_hash = hashlib.sha256((output / "media-manifest.json").read_bytes()).hexdigest()
        self.assertEqual((output / "media-manifest.sha256").read_bytes(), (expected_hash + "\n").encode("ascii"))
        summary = json.loads((output / "scan-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["metadata_manifest"], {
            "path": str((output / "media-manifest.json").resolve()),
            "sha256": expected_hash,
        })


if __name__ == "__main__":
    unittest.main()
