from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from media_metadata import AUDIO, IMAGE, VIDEO, MEDIA_SUFFIXES, inspect_media, probe_file


def probe(path: Path) -> dict:
    """Compatibility entrypoint; full metadata and failures are preserved."""
    return probe_file(path)[0]


def quick_hash(path: Path) -> str:
    digest = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as handle:
        digest.update(handle.read(1024 * 1024))
        if size > 1024 * 1024:
            handle.seek(max(0, size - 1024 * 1024))
            digest.update(handle.read(1024 * 1024))
    digest.update(str(size).encode("ascii"))
    return digest.hexdigest()


def collect(inputs: list[Path]) -> list[Path]:
    found: set[Path] = set()
    allowed = MEDIA_SUFFIXES
    for item in inputs:
        if item.is_file() and item.suffix.lower() in allowed:
            found.add(item.resolve())
        elif item.is_dir():
            found.update(p.resolve() for p in item.rglob("*") if p.is_file() and p.suffix.lower() in allowed)
    return sorted(found, key=lambda p: str(p).lower())


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan arbitrary video, audio, and image paths.")
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ffprobe", default="ffprobe", help="FFprobe executable or absolute path")
    exif_options = parser.add_mutually_exclusive_group()
    exif_options.add_argument("--exiftool", help="Optional ExifTool executable; otherwise auto-detect on PATH")
    exif_options.add_argument("--no-exiftool", action="store_true", help="Skip optional ExifTool extraction")
    parser.add_argument("--metadata-timeout", type=float, default=20, help="Per-tool timeout in seconds")
    args = parser.parse_args()
    if args.metadata_timeout <= 0:
        parser.error("--metadata-timeout must be positive")
    args.output.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in collect(args.input):
        suffix = path.suffix.lower()
        media_type = "video" if suffix in VIDEO else "audio" if suffix in AUDIO else "image"
        metadata = inspect_media(path, media_type, ffprobe_executable=args.ffprobe,
                                 exiftool_executable="" if args.no_exiftool else args.exiftool,
                                 timeout=args.metadata_timeout)
        row = {
            "path": str(path),
            "media_type": media_type,
            "extension": suffix,
            "size_bytes": None,
            "quick_hash": "",
            **metadata,
        }
        try:
            row["size_bytes"] = path.stat().st_size
            row["quick_hash"] = quick_hash(path)
        except OSError as exc:
            row["scan_error"] = str(exc)
        rows.append(row)

    manifest = args.output / "media-manifest.json"
    manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (args.output / "media-manifest.sha256").write_bytes((manifest_sha256 + "\n").encode("ascii"))
    counts = Counter(row["media_type"] for row in rows)
    summary = {
        "inputs": [str(p.resolve()) for p in args.input],
        "file_count": len(rows),
        "counts": dict(counts),
        "metadata_manifest": {"path": str(manifest.resolve()), "sha256": manifest_sha256},
    }
    (args.output / "scan-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
