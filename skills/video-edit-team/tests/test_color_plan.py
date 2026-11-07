from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from color_plan import validate_color_plan
from validate_blueprint import validate_blueprint, validate_delivery


def evidence(value):
    return [{"source": "verified metadata", "field": "profile", "value": value}]


def confirmed(value):
    return {"value": value, "status": "confirmed", "evidence": evidence(value)}


def color_entry(cid, gamut, gamma):
    return {
        "clip_id": cid, "scene_id": "interview", "reference_clip_id": "a",
        "input": {"gamut": confirmed(gamut), "gamma": confirmed(gamma)},
        "existing_input_transforms": [], "action": "apply",
        "input_transform": {"method": "rcm"},
        "adjustments": ["white_balance", "shot_match"], "unresolved": [],
    }


class ColorPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "media-manifest.json"
        self.manifest.write_text("[]", encoding="utf-8")
        source = self.root / "source.mp4"
        source.write_bytes(b"offline fixture, never imported into Resolve")
        self.plan = {
            "clips": [
                {"id": cid, "media_type": "video", "source_path": str(source),
                 "source_in_seconds": 0, "source_out_seconds": 2,
                 "timeline_in_seconds": i * 2, "timeline_out_seconds": (i + 1) * 2}
                for i, cid in enumerate(("a", "b"))
            ],
            "color_plan": {
                "version": "1.0",
                "metadata_manifest": {"path": str(self.manifest), "sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest()},
                "working_space": {"gamut": "DaVinci Wide Gamut", "gamma": "DaVinci Intermediate"},
                "output_space": {"gamut": "Rec.709", "gamma": "Gamma 2.4"},
                "clips": [color_entry("a", "S-Gamut3.Cine", "S-Log3"), color_entry("b", "Rec.709", "Gamma 2.4")],
            },
        }

    def test_confirmed_mixed_log_and_sdr_are_ready(self):
        result = validate_color_plan(self.plan, require_ready=True)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["all_clips_ready"])
        self.assertEqual(result["ready_clip_ids"], ["a", "b"])

    def test_unknown_and_conflicting_cannot_convert(self):
        for status in ("unknown", "candidate", "conflicting"):
            with self.subTest(status=status):
                self.plan["color_plan"]["clips"][1]["input"]["gamma"]["status"] = status
                result = validate_color_plan(self.plan)
                self.assertTrue(result["errors"])
                self.assertEqual(result["ready_clip_ids"], [])
                self.assertIn("b", result["invalid_clip_ids"])

    def block_b(self):
        item = self.plan["color_plan"]["clips"][1]
        item["input"]["gamma"] = {"value": None, "status": "unknown", "evidence": []}
        item.update(action="blocked", input_transform=None, reference_clip_id=None,
                    unresolved=["Recording gamma is not known"])

    def test_valid_blocked_plan_preserves_safe_work_but_fails_final_readiness(self):
        self.block_b()
        result = validate_color_plan(self.plan, require=True)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["plan_valid"])
        self.assertFalse(result["all_clips_ready"])
        self.assertEqual(result["ready_clip_ids"], ["a"])
        self.assertEqual(result["blocked_clip_ids"], ["b"])
        self.assertTrue(validate_color_plan(self.plan, require_ready=True)["errors"])

    def existing_transform(self):
        return {"method": "rcm", "output_space": self.plan["color_plan"]["working_space"],
                "evidence": evidence("Resolve RCM readback")}

    def test_rcm_plus_second_cst_is_rejected(self):
        item = self.plan["color_plan"]["clips"][0]
        item["existing_input_transforms"] = [self.existing_transform()]
        item["input_transform"] = {"method": "cst"}
        self.assertIn("duplicate input conversion", " ".join(validate_color_plan(self.plan)["errors"]))

    def test_multiple_new_input_methods_are_rejected(self):
        self.plan["color_plan"]["clips"][0]["input_transform"] = {"method": "rcm", "then": "lut"}
        self.assertTrue(validate_color_plan(self.plan)["errors"])

    def test_existing_normalization_requires_evidence_and_target(self):
        item = self.plan["color_plan"]["clips"][0]
        item.update(action="already_normalized", input_transform=None,
                    existing_input_transforms=[self.existing_transform()])
        self.assertEqual(validate_color_plan(self.plan)["errors"], [])
        item["existing_input_transforms"][0]["output_space"] = {"gamut": "Rec.709", "gamma": "Gamma 2.4"}
        self.assertTrue(validate_color_plan(self.plan)["errors"])

    def test_missing_visual_and_cross_scene_references_fail(self):
        bad = copy.deepcopy(self.plan)
        bad["color_plan"]["clips"].pop()
        self.assertTrue(validate_color_plan(bad)["errors"])
        self.plan["color_plan"]["clips"][1]["scene_id"] = "exterior"
        self.assertIn("same scene", " ".join(validate_color_plan(self.plan)["errors"]))

    def test_output_space_and_manifest_revision_are_required(self):
        bad = copy.deepcopy(self.plan)
        bad["color_plan"].pop("output_space")
        self.assertTrue(validate_color_plan(bad)["errors"])
        self.manifest.write_text("[{}]", encoding="utf-8")
        self.assertIn("does not match", " ".join(validate_color_plan(self.plan)["errors"]))

    def test_audio_does_not_require_color_or_collide_with_video(self):
        audio = copy.deepcopy(self.plan["clips"][0])
        audio.update(id="music", media_type="audio", audio_track=1)
        self.plan["clips"].append(audio)
        self.assertEqual(validate_blueprint(self.plan, require_color_ready=True)["errors"], [])
        self.plan["color_plan"]["clips"].append(color_entry("music", "Rec.709", "Gamma 2.4"))
        self.assertTrue(validate_color_plan(self.plan)["errors"])

    def test_legacy_blueprint_remains_compatible_unless_required(self):
        self.plan.pop("color_plan")
        self.assertEqual(validate_blueprint(self.plan)["errors"], [])
        self.assertTrue(validate_blueprint(self.plan, require_color_plan=True)["errors"])
        self.assertFalse(validate_color_plan(self.plan)["all_clips_ready"])

    def test_cli_distinguishes_structural_validity_and_execution_readiness(self):
        self.block_b()
        path = self.root / "blueprint.json"
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        command = [sys.executable, str(SCRIPTS / "validate_blueprint.py"), str(path)]
        partial = subprocess.run(command + ["--require-color-plan"], capture_output=True, text=True)
        final = subprocess.run(command + ["--require-color-ready"], capture_output=True, text=True)
        self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
        self.assertEqual(final.returncode, 1, final.stdout + final.stderr)
        self.assertFalse(json.loads(partial.stdout)["color_plan"]["all_clips_ready"])

    def test_malformed_status_and_transform_report_errors(self):
        item = self.plan["color_plan"]["clips"][0]
        item["input"]["gamma"]["status"] = []
        item["input_transform"]["method"] = []
        self.assertTrue(validate_color_plan(self.plan)["errors"])

    def delivery(self):
        return {
            "output_path": str(self.root / "renders" / "preview-v1.mp4"),
            "container": "mp4", "video_codec": "h264", "audio_codec": "aac",
            "width": 1920, "height": 1080, "fps": 24,
            "range": {"start_seconds": 0, "end_seconds": 4},
            "color_space": {"gamut": "Rec.709", "gamma": "Gamma 2.4"},
            "subtitle_mode": "sidecar",
        }

    def test_delivery_requires_explicit_spec_but_remains_optional_for_legacy(self):
        self.assertEqual(validate_blueprint(self.plan)["errors"], [])
        self.assertTrue(validate_blueprint(self.plan, require_delivery=True)["errors"])
        self.plan["delivery"] = self.delivery()
        result = validate_blueprint(self.plan, require_color_ready=True, require_delivery=True)
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["delivery"]["valid"])
        self.assertFalse(Path(self.plan["delivery"]["output_path"]).parent.exists())

    def test_delivery_rejects_existing_or_original_output(self):
        self.plan["delivery"] = self.delivery()
        existing = self.root / "existing.mp4"
        existing.write_bytes(b"already exported")
        for output in (str(existing), self.plan["clips"][0]["source_path"], "relative.mp4"):
            with self.subTest(output=output):
                self.plan["delivery"]["output_path"] = output
                self.assertTrue(validate_delivery(self.plan)["errors"])
        self.assertEqual(existing.read_bytes(), b"already exported")

    def test_delivery_rejects_bad_numbers_range_and_color_mismatch(self):
        changes = (
            {"fps": float("nan")}, {"width": True}, {"height": 0},
            {"range": {"start_seconds": 4, "end_seconds": 2}},
            {"range": {"start_seconds": 0, "end_seconds": float("inf")}},
            {"color_space": {"gamut": "Rec.2020", "gamma": "ST2084"}},
            {"subtitle_mode": "guess"}, {"audio_codec": ""},
        )
        for change in changes:
            with self.subTest(change=change):
                self.plan["delivery"] = self.delivery() | change
                self.assertTrue(validate_delivery(self.plan)["errors"])

    def test_cli_delivery_preflight_does_not_render_or_create_directories(self):
        self.plan["delivery"] = self.delivery()
        path = self.root / "delivery-blueprint.json"
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        command = [sys.executable, str(SCRIPTS / "validate_blueprint.py"), str(path),
                   "--require-color-ready", "--require-delivery"]
        good = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertEqual(json.loads(good.stdout)["delivery"]["verification"], "spec_only_not_render_verification")
        self.assertFalse((self.root / "renders").exists())
        self.plan.pop("delivery")
        path.write_text(json.dumps(self.plan), encoding="utf-8")
        bad = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
        self.assertIn("delivery is required", json.loads(bad.stdout)["errors"])


if __name__ == "__main__":
    unittest.main()
