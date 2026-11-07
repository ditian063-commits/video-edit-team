from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from color_plan import validate_color_plan


def validate_delivery(payload: dict, *, require=False) -> dict:
    """Check export declarations without creating directories or render jobs."""
    delivery = payload.get("delivery")
    errors: list[str] = []
    report = {
        "present": delivery is not None, "valid": False, "errors": errors,
        "verification": "spec_only_not_render_verification",
    }
    if delivery is None:
        if require:
            errors.append("delivery is required")
        return report
    if not isinstance(delivery, dict):
        errors.append("delivery must be an object")
        return report

    output = delivery.get("output_path")
    if not isinstance(output, str) or not output.strip():
        errors.append("delivery.output_path must be an absolute path to a new file")
    else:
        try:
            path = Path(output)
            if not path.is_absolute():
                errors.append("delivery.output_path must be absolute")
            elif path.exists() or path.is_symlink():
                errors.append("delivery.output_path already exists; choose a new versioned file")
            resolved = path.resolve()
            clips = payload.get("clips", [])
            for clip in clips if isinstance(clips, list) else []:
                source = clip.get("source_path") if isinstance(clip, dict) else None
                if isinstance(source, str) and source.strip() and resolved == Path(source).resolve():
                    errors.append("delivery.output_path must not refer to a source file")
                    break
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"delivery.output_path is invalid: {exc}")
    for field in ("container", "video_codec", "audio_codec"):
        value = delivery.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"delivery.{field} must be a nonempty string")
    for field in ("width", "height"):
        value = delivery.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"delivery.{field} must be a positive integer")

    def finite_number(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

    fps = delivery.get("fps")
    if not finite_number(fps) or fps <= 0:
        errors.append("delivery.fps must be a finite positive number")
    span = delivery.get("range")
    if not isinstance(span, dict):
        errors.append("delivery.range requires start_seconds and end_seconds")
    else:
        start, end = span.get("start_seconds"), span.get("end_seconds")
        if not finite_number(start) or not finite_number(end):
            errors.append("delivery.range boundaries must be finite numbers")
        elif start < 0 or end <= start:
            errors.append("delivery.range requires 0 <= start_seconds < end_seconds")
    if delivery.get("subtitle_mode") not in ("burn_in", "sidecar", "none"):
        errors.append("delivery.subtitle_mode must be burn_in, sidecar or none")

    space = delivery.get("color_space")
    color_plan = payload.get("color_plan")
    target = color_plan.get("output_space") if isinstance(color_plan, dict) else None
    if not isinstance(space, dict) or not all(isinstance(space.get(k), str) and space[k].strip() for k in ("gamut", "gamma")):
        errors.append("delivery.color_space requires nonempty gamut and gamma")
    elif not isinstance(target, dict) or not all(isinstance(target.get(k), str) and target[k].strip() for k in ("gamut", "gamma")):
        errors.append("delivery.color_space requires color_plan.output_space for comparison")
    elif any(space[k].strip().casefold() != target[k].strip().casefold() for k in ("gamut", "gamma")):
        errors.append("delivery.color_space must match color_plan.output_space")
    report["valid"] = not errors
    return report


def validate_blueprint(payload: dict, *, require_color_plan=False, require_color_ready=False, require_delivery=False) -> dict:
    clips = payload.get("clips", [])
    errors: list[str] = []
    warnings: list[str] = []
    groups: Counter[str] = Counter()
    tracks: dict[tuple[str, int], list[tuple[float, float, str, str]]] = {}
    if not isinstance(clips, list):
        errors.append("clips must be an array")
        clips = []

    for index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            errors.append(f"clip-{index}: clip must be an object")
            continue
        label = str(clip.get("id", f"clip-{index}"))
        source = Path(str(clip.get("source_path", "")))
        try:
            source_in, source_out, timeline_in, timeline_out = (
                float(clip.get(key, 0)) for key in
                ("source_in_seconds", "source_out_seconds", "timeline_in_seconds", "timeline_out_seconds")
            )
            if not all(math.isfinite(x) for x in (source_in, source_out, timeline_in, timeline_out)):
                raise ValueError("non-finite time")
            track_type = "audio" if clip.get("media_type") == "audio" else "video"
            track_index = int(clip.get(f"{track_type}_track", 1))
            if track_index < 1:
                raise ValueError("track index must be positive")
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(f"{label}: invalid timing/track value: {exc}")
            continue
        if not source.is_file():
            errors.append(f"{label}: missing source file {source}")
        if source_in < 0 or timeline_in < 0:
            errors.append(f"{label}: negative source/timeline start")
        if source_out <= source_in:
            errors.append(f"{label}: non-positive source duration")
        if timeline_out <= timeline_in:
            errors.append(f"{label}: non-positive timeline duration")
        if abs((source_out - source_in) - (timeline_out - timeline_in)) > 0.05 and not clip.get("speed"):
            warnings.append(f"{label}: source/timeline duration mismatch without speed declaration")
        tracks.setdefault((track_type, track_index), []).append((timeline_in, timeline_out, str(source), label))
        groups[str(clip.get("source_group", "unclassified"))] += timeline_out - timeline_in
    # Overlapping sound and picture, or different video layers, are separate tracks.
    for track, items in tracks.items():
        previous = None
        for item in sorted(items):
            if previous is not None:
                delta = item[0] - previous[1]
                if delta > 0.001:
                    warnings.append(f"{item[3]}: {track} timeline gap {delta:.3f}s")
                elif delta < -0.001:
                    errors.append(f"{item[3]}: {track} timeline overlap {-delta:.3f}s")
                if item[2] == previous[2]:
                    warnings.append(f"{item[3]}: adjacent reuse of source {Path(item[2]).name}")
            previous = item
    color = validate_color_plan(payload, require=require_color_plan, require_ready=require_color_ready)
    errors.extend(color["errors"])
    warnings.extend(color["warnings"])
    delivery = validate_delivery(payload, require=require_delivery)
    errors.extend(delivery["errors"])
    return {
        "clip_count": len(clips),
        "errors": errors,
        "warnings": warnings,
        "duration_by_source_group_seconds": dict(groups),
        "color_plan": color,
        "delivery": delivery,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a blueprint; this does not execute or verify Resolve writes.")
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--require-color-plan", action="store_true", help="Reject legacy blueprints without a color plan.")
    parser.add_argument("--require-color-ready", action="store_true", help="Require a valid color plan with no blocked visual clips.")
    parser.add_argument("--require-delivery", action="store_true", help="Require explicit export settings and a new output file path.")
    args = parser.parse_args()
    try:
        payload = json.loads(args.blueprint.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("blueprint must be an object")
        report = validate_blueprint(payload, require_color_plan=args.require_color_plan,
                                    require_color_ready=args.require_color_ready, require_delivery=args.require_delivery)
    except (OSError, ValueError) as exc:
        report = {"errors": [str(exc)], "warnings": []}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
