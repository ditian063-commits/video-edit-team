from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import deque
from pathlib import Path


TIME_BASE = re.compile(r"config in time_base:\s*(\d+)/(\d+)")
FRAME = re.compile(r"\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:")
DURATION = re.compile(r"\bduration:\s*(\d+)\s+duration_time:")
MEAN_LUMA = re.compile(r"\bmean:\[\s*(\d+)\b")
THRESHOLDS = {"near_black_max": 16, "near_white_min": 239, "brightness_jump_min": 70}
TIMESTAMP_EPSILON = 0.000001


def screen_window(ffmpeg: str, source: Path, start: float, end: float, limit: int) -> dict:
    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "info", "-xerror",
        "-copyts", "-start_at_zero", "-ss", f"{start:.6f}", "-protocol_whitelist", "file",
        "-i", str(source), "-map", "0:V:0", "-an", "-sn", "-dn",
        "-vf", "scale=160:90:flags=area:out_range=full,format=yuv420p,showinfo",
        "-t", f"{end:.6f}", "-fps_mode", "passthrough", "-f", "null", "-",
    ]
    time_base = first_time = last_time = previous_luma = None
    first_duration = last_duration = 0.0
    frames = candidate_count = 0
    saw_end = malformed_stats = False
    candidates = []
    diagnostics = deque(maxlen=8)
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace") as process:
        assert process.stderr is not None
        for line in process.stderr:
            if "Parsed_showinfo_" not in line:
                diagnostics.append(line.strip())
                continue
            config = TIME_BASE.search(line)
            if config:
                numerator, denominator = map(int, config.groups())
                time_base = numerator / denominator if numerator and denominator else None
                continue
            if "pts_time:" not in line:
                continue
            frame, mean = FRAME.search(line), MEAN_LUMA.search(line)
            if not (frame and mean and time_base):
                malformed_stats = True
                continue
            timestamp = int(frame[1]) * time_base
            if timestamp < start - TIMESTAMP_EPSILON:
                continue
            if timestamp >= end - TIMESTAMP_EPSILON:
                saw_end = True
                continue

            duration = DURATION.search(line)
            last_duration = int(duration[1]) * time_base if duration else 0.0
            if first_time is None:
                first_time, first_duration = timestamp, last_duration
            if last_time is not None and timestamp < last_time:
                malformed_stats = True
            last_time = timestamp
            luma = int(mean[1])
            reasons = []
            if luma <= THRESHOLDS["near_black_max"]:
                reasons.append("near_black")
            if luma >= THRESHOLDS["near_white_min"]:
                reasons.append("near_white")
            if previous_luma is not None and abs(luma - previous_luma) >= THRESHOLDS["brightness_jump_min"]:
                reasons.append("brightness_jump")
            if reasons:
                candidate_count += 1
                if len(candidates) < limit:
                    candidates.append({"source_seconds": timestamp, "frame_index_in_window": frames,
                                       "mean_luma_8bit": luma, "reasons": reasons})
            previous_luma = luma
            frames += 1
        returncode = process.wait()

    errors = []
    if returncode:
        details = "\n".join(line for line in diagnostics if line)
        errors.append(f"FFmpeg exited {returncode}" + (f":\n{details}" if details else ""))
    if malformed_stats:
        errors.append("FFmpeg did not provide usable frame luminance and ordered timestamps")
    end_evidence = None
    if first_time is None or last_time is None:
        errors.append("No video frame timestamp in the requested source window")
    else:
        if first_duration and first_time - start > first_duration + TIMESTAMP_EPSILON:
            errors.append("Decoded frames begin more than one frame duration after the requested start")
        if saw_end:
            end_evidence = "following_timestamp"
        elif last_time + last_duration >= end - TIMESTAMP_EPSILON:
            end_evidence = "last_frame_duration"
        else:
            errors.append("Could not establish coverage through the requested end from decoded timestamps")

    return {
        "status": "incomplete" if errors else "screened", "errors": errors,
        "frames_read": frames, "first_frame_seconds": first_time, "last_frame_seconds": last_time,
        "end_evidence": end_evidence, "candidate_count": candidate_count,
        "candidates_truncated": candidate_count > len(candidates), "candidates": candidates,
    }


def screen_blueprint(blueprint: Path, ffmpeg: str, limit: int) -> dict:
    raw = blueprint.read_bytes()
    plan = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(plan, dict) or not isinstance(plan.get("clips"), list):
        raise ValueError("blueprint must contain a clips array")
    windows = []
    skipped = 0
    for index, clip in enumerate(plan["clips"], start=1):
        window = {"clip_id": f"clip-{index}"}
        try:
            if not isinstance(clip, dict):
                raise ValueError("clip must be an object")
            window["clip_id"] = clip.get("id") or clip.get("clip_id") or window["clip_id"]
            if clip.get("media_type") in ("audio", "image", "still"):
                skipped += 1
                continue
            if clip.get("media_type", "video") != "video":
                raise ValueError("unsupported clip media_type")
            source = Path(clip["source_path"])
            window["source_path"] = str(source)
            if not source.is_absolute() or not source.is_file():
                raise ValueError("source_path must identify an existing absolute local file")
            start, end = clip["source_in_seconds"], clip["source_out_seconds"]
            if not all(type(value) in (int, float) and math.isfinite(value) for value in (start, end)):
                raise ValueError("source time boundaries must be finite numbers")
            if not 0 <= start < end:
                raise ValueError("source boundaries must satisfy 0 <= source_in_seconds < source_out_seconds")
            window.update(source_in_seconds=start, source_out_seconds=end)
            window.update(screen_window(ffmpeg, source, start, end, limit))
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            window.update(status="incomplete", errors=[str(exc)])
        windows.append(window)

    return {
        "scope": "selected_source_luminance_screen",
        "blueprint": {"path": str(blueprint.resolve()), "sha256": hashlib.sha256(raw).hexdigest()},
        "measurement": "Mean 8-bit luma at 160x90 with decoded source timestamps and no frame sampling",
        "thresholds": THRESHOLDS, "max_candidates_per_window": limit,
        "skipped_non_video_clips": skipped, "windows": windows,
        "complete": all(window["status"] == "screened" for window in windows),
        "limitations": [
            "Candidates require visual review. Highlights, cuts and fades can trigger them.",
            "Review selected heads, tails and internal transitions for focus and edit artifacts.",
            "Source timestamps and luminance do not verify a Resolve render, audio or output color.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen selected local source windows for luminance anomalies.")
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable path (requires -fps_mode)")
    parser.add_argument("--max-candidates-per-window", type=int, default=50,
                        help="Maximum listed candidates per window; all detections are counted")
    args = parser.parse_args()
    if args.max_candidates_per_window < 1:
        parser.error("--max-candidates-per-window must be positive")
    try:
        report = screen_blueprint(args.blueprint, args.ffmpeg, args.max_candidates_per_window)
    except (OSError, ValueError) as exc:
        report = {"scope": "selected_source_luminance_screen", "complete": False, "errors": [str(exc)]}
    print(json.dumps(report, indent=2))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
