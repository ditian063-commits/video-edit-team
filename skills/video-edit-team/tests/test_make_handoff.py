import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_handoff import STAGES, make_handoff


class HandoffTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.blueprint = self.root / "blueprint.json"
        self.render = self.root / "render.mp4"
        self.delivery = self.root / "delivered.mp4"
        self.qc = self.root / "qc.json"
        self.render.write_bytes(b"fixture render bytes")
        self.qc.write_text('{"unverified":["audition"]}', encoding="utf-8")
        self.plan = {
            "schema_version": "1.0",
            "version": "v2",
            "project": {"name": "剪辑", "fps": 24},
            "timeline": {"name": "Edit v2", "action": "create"},
            "clips": [
                {"id": "picture", "media_type": "video", "visual_content": "not in packet"},
                {"id": "music", "media_type": "audio", "source_path": str(self.root / "music.wav"),
                 "source_in_seconds": 2, "source_out_seconds": 9, "processing_baked": True},
            ],
            "music": [{"clip_id": "music", "placement": "reference_only"}],
            "audio_plan": {"origin_source_in_seconds": 5, "origin_source_out_seconds": 12,
                           "processing_already_baked": {"constant_gain_db": -2, "filter": "internal"}},
            "captions": [{"text": "not in packet"}],
            "color_plan": {"bypass_by_user": True, "clips": [{"action": "blocked"}]},
            "delivery": {"output_path": str(self.render), "final_delivery_path": str(self.delivery),
                         "subtitle_mode": "sidecar"},
        }

    def save(self):
        data = ("\ufeff" + json.dumps(self.plan, ensure_ascii=False, indent=3) + "\n").encode("utf-8")
        self.blueprint.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def test_exact_revision_and_paths_are_shared_by_all_stages(self):
        expected_hash = self.save()
        for stage in STAGES:
            with self.subTest(stage=stage):
                evidence = [self.qc, self.render] if stage == "dsh-delivery" else [self.qc]
                report = make_handoff(self.blueprint, stage, evidence)
                self.assertEqual(report["blueprint"]["sha256"], expected_hash)
                self.assertEqual(report["blueprint"]["version"], "v2")
                self.assertEqual(report["delivery"], self.plan["delivery"])
                self.assertEqual(report["project"], self.plan["project"])
                self.assertEqual(report["timeline"], self.plan["timeline"])
                self.assertEqual(report["clip_counts"], {"audio": 1, "video": 1})
                self.assertEqual(report["audio"]["origin_source_in_seconds"], 5)
                self.assertEqual(report["audio"]["tracks"][0]["source_out_seconds"], 9)
                self.assertEqual(report["audio"]["processing_already_baked"], {"constant_gain_db": -2})
                self.assertEqual(report["captions"], {"count": 1, "subtitle_mode": "sidecar"})
                self.assertEqual(report["color"]["action_counts"], {"blocked": 1})
                self.assertEqual(report["evidence"][0]["sha256"], hashlib.sha256(self.qc.read_bytes()).hexdigest())
                self.assertEqual(report["verification"], "handoff_only")
                self.assertNotIn("not in packet", json.dumps(report))
                if stage == "dsh-delivery":
                    self.assertEqual(report["render"], report["evidence"][1])
                else:
                    self.assertNotIn("render", report)
        self.assertFalse(self.delivery.exists())

    def test_delivery_uses_declared_evidence_and_detects_mismatch(self):
        self.save()
        with self.assertRaisesRegex(ValueError, "declared render or final delivery path"):
            make_handoff(self.blueprint, "dsh-delivery", [self.qc])
        self.delivery.write_bytes(b"unrelated bytes")
        with self.assertRaisesRegex(ValueError, "different hashes"):
            make_handoff(self.blueprint, "dsh-delivery", [self.render, self.delivery])
        final_only = make_handoff(self.blueprint, "dsh-delivery", [self.delivery])
        self.assertEqual(final_only["render"]["path"], str(self.delivery))

    def test_cli_legacy_without_export_and_missing_evidence(self):
        self.plan = {"project": {"name": "剪辑"}, "clips": []}
        self.save()
        command = [sys.executable, str(SCRIPTS / "make_handoff.py"), str(self.blueprint), "--stage", "confirm"]
        good = subprocess.run(command, capture_output=True, check=True)
        report = json.loads(good.stdout)
        self.assertEqual(report["project"]["name"], "剪辑")
        self.assertNotIn("delivery", report)
        self.assertNotIn("timeline", report)
        bad = subprocess.run(command + ["--evidence", str(self.root / "missing.json")], capture_output=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertFalse(bad.stdout)
        self.assertIn(b"evidence must be a regular file", bad.stderr)


if __name__ == "__main__":
    unittest.main()
