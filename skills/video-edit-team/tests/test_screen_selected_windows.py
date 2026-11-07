import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FFMPEG = shutil.which("ffmpeg")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "screen_selected_windows.py"


@unittest.skipUnless(FFMPEG, "ffmpeg is required for the source window smoke test")
class SelectedWindowTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name).resolve()
        self.blueprint = root / "edit.json"
        self.source = root / "two flash frames.mkv"
        plane = 64 * 64
        frames = b"".join(
            bytes([235 if index in (13, 14) else 100]) * plane + bytes([128]) * (plane // 2)
            for index in range(40)
        )
        subprocess.run([
            FFMPEG, "-v", "error", "-f", "rawvideo", "-pixel_format", "yuv420p",
            "-video_size", "64x64", "-framerate", "25", "-i", "-", "-c:v", "ffv1", str(self.source),
        ], input=frames, check=True)

    def screen(self, start, end, limit=50):
        self.blueprint.write_text(json.dumps({"clips": [
            {"clip_id": "picture", "media_type": "video", "source_path": str(self.source),
             "source_in_seconds": start, "source_out_seconds": end},
            {"id": "sound", "media_type": "audio"},
        ]}), encoding="utf-8")
        process = subprocess.run([
            sys.executable, str(SCRIPT), str(self.blueprint), "--ffmpeg", FFMPEG,
            "--max-candidates-per-window", str(limit),
        ], capture_output=True)
        return process.returncode, json.loads(process.stdout)

    def test_nonzero_start_preserves_cadence_and_excludes_end_frame(self):
        code, report = self.screen(0.4, 0.8, limit=2)
        self.assertEqual(code, 0)
        self.assertEqual(report["skipped_non_video_clips"], 1)
        window = report["windows"][0]
        self.assertEqual(window["clip_id"], "picture")
        self.assertEqual(window["frames_read"], 10)
        self.assertAlmostEqual(window["first_frame_seconds"], 0.4)
        self.assertAlmostEqual(window["last_frame_seconds"], 0.76)
        self.assertEqual(window["candidate_count"], 3)
        self.assertTrue(window["candidates_truncated"])
        for candidate, timestamp in zip(window["candidates"], (0.52, 0.56)):
            self.assertAlmostEqual(candidate["source_seconds"], timestamp)
            self.assertIn("near_white", candidate["reasons"])

    def test_source_ending_before_requested_end_is_incomplete(self):
        code, report = self.screen(0.4, 1.8)
        self.assertEqual(code, 1)
        self.assertFalse(report["complete"])
        self.assertEqual(report["windows"][0]["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
