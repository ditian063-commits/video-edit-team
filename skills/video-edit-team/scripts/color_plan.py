"""Validate declared color operations without touching Resolve."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

STATUSES = {"confirmed", "candidate", "unknown", "conflicting"}
METHODS = {"rcm", "cst", "lut"}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _space(value):
    return isinstance(value, dict) and all(_text(value.get(k)) for k in ("gamut", "gamma"))


def _same_space(left, right):
    return all(str(left.get(k, "")).strip().casefold() == str(right.get(k, "")).strip().casefold()
               for k in ("gamut", "gamma"))


def _evidence(value):
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, dict) and _text(item.get("source")) and _text(item.get("field"))
        and "value" in item and item["value"] is not None and item["value"] != ""
        for item in value
    )


def validate_color_plan(payload: dict, *, require=False, require_ready=False) -> dict:
    """A valid blocked entry must not execute; readiness never proves rendering.

    Invalid plans expose no ready entries. A valid mixed plan can execute only
    its ready entries. require_ready rejects even a structurally valid blocked
    plan and is intended for the final all-clips preflight.
    """
    errors, warnings, ready, blocked, invalid = [], [], [], [], []
    blocked_reasons = {}
    plan = payload.get("color_plan")
    result = {
        "present": plan is not None, "plan_valid": False, "all_clips_ready": False,
        "ready_clip_ids": ready, "blocked_clip_ids": blocked, "invalid_clip_ids": invalid,
        "blocked_reasons": blocked_reasons, "errors": errors, "warnings": warnings,
        "verification": "plan_only_not_render_verification",
    }
    if plan is None:
        if require or require_ready:
            errors.append("color_plan is required")
        else:
            warnings.append("No color_plan: legacy assembly only; color readiness was not checked")
        return result
    if not isinstance(plan, dict):
        errors.append("color_plan must be an object")
        return result
    if plan.get("version") != "1.0":
        errors.append("color_plan.version must be '1.0'")
    for key in ("working_space", "output_space"):
        if not _space(plan.get(key)):
            errors.append(f"color_plan.{key} requires nonempty gamut and gamma")
    working = plan.get("working_space") if _space(plan.get("working_space")) else {}

    manifest = plan.get("metadata_manifest")
    if not isinstance(manifest, dict):
        errors.append("color_plan.metadata_manifest requires path and sha256")
    else:
        raw_path, digest = manifest.get("path"), manifest.get("sha256")
        valid_digest = isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest)
        if not valid_digest:
            errors.append("metadata_manifest.sha256 must contain 64 hexadecimal characters")
        if not _text(raw_path):
            errors.append("metadata_manifest.path must be an absolute file path")
        else:
            path = Path(raw_path)
            if not path.is_absolute() or not path.is_file():
                errors.append(f"metadata_manifest.path is not an existing absolute file: {raw_path}")
            elif valid_digest:
                try:
                    if hashlib.sha256(path.read_bytes()).hexdigest() != digest.lower():
                        errors.append("metadata_manifest.sha256 does not match the current file")
                except OSError as exc:
                    errors.append(f"Cannot read metadata_manifest: {exc}")

    clips = payload.get("clips", [])
    if not isinstance(clips, list):
        errors.append("blueprint.clips must be an array")
        return result
    visual, all_ids = {}, set()
    for index, clip in enumerate(clips):
        if not isinstance(clip, dict):
            errors.append(f"blueprint.clips[{index}] must be an object")
            continue
        cid = clip.get("id")
        if not _text(cid):
            errors.append(f"blueprint.clips[{index}].id is required for color_plan")
            continue
        if cid in all_ids:
            errors.append(f"Duplicate blueprint clip id: {cid}")
        all_ids.add(cid)
        if clip.get("media_type", "video") in ("video", "image"):
            visual[cid] = clip
    entries = plan.get("clips")
    if not isinstance(entries, list):
        errors.append("color_plan.clips must be an array")
        return result
    by_id = {}
    for index, entry in enumerate(entries):
        before = len(errors)
        if not isinstance(entry, dict):
            errors.append(f"color_plan.clips[{index}] must be an object")
            continue
        cid = entry.get("clip_id")
        if not _text(cid):
            errors.append(f"color_plan.clips[{index}].clip_id is required")
            continue
        if cid in by_id:
            errors.append(f"{cid}: duplicate color entry")
        by_id[cid] = entry
        if cid not in visual:
            errors.append(f"{cid}: color entry must reference a visual blueprint clip")
        if not _text(entry.get("scene_id")):
            errors.append(f"{cid}: scene_id is required")
        inp, confirmed, input_values = entry.get("input"), True, {}
        for field in ("gamut", "gamma"):
            item = inp.get(field) if isinstance(inp, dict) else None
            if not isinstance(item, dict) or not isinstance(item.get("status"), str) or item["status"] not in STATUSES:
                errors.append(f"{cid}: input.{field} needs value, status and evidence")
                confirmed = False
                continue
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                errors.append(f"{cid}: input.{field}.evidence must be an array")
            if item["status"] == "confirmed":
                if not _text(item.get("value")) or not _evidence(evidence):
                    errors.append(f"{cid}: confirmed input.{field} requires a value and attributable evidence")
                    confirmed = False
                else:
                    input_values[field] = item["value"]
            else:
                confirmed = False
        existing = entry.get("existing_input_transforms")
        if not isinstance(existing, list):
            errors.append(f"{cid}: existing_input_transforms must be an array (including project RCM)")
            existing = []
        action, transform = entry.get("action"), entry.get("input_transform")
        unresolved, adjustments = entry.get("unresolved"), entry.get("adjustments")
        if not isinstance(adjustments, list) or not all(_text(x) for x in adjustments):
            errors.append(f"{cid}: adjustments must be an array of adjustment intentions")
        if not isinstance(unresolved, list) or not all(_text(x) for x in unresolved):
            errors.append(f"{cid}: unresolved must be an array of explanations")
            unresolved = []
        if action == "blocked":
            if transform is not None:
                errors.append(f"{cid}: blocked clips must not carry an executable input_transform")
            if not unresolved:
                errors.append(f"{cid}: blocked clips require an unresolved reason")
            blocked.append(cid)
            blocked_reasons[cid] = unresolved
        elif action in ("apply", "already_normalized"):
            if not confirmed:
                errors.append(f"{cid}: {action} requires separately confirmed input gamut and gamma")
            if unresolved:
                errors.append(f"{cid}: unresolved input issues require action='blocked'")
            if action == "apply":
                if existing:
                    errors.append(f"{cid}: duplicate input conversion: an existing transform is declared")
                if not isinstance(transform, dict) or not isinstance(transform.get("method"), str) or transform["method"] not in METHODS:
                    errors.append(f"{cid}: apply requires exactly one input_transform method: rcm, cst or lut")
                else:
                    allowed = {"method", "lut_path"} if transform["method"] == "lut" else {"method"}
                    if set(transform) - allowed:
                        errors.append(f"{cid}: unsupported input_transform fields; declare one conversion only")
                    if transform["method"] == "lut":
                        lut_path = transform.get("lut_path")
                        if not _text(lut_path) or not Path(lut_path).is_absolute() or not Path(lut_path).is_file():
                            errors.append(f"{cid}: lut input_transform requires an existing absolute lut_path")
            else:
                if transform is not None:
                    errors.append(f"{cid}: already_normalized must not apply another input transform")
                if len(existing) > 1:
                    errors.append(f"{cid}: multiple existing input conversions must be reviewed and blocked")
                elif existing:
                    previous = existing[0]
                    if not isinstance(previous, dict) or not isinstance(previous.get("method"), str) or previous["method"] not in METHODS | {"baked"}:
                        errors.append(f"{cid}: existing transform needs a supported method")
                    elif not _space(previous.get("output_space")) or not _same_space(previous["output_space"], working):
                        errors.append(f"{cid}: existing transform must resolve into working_space")
                    if not isinstance(previous, dict) or not _evidence(previous.get("evidence")):
                        errors.append(f"{cid}: existing transform requires attributable evidence")
                elif not _same_space(input_values, working):
                    errors.append(f"{cid}: no existing conversion and input does not equal working_space")
        else:
            errors.append(f"{cid}: action must be apply, already_normalized or blocked")
        if len(errors) > before:
            invalid.append(cid)
        elif action != "blocked":
            ready.append(cid)
    missing = sorted(set(visual) - set(by_id))
    if missing:
        errors.append("Missing color entries for visual clips: " + ", ".join(missing))
        invalid.extend(missing)
    for cid, entry in by_id.items():
        ref = entry.get("reference_clip_id")
        if entry.get("action") == "blocked" and ref is None:
            continue
        reference = by_id.get(ref) if isinstance(ref, str) else None
        if not isinstance(ref, str) or ref not in visual:
            errors.append(f"{cid}: reference_clip_id must name a visual clip (or null while blocked)")
            invalid.append(cid)
        elif reference is None or reference.get("scene_id") != entry.get("scene_id"):
            errors.append(f"{cid}: reference_clip_id must have a color entry in the same scene")
            invalid.append(cid)
        elif entry.get("action") != "blocked" and reference.get("action") == "blocked":
            errors.append(f"{cid}: a ready clip cannot use a blocked color reference")
            invalid.append(cid)
    result["plan_valid"] = not errors
    result["all_clips_ready"] = not errors and not blocked
    if require_ready and blocked:
        errors.append("Color work is blocked for: " + ", ".join(blocked))
    if errors:
        ready.clear()
    result["invalid_clip_ids"] = sorted(set(invalid))
    return result
