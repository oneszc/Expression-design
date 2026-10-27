import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_pack.py"
spec = importlib.util.spec_from_file_location("validate_pack", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ValidatePackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "stickers").mkdir()
        self.path = self.root / "manifest.json"
        self.data = {
            "profile": module.PROFILE, "name": "慢半拍", "name_status": "confirmed",
            "mode": "static", "count": 8, "stickers": [],
            "banner": "banner.png", "cover": "cover.png", "icon": "icon.png",
        }
        for index in range(8):
            name = f"stickers/{index + 1:02}.png"
            self.image(self.root / name, (240, 240), index)
            self.data["stickers"].append({"file": name, "meaning": f"表达{index + 1}", "text": ""})
        for name, size in [("banner.png", (750, 400)), ("cover.png", (240, 240)), ("icon.png", (50, 50))]:
            self.image(self.root / name, size, 20)

    def image(self, path, size, index):
        img = Image.new("RGBA", size)
        ImageDraw.Draw(img).rectangle((5, 5, 20 + index, 20 + index), fill=(20 + index, 100, 180, 255))
        img.save(path, format="PNG")

    def check(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return module.validate(self.path)

    def test_valid_static(self):
        result = self.check()
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(len(result["files"]), 11)

    def test_valid_animated(self):
        self.data["mode"] = "animated"
        for index, item in enumerate(self.data["stickers"]):
            name = f"stickers/{index + 1:02}.gif"
            frames = []
            for offset in (0, 20):
                frame = Image.new("RGB", (240, 240), "white")
                ImageDraw.Draw(frame).rectangle((10 + offset, 10, 30 + index + offset, 30), fill="red")
                frames.append(frame)
            frames[0].save(self.root / name, save_all=True, append_images=frames[1:], duration=100, loop=0)
            item["file"] = name
        result = self.check()
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["files"][0]["frames"], 2)

    def test_wrong_size(self):
        self.image(self.root / "icon.png", (240, 240), 1)
        self.assertFalse(self.check()["valid"])

    def test_bad_count_and_empty_name(self):
        self.data.update(count=7, name=" ")
        self.assertGreaterEqual(len(self.check()["errors"]), 2)

    def test_outside_directory(self):
        self.data["stickers"][0]["file"] = "../outside.png"
        self.assertTrue(any("inside delivery" in x for x in self.check()["errors"]))

    def test_symlink_outside_directory(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "outside.png"
            self.image(target, (240, 240), 0)
            (self.root / "linked.png").symlink_to(target)
            self.data["stickers"][0]["file"] = "linked.png"
            self.assertFalse(self.check()["valid"])

    def test_duplicate_stickers(self):
        (self.root / "stickers/02.png").write_bytes((self.root / "stickers/01.png").read_bytes())
        self.assertTrue(any("duplicates sticker" in x for x in self.check()["errors"]))

    def test_fake_gif(self):
        target = self.root / "stickers/01.gif"
        target.write_bytes((self.root / "stickers/01.png").read_bytes())
        self.data["mode"] = "animated"
        self.data["stickers"][0]["file"] = "stickers/01.gif"
        result = self.check()
        self.assertTrue(any("extension" in x for x in result["errors"]))
        self.assertTrue(any("multi-frame GIF" in x for x in result["errors"]))

    def test_single_frame_gif(self):
        Image.new("RGB", (240, 240), "white").save(self.root / "stickers/01.gif")
        self.data["mode"] = "animated"
        self.data["stickers"][0]["file"] = "stickers/01.gif"
        self.assertTrue(any("multi-frame GIF" in x for x in self.check()["errors"]))

    def test_animated_without_loop(self):
        frames = [Image.new("RGB", (240, 240), color) for color in ("red", "blue")]
        frames[0].save(self.root / "stickers/01.gif", save_all=True, append_images=frames[1:], duration=100)
        self.data["mode"] = "animated"
        self.data["stickers"][0]["file"] = "stickers/01.gif"
        self.assertTrue(any("loop indefinitely" in x for x in self.check()["errors"]))

    def test_fully_transparent_sticker(self):
        Image.new("RGBA", (240, 240)).save(self.root / "stickers/01.png")
        self.assertTrue(any("fully transparent" in x for x in self.check()["errors"]))

    def test_missing_asset(self):
        self.data["cover"] = "missing.png"
        self.assertTrue(any("file not found" in x for x in self.check()["errors"]))

    def test_large_file(self):
        with (self.root / "cover.png").open("ab") as handle:
            handle.write(b"x" * 500_000)
        self.assertTrue(any("exceeds" in x for x in self.check()["errors"]))

    def test_corrupt_image(self):
        (self.root / "icon.png").write_bytes(b"broken image")
        self.assertFalse(self.check()["valid"])

    def test_invalid_manifest(self):
        self.path.write_text("[]", encoding="utf-8")
        self.assertFalse(module.validate(self.path)["valid"])

    def test_cli_preserves_existing_report(self):
        self.check()
        report = self.root / "report.json"
        report.write_text("keep", encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.path), "--report", str(report)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(report.read_text(), "keep")

    def test_cli_report(self):
        self.check()
        report = self.root / "report.json"
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.path), "--report", str(report)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(report.read_text())["valid"])


if __name__ == "__main__":
    unittest.main()
