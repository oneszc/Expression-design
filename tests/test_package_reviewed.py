import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package_reviewed as module


class PackageReviewedTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.manifest = self.root / "manifest.json"
        self.review = self.root / "review.json"
        self.output = self.root / "approved.zip"
        data = {"profile": "wechat-user-2026-11-04", "name": "测试", "name_status": "confirmed",
                "description": "用于合成测试的表情清单。",
                "mode": "static", "count": 8, "stickers": [], "banner": "banner.png",
                "cover": "cover.png", "icon": "icon.png"}
        names = []
        for i in range(8):
            name = f"表情{i}.png"
            self.image(name, (240, 240), i)
            data["stickers"].append({"file": name, "meaning": f"含义{i}"})
            names.append(name)
        for name, size in [("banner.png", (750, 400)), ("cover.png", (240, 240)), ("icon.png", (50, 50))]:
            self.image(name, size, 10)
            names.append(name)
        self.manifest.write_text(json.dumps(data))
        self.record = {"schema_version": 1, "reviewer_id": "test-fixture-not-real-review",
                       "manifest_sha256": self.hash(self.manifest), "items": [],
                       "batch": {"score": 90, "decision": "pass", "critical_issues": [],
                                 "unchecked": [], "evidence": "Synthetic test data only"}}
        for name in names:
            self.record["items"].append({"file": name, "sha256": self.hash(self.root / name),
                "stage": "final", "decision": "pass", "critical_issues": [], "unchecked": [],
                "scores": {"identity": 20, "expression": 20, "craft": 26, "legibility": 15},
                "evidence": {key: "Synthetic boundary fixture" for key in module.LIMITS},
                "checks": {"light": True, "dark": True}})
            for role in ("banner", "cover", "icon"):
                if name == data[role]:
                    self.record["items"][-1]["checks"][role + "_design"] = True
                    self.record["items"][-1]["platform_evidence"] = "Synthetic WeChat design check, not real review"

    def image(self, name, size, index):
        im = Image.new("RGBA", size)
        ImageDraw.Draw(im).rectangle((5, 5, 25 + index, 25 + index), fill=(20 + index, 100, 180, 255))
        im.save(self.root / name)

    def hash(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run_package(self):
        self.review.write_text(json.dumps(self.record))
        return module.package(self.manifest, self.review, self.output)

    def rejected(self):
        with self.assertRaises(ValueError):
            self.run_package()
        self.assertFalse(self.output.exists())

    def test_81_passes_and_zip_contains_only_delivery(self):
        self.run_package()
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), {"manifest.json"} | {v["file"] for v in self.record["items"]})
            self.assertIsNone(archive.testzip())

    def test_80_and_boolean_scores_rejected(self):
        self.record["items"][0]["scores"]["legibility"] = 14
        self.rejected()
        self.record["items"][0]["scores"]["legibility"] = True
        self.rejected()

    def test_missing_wechat_design_review_rejected(self):
        self.record["items"][-1]["checks"].pop("icon_design")
        self.rejected()

    def test_high_score_cannot_hide_critical_defect_or_weak_expression(self):
        item = self.record["items"][0]
        item["critical_issues"] = ["extra arm"]
        self.rejected()
        item["critical_issues"] = []
        item["scores"] = {"identity": 25, "expression": 17, "craft": 35, "legibility": 15}
        self.rejected()

    def test_revised_asset_requires_fresh_review(self):
        self.image("表情0.png", (240, 240), 30)
        self.rejected()
        self.record["items"][0]["sha256"] = self.hash(self.root / "表情0.png")
        self.run_package()
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.read("表情0.png"), (self.root / "表情0.png").read_bytes())

    def test_changed_meaning_invalidates_manifest_review(self):
        data = json.loads(self.manifest.read_text())
        data["stickers"][0]["meaning"] = "changed"
        self.manifest.write_text(json.dumps(data))
        self.rejected()

    def test_missing_duplicate_draft_blocked_and_batch_failures(self):
        original = json.loads(json.dumps(self.record))
        for change in (lambda r: r["items"].pop(),
                       lambda r: r["items"].append(r["items"][0]),
                       lambda r: r["items"][0].update(stage="draft"),
                       lambda r: r["items"][0].update(decision="blocked"),
                       lambda r: r["batch"].update(score=80)):
            self.record = json.loads(json.dumps(original))
            change(self.record)
            self.rejected()

    def test_animation_needs_playback_not_just_decodable_frames(self):
        data = json.loads(self.manifest.read_text())
        data["mode"] = "animated"
        for i, entry in enumerate(data["stickers"]):
            frames = []
            for x in (10, 30):
                im = Image.new("RGB", (240, 240), "white")
                ImageDraw.Draw(im).rectangle((x, 10, x + 10 + i, 30), fill="black")
                frames.append(im)
            name = f"表情{i}.gif"
            frames[0].save(self.root / name, save_all=True, append_images=frames[1:], duration=100, loop=0)
            entry["file"] = name
            item = self.record["items"][i]
            item.update(file=name, sha256=self.hash(self.root / name), playback_evidence="Fixture only")
            item["checks"].update(all_frames=True, playback=False)
        self.manifest.write_text(json.dumps(data))
        self.record["manifest_sha256"] = self.hash(self.manifest)
        self.rejected()
        for item in self.record["items"][:8]:
            item["checks"]["playback"] = True
        self.run_package()

    def test_technical_failure_and_no_overwrite(self):
        self.image("icon.png", (240, 240), 10)
        self.record["items"][-1]["sha256"] = self.hash(self.root / "icon.png")
        self.rejected()
        self.image("icon.png", (50, 50), 10)
        self.record["items"][-1]["sha256"] = self.hash(self.root / "icon.png")
        self.run_package()
        previous = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_package()
        self.assertEqual(self.output.read_bytes(), previous)

    def test_changed_bytes_after_initial_validation_are_revalidated(self):
        bad = b"not-an-image"
        self.record["items"][-1]["sha256"] = hashlib.sha256(bad).hexdigest()
        validate = module.validate

        def change_after_validation(path):
            result = validate(path)
            if Path(path).resolve() == self.manifest.resolve():
                (self.root / "icon.png").write_bytes(bad)
            return result

        with patch.object(module, "validate", side_effect=change_after_validation):
            with self.assertRaisesRegex(ValueError, "Snapshot technical validation failed"):
                self.run_package()
        self.assertEqual((self.root / "icon.png").read_bytes(), bad)
        self.assertFalse(self.output.exists())

    def test_resolving_inside_delivery_is_not_enough_for_archive_paths(self):
        data = json.loads(self.manifest.read_text())
        name = f"../{self.root.name}/icon.png"
        data["icon"] = name
        self.record["items"][-1]["file"] = name
        self.manifest.write_text(json.dumps(data))
        self.record["manifest_sha256"] = self.hash(self.manifest)
        self.rejected()

    def test_unknown_scores_and_incomplete_observations_do_not_pass(self):
        original = json.loads(json.dumps(self.record))
        for change in (lambda r: r["items"][0]["scores"].update(craft=None),
                       lambda r: r["items"][0]["checks"].update(light=1),
                       lambda r: r["items"][0].update(unchecked=["dark background"]),
                       lambda r: r["items"][0]["evidence"].update(expression=" ")):
            self.record = json.loads(json.dumps(original))
            change(self.record)
            self.rejected()

    def test_cli_pass_and_failure_exit_codes(self):
        self.review.write_text(json.dumps(self.record))
        command = [sys.executable, str(Path(module.__file__)), str(self.manifest),
                   str(self.review), "--output", str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])
        self.record["items"][0]["scores"]["legibility"] = 14
        self.review.write_text(json.dumps(self.record))
        failed = self.root / "failed.zip"
        command[-1] = str(failed)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse(json.loads(result.stdout)["valid"])
        self.assertFalse(failed.exists())


if __name__ == "__main__":
    unittest.main()
