"""Summarize a specific blueprint revision without executing or approving it."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


STAGES = ("confirm", "resolve", "dsh-plan", "dsh-delivery")
AUDIO_FIELDS = (
    "id", "clip_id", "name", "placement", "source_path", "origin_path",
    "source_in_seconds", "source_out_seconds", "origin_source_in_seconds",
    "origin_source_out_seconds", "timeline_in_seconds", "timeline_out_seconds",
    "audio_track", "gain_db", "fade_in_seconds", "fade_out_seconds",
    "processing_baked",
)


def select(record: dict, fields: tuple[str, ...]) -> dict:
    return {field: record[field] for field in fields if field in record}


def object_field(record: dict, key: str, *, required: bool = False) -> dict:
    if key not in record and not required:
        return {}
    value = record.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def array_field(record: dict, key: str, *, required: bool = False) -> list:
    if key not in record and not required:
        return []
    value = record.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be an array")
    return value


def count_labels(rows: list, field: str) -> dict:
    counts = Counter()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"entries summarized by {field} must be objects")
        label = row.get(field, "unspecified")
        if not isinstance(label, str) or not label:
            raise ValueError(f"{field} must be a nonempty string when present")
        counts[label] += 1
    return dict(sorted(counts.items()))


def file_identity(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"evidence must be a regular file: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_ino != after.st_ino or before.st_dev != after.st_dev
            or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns):
        raise ValueError(f"evidence changed during hashing: {path}")
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": after.st_size}


def render_paths(delivery: dict) -> list[Path]:
    paths = []
    for field in ("output_path", "final_delivery_path"):
        if field in delivery:
            value = delivery[field]
            if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
                raise ValueError(f"delivery.{field} must be an absolute file path")
            paths.append(Path(value).resolve())
    return paths


def summarize_audio(plan: dict, clips: list) -> dict:
    audio = object_field(plan, "audio_plan")
    music = array_field(plan, "music")
    if any(not isinstance(entry, (dict, str)) for entry in music):
        raise ValueError("music entries must be objects or strings")
    result = select(audio, (
        "origin_path", "origin_source_in_seconds", "origin_source_out_seconds",
        "gain_db_on_prepared_wav", "source_video_audio", "additional_processing",
        "auditory_review",
    ))
    if "processing_already_baked" in audio:
        baked = audio["processing_already_baked"]
        if isinstance(baked, dict):
            baked = select(baked, ("constant_gain_db", "fade_in", "fade_out", "loop", "time_stretch"))
        result["processing_already_baked"] = baked
    result["tracks"] = [select(clip, AUDIO_FIELDS) for clip in clips if clip.get("media_type") == "audio"]
    result["music"] = [select(entry, AUDIO_FIELDS) if isinstance(entry, dict) else entry for entry in music]
    result["narration_count"] = len(array_field(plan, "narration"))
    return result


def make_handoff(blueprint: Path, stage: str, evidence: list[Path]) -> dict:
    blueprint = blueprint.resolve()
    if not blueprint.is_file():
        raise ValueError(f"blueprint must be a regular file: {blueprint}")
    data = blueprint.read_bytes()
    plan = json.loads(data.decode("utf-8-sig"))
    if not isinstance(plan, dict):
        raise ValueError("blueprint must be an object")

    project = object_field(plan, "project", required=True)
    delivery = object_field(plan, "delivery")
    clips = array_field(plan, "clips", required=True)
    color = object_field(plan, "color_plan")
    declared_renders = render_paths(delivery)
    paths = list(dict.fromkeys(path.resolve() for path in evidence))
    matching_renders = [path for path in declared_renders if path in paths]
    if stage == "dsh-delivery" and not matching_renders:
        raise ValueError("dsh-delivery requires --evidence for the declared render or final delivery path")

    report = {
        "stage": stage,
        "verification": "handoff_only",
        "blueprint": {
            "path": str(blueprint), "sha256": hashlib.sha256(data).hexdigest(),
            **select(plan, ("schema_version", "run_id", "version")),
        },
        "project": project,
        "clip_counts": count_labels(clips, "media_type"),
        "audio": summarize_audio(plan, clips),
        "captions": {"count": len(array_field(plan, "captions")), **select(delivery, ("subtitle_mode",))},
    }
    for field in ("timeline", "tracks", "delivery", "scope"):
        if field in plan:
            report[field] = object_field(plan, field)
    if "unverified" in plan:
        report["unverified"] = array_field(plan, "unverified")
    if "color_plan" in plan:
        report["color"] = select(color, (
            "working_space", "output_space", "metadata_manifest", "bypass_by_user",
            "color_status", "assembly_blocked_by_color", "render_blocked_by_color",
        ))
        report["color"]["action_counts"] = count_labels(array_field(color, "clips"), "action")

    identities = {path: file_identity(path) for path in paths}
    report["evidence"] = list(identities.values())
    if stage == "dsh-delivery":
        renders = [identities[path] for path in matching_renders]
        if len({item["sha256"] for item in renders}) > 1:
            raise ValueError("declared render and final delivery evidence have different hashes")
        report["render"] = renders[0]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--evidence", action="append", default=[], type=Path,
                        help="Reference a local evidence file by resolved path and SHA-256; repeat for each file.")
    args = parser.parse_args()
    try:
        report = make_handoff(args.blueprint, args.stage, args.evidence)
        data = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
        sys.stdout.buffer.write((data + "\n").encode("utf-8"))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"handoff: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
