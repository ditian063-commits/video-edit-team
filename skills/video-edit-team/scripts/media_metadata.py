"""Read camera and colour evidence without modifying media or guessing a profile."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit


RAW_VIDEO = {".braw", ".r3d"}
VIDEO = {".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".webm", ".mpg", ".mpeg", ".mxf"} | RAW_VIDEO
AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".wma"}
IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
MEDIA_SUFFIXES = VIDEO | AUDIO | IMAGE
MAX_SIDECAR_BYTES = 2 * 1024 * 1024
MAX_SIDECARS = 128
ENCODED_FIELDS = (
    "codec_name", "codec_tag_string", "profile", "pix_fmt", "bits_per_raw_sample",
    "color_primaries", "color_transfer", "color_space", "color_range",
    "r_frame_rate", "avg_frame_rate", "time_base", "width", "height",
)

# Only explicitly named input/capture properties can confirm an input transform.
# Generic Gamma/Gamut properties are retained as candidates, never auto-applied.
FIELD_ALIASES = {
    "make": {"make", "cameramake", "manufacturer", "cameramanufacturer", "comapplequicktimemake"},
    "model": {"model", "modelname", "cameramodel", "cameramodelname", "comapplequicktimemodel"},
    "body_id": {"bodyserialnumber", "cameraserialnumber", "cameraserial", "serialnumber", "serialno"},
    "input_gamut": {"inputgamut", "inputcolorspace", "capturegamut", "capturecolorspace", "capturecolorprimaries", "recordinggamut"},
    "input_gamma": {"inputgamma", "capturegamma", "capturegammaequation", "recordinggamma", "shootinggamma"},
}
CANDIDATE_ALIASES = {"input_gamut": {"gamut"}, "input_gamma": {"gamma", "gammaequation", "gammacurve"}}
REFERENCE_FIELDS = {
    "filename", "clipfilename", "mediafilename", "sourcefilename", "sourcefile",
    "filepath", "sourcepath", "mediafile", "clipfile", "videofile", "clipname",
    "clipuri", "mediauri", "src", "href",
}
EMPTY_VALUES = {"", "unknown", "unspecified", "undefined", "none", "null", "na", "notavailable", "未知", "未指定"}


def _key(value: str) -> str:
    local = value.rsplit("}", 1)[-1].rsplit(":", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", local.casefold())


def _comparable(value: object) -> str:
    result = "".join(character for character in str(value).casefold() if character.isalnum())
    return {"sonycorporation": "sony", "sonycorp": "sony", "canoninc": "canon", "nikoncorporation": "nikon"}.get(result, result)


def _field(evidence: list[dict]) -> dict:
    usable = [e for e in evidence if _comparable(e["value"]) not in EMPTY_VALUES]
    distinct = {_comparable(e["value"]) for e in usable}
    if not distinct:
        return {"value": None, "status": "unknown", "evidence": usable}
    if len(distinct) > 1:
        return {"value": None, "status": "conflicting", "evidence": usable}
    confirmed = [e for e in usable if e["strength"] == "confirmed"]
    chosen = (confirmed or usable)[0]
    return {"value": chosen["value"], "status": "confirmed" if confirmed else "candidate", "evidence": usable}


def _collect_fields(entries: list[dict]) -> tuple[dict, dict]:
    evidence: dict[str, list] = {name: [] for name in FIELD_ALIASES}
    for entry in entries:
        key = _key(entry["key"])
        context = entry["field"].casefold()
        # Lens model/serial and editing software identity are not camera identity.
        if any(word in context for word in ("lens", "software", "encoder", "harddisk")):
            continue
        for name, aliases in FIELD_ALIASES.items():
            strength = "confirmed" if key in aliases else "candidate" if key in CANDIDATE_ALIASES.get(name, set()) else None
            if strength is None:
                continue
            if entry["tool"] == "sidecar" and name in {"make", "model", "body_id"}:
                # Generic XML Model/Serial properties need a camera/device context.
                known_context = any(word in context for word in ("camera", "device", "tiff", "exif"))
                if not known_context and key in {"model", "modelname", "manufacturer", "serialnumber", "serialno"}:
                    strength = "candidate"
            evidence[name].append({k: entry[k] for k in ("tool", "source", "field", "value")} | {"strength": strength})
    fields = {name: _field(items) for name, items in evidence.items()}
    return ({name: fields[name] for name in ("make", "model", "body_id")},
            {name: fields[name] for name in ("input_gamut", "input_gamma")})


def _run_json(command: list[str], timeout: float) -> tuple[object | None, dict]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except FileNotFoundError:
        return None, {"status": "unavailable", "error": f"Executable not found: {command[0]}"}
    except subprocess.TimeoutExpired:
        return None, {"status": "timeout", "error": f"Metadata command exceeded {timeout:g} seconds"}
    except OSError as exc:
        return None, {"status": "error", "error": str(exc)}
    if result.returncode:
        return None, {"status": "error", "error": result.stderr.strip() or f"Exit status {result.returncode}"}
    try:
        return json.loads(result.stdout), {"status": "ok"}
    except (json.JSONDecodeError, TypeError) as exc:
        return None, {"status": "parse_error", "error": str(exc)}


def probe_file(path: Path, executable: str = "ffprobe", timeout: float = 20) -> tuple[dict, dict]:
    data, report = _run_json([executable, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], timeout)
    if report["status"] == "ok" and not isinstance(data, dict):
        report = {"status": "parse_error", "error": "FFprobe output must be a JSON object"}
    if report["status"] == "ok" and (("format" in data and not isinstance(data["format"], dict)) or
                                      ("streams" in data and (not isinstance(data["streams"], list) or any(not isinstance(stream, dict) for stream in data["streams"])))):
        report = {"status": "parse_error", "error": "FFprobe format/streams metadata has an unexpected shape"}
    return (data if report["status"] == "ok" else {"error": report["error"]}), report


def _probe_entries(probe: dict, path: Path) -> list[dict]:
    entries = []
    containers = [("format", probe.get("format", {}))]
    streams = probe.get("streams", [])
    if isinstance(streams, list):
        containers.extend((f"streams[{i}]", item) for i, item in enumerate(streams))
    for location, obj in containers:
        if not isinstance(obj, dict) or not isinstance(obj.get("tags", {}), dict):
            continue
        for key, value in obj.get("tags", {}).items():
            if isinstance(value, (str, int, float)):
                entries.append({"tool": "ffprobe", "source": str(path), "field": f"{location}.tags.{key}", "key": key, "value": value})
    return entries


def _xml_entries(root: ET.Element, sidecar: Path) -> list[dict]:
    entries = []

    def walk(element: ET.Element, parents: list[str]) -> None:
        parts = parents + [str(element.tag)]
        field = "/".join(parts)
        value = (element.text or "").strip()
        if value:
            entries.append({"tool": "sidecar", "source": str(sidecar), "field": field, "key": str(element.tag), "value": value})
        for key, value in element.attrib.items():
            semantic_key = str(element.tag) if _key(key) == "value" else key
            entries.append({"tool": "sidecar", "source": str(sidecar), "field": f"{field}/@{key}", "key": semantic_key, "value": value})
        for child in element:
            walk(child, parts)

    walk(root, [])
    return entries


def _reference_match(value: object, key: str, media: Path, stem_collision: bool) -> bool | None:
    """None is not a media reference; False is a conflicting/ambiguous reference."""
    raw = unquote(str(value).strip()).replace("\\", "/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme == "file":
        if parsed.netloc and parsed.netloc not in {"localhost", ""}:
            raw = f"//{parsed.netloc}{parsed.path}"
        else:
            raw = parsed.path
            if re.match(r"^/[A-Za-z]:/", raw):
                raw = raw[1:]
    elif parsed.scheme and not re.match(r"^[A-Za-z]:/", raw):
        return False if Path(parsed.path).suffix.casefold() in MEDIA_SUFFIXES else None
    reference = Path(raw)
    if not reference.suffix and key == "clipname":
        return not stem_collision and raw.casefold() == media.stem.casefold()
    if reference.suffix.casefold() not in MEDIA_SUFFIXES:
        return None
    if "/" not in raw:
        return raw.casefold() == media.name.casefold()
    resolved = reference.resolve() if reference.is_absolute() else (media.parent / reference).resolve()
    return str(resolved).casefold() == str(media.resolve()).casefold()


def read_sidecars(path: Path) -> tuple[list[dict], list[dict], list[str]]:
    """Inspect a bounded set of XML/XMP files in the media's own directory."""
    try:
        siblings = list(path.parent.iterdir())
    except OSError as exc:
        return [], [], [f"Cannot inspect sidecars: {exc}"]
    names = {f"{path.stem}.xml".casefold(), f"{path.stem}.xmp".casefold(), f"{path.name}.xml".casefold(), f"{path.name}.xmp".casefold()}
    candidates = sorted((p for p in siblings if p.suffix.casefold() in {".xml", ".xmp"}), key=lambda p: (p.name.casefold() not in names, p.name.casefold()))
    collisions = [p for p in siblings if p.suffix.casefold() in MEDIA_SUFFIXES and p.stem.casefold() == path.stem.casefold()]
    stem_collision = len(collisions) > 1
    warnings = [f"Sidecar search limited to {MAX_SIDECARS} XML/XMP files in the media directory"] if len(candidates) > MAX_SIDECARS else []
    reports, entries = [], []
    for sidecar in candidates[:MAX_SIDECARS]:
        report = {"source": str(sidecar), "status": "ignored"}
        try:
            if sidecar.is_symlink() or sidecar.resolve().parent != path.parent.resolve():
                report.update(status="rejected", reason="Sidecar is a link or resolves outside the media directory")
            elif not sidecar.is_file():
                continue
            elif sidecar.stat().st_size > MAX_SIDECAR_BYTES:
                report.update(status="rejected", reason="Sidecar exceeds the 2 MiB metadata limit")
            else:
                raw = sidecar.read_bytes()
                # Never process DTDs/entities or fetch referenced resources. Null
                # removal catches declarations in UTF-16/32 as well as UTF-8.
                declarations = raw.replace(b"\x00", b"").upper()
                if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
                    raise ValueError("DTD/entity declarations are not allowed in metadata sidecars")
                parsed = _xml_entries(ET.fromstring(raw), sidecar)
                references = [_reference_match(e["value"], _key(e["key"]), path, stem_collision) for e in parsed if _key(e["key"]) in REFERENCE_FIELDS]
                references = [r for r in references if r is not None]
                same_name = sidecar.name.casefold() in names
                fully_named = sidecar.name.casefold() in {f"{path.name}.xml".casefold(), f"{path.name}.xmp".casefold()}
                if False in references:
                    report.update(status="rejected", reason="Explicit clip reference does not identify this media exclusively")
                elif references or (same_name and (fully_named or not stem_collision)):
                    report.update(status="associated", association="explicit_clip_reference" if references else "same_filename")
                    entries.extend(parsed)
                elif same_name and stem_collision:
                    report.update(status="rejected", reason="Same-stem sidecar is ambiguous across media extensions")
                else:
                    report.update(reason="No verifiable association to this media")
        except (OSError, ET.ParseError, ValueError, RecursionError) as exc:
            report.update(status="parse_error", error=str(exc))
        reports.append(report)
    return entries, reports, warnings


def inspect_media(path: Path, media_type: str, *, ffprobe_executable: str = "ffprobe", exiftool_executable: str | None = None, timeout: float = 20) -> dict:
    """Return compatible raw probe data plus evidence-based camera/colour fields.

    exiftool_executable=None auto-detects ExifTool; an empty string disables it.
    Coverage describes tools checked, not certainty that all metadata exists.
    """
    if timeout <= 0:
        raise ValueError("Metadata timeout must be positive")
    path = path.resolve()
    if media_type == "image":
        probe, probe_report = {}, {"status": "not_applicable"}
    else:
        probe, probe_report = probe_file(path, ffprobe_executable, timeout)
    entries = _probe_entries(probe, path)
    tool = shutil.which("exiftool") if exiftool_executable is None else exiftool_executable
    if tool:
        exif, exif_report = _run_json([tool, "-json", "-G1", "-s", str(path)], timeout)
        if exif_report["status"] == "ok":
            if not isinstance(exif, list) or len(exif) != 1 or not isinstance(exif[0], dict):
                exif_report = {"status": "parse_error", "error": "ExifTool must return one metadata object for this media"}
            else:
                for key, value in exif[0].items():
                    if _key(key) == "error":
                        exif_report = {"status": "error", "error": str(value)}
                    elif _key(key) == "warning":
                        exif_report.setdefault("warnings", []).append(str(value))
                        if exif_report["status"] == "ok":
                            exif_report["status"] = "partial"
                    elif isinstance(value, (str, int, float)):
                        entries.append({"tool": "exiftool", "source": str(path), "field": key, "key": key, "value": value})
    else:
        exif_report = {"status": "disabled" if exiftool_executable == "" else "unavailable"}
    sidecar_entries, sidecars, sidecar_warnings = read_sidecars(path)
    entries.extend(sidecar_entries)
    camera, color = _collect_fields(entries)
    if media_type == "audio":
        camera = {name: _field([]) for name in ("make", "model", "body_id")}
    tools = {"ffprobe": probe_report, "exiftool": exif_report}
    errors = [{"tool": name, "error": report["error"]} for name, report in tools.items() if "error" in report]
    errors.extend({"tool": "sidecar", "source": r["source"], "error": r["error"]} for r in sidecars if "error" in r)
    partial = any(r["status"] not in {"ok", "not_applicable"} for r in tools.values()) or bool(errors or sidecar_warnings) or any(r["status"] == "rejected" for r in sidecars)
    coverage = {"level": "partial" if partial else "available_sources_checked", "tools": tools, "sidecars": sidecars, "errors": errors, "warnings": sidecar_warnings}
    coverage["resolve_backfill_recommended"] = path.suffix.casefold() in RAW_VIDEO and (probe_report["status"] != "ok" or any(f["status"] != "confirmed" for f in (camera["model"], color["input_gamut"], color["input_gamma"])))
    streams = probe.get("streams", []) if isinstance(probe.get("streams", []), list) else []
    color["encoded"] = {"streams": [{"stream_index": stream.get("index", i), **{k: stream[k] for k in ENCODED_FIELDS if k in stream}} for i, stream in enumerate(streams) if isinstance(stream, dict) and stream.get("codec_type") == "video"], "metadata": [{k: e[k] for k in ("tool", "source", "field", "value")} for e in entries if _key(e["key"]) in {"colorspace", "colorprimaries", "colortransfer", "transfercharacteristics", "matrixcoefficients", "colorrange"}]}
    camera["coverage"] = coverage
    color["coverage"] = coverage
    return {"probe": probe, "camera": camera, "color": color}
