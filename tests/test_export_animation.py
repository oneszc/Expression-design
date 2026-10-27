import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_animation.py"
spec = importlib.util.spec_from_file_location("export_animation", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExportAnimationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sequence = self.root / "sequence.json"
        self.data = {"stage": "draft", "frames": []}
        for i, duration in enumerate((100, 300, 200)):
            frame = Image.new("RGBA", (240, 240))
            draw = ImageDraw.Draw(frame)
            draw.rectangle((20, 190, 220, 210), fill="black")
            draw.rectangle((30 + i * 20, 60, 60 + i * 20, 100), fill="orange")
            frame.save(self.root / f"{i}.png")
            self.data["frames"].append({"file": f"{i}.png", "duration_ms": duration})

    def run_export(self):
        self.sequence.write_text(json.dumps(self.data), encoding="utf-8")
        return module.export(self.sequence, self.root / "output")

    def test_timing_and_transparent_disposal(self):
        report = self.run_export()
        self.assertTrue(report["size_passed"])
        self.assertEqual(report["encoded_durations_ms"], [100, 300, 200])
        with Image.open(self.root / "output/animation.gif") as gif:
            self.assertEqual(gif.info["loop"], 0)
            for i in range(3):
                gif.seek(i)
                frame = gif.convert("RGBA")
                self.assertEqual(frame.getpixel((0, 0))[3], 0)
                self.assertEqual(frame.getpixel((50, 200)), (0, 0, 0, 255))
                self.assertEqual(frame.getpixel((35 + i * 20, 70))[3], 255)
            gif.seek(2)
            self.assertEqual(gif.convert("RGBA").getpixel((35, 70))[3], 0)

    def test_duplicate_holds_merge_without_time_loss(self):
        self.data["frames"].insert(1, {"file": "0.png", "duration_ms": 250})
        result = self.run_export()
        self.assertEqual(result["input_entries"], 4)
        self.assertEqual(result["encoded_frames"], 3)
        self.assertEqual(result["encoded_durations_ms"], [350, 300, 200])

    def test_fixed_region_and_intentional_movement(self):
        self.data["stable_regions"] = [{"name": "desk", "rect": [20, 190, 200, 20]}]
        result = self.run_export()
        self.assertEqual(result["stable_regions"][0]["flagged_frames"], [])

    def test_changed_fixed_region(self):
        self.data["stable_regions"] = [{"name": "subject", "rect": [20, 50, 120, 60]}]
        result = self.run_export()
        self.assertEqual(result["stable_regions"][0]["flagged_frames"], [1, 2])
        self.assertTrue(result["visual_review_required"])

    def test_no_regions_does_not_claim_stability(self):
        result = self.run_export()
        self.assertEqual(result["stable_regions"], [])
        self.assertTrue(any("No fixed regions" in msg for msg in result["warnings"]))

    def test_hidden_rgb_not_reported_as_drift(self):
        for i in range(3):
            path = self.root / f"{i}.png"
            with Image.open(path) as image:
                frame = image.convert("RGBA")
            ImageDraw.Draw(frame).rectangle((0, 0, 15, 15), fill=(i * 100, 255, 255, 0))
            frame.save(path)
        self.data["stable_regions"] = [{"name": "empty", "rect": [0, 0, 15, 15]}]
        result = self.run_export()
        self.assertEqual(result["stable_regions"][0]["max_difference"], 0)

    def test_mismatched_canvas_rejected(self):
        Image.new("RGBA", (200, 240), "red").save(self.root / "1.png")
        with self.assertRaisesRegex(ValueError, "canvas size"):
            self.run_export()
        self.assertFalse((self.root / "output").exists())

    def test_sheet_crops(self):
        sheet = Image.new("RGBA", (480, 240))
        sheet.paste(Image.open(self.root / "0.png"), (0, 0))
        sheet.paste(Image.open(self.root / "1.png"), (240, 0))
        sheet.save(self.root / "sheet.png")
        self.data["frames"] = [
            {"file": "sheet.png", "crop": [0, 0, 240, 240], "duration_ms": 150},
            {"file": "sheet.png", "crop": [240, 0, 240, 240], "duration_ms": 450},
        ]
        self.assertEqual(self.run_export()["encoded_durations_ms"], [150, 450])

    def test_invalid_crop(self):
        self.data["frames"][0]["crop"] = [230, 0, 240, 240]
        with self.assertRaisesRegex(ValueError, "outside"):
            self.run_export()

    def test_non_square_canvas_is_letterboxed(self):
        for i in range(3):
            Image.new("RGBA", (480, 240), (20 + i * 60, 90, 0, 255)).save(self.root / f"{i}.png")
        self.run_export()
        with Image.open(self.root / "output/animation.gif") as gif:
            self.assertEqual(gif.size, (240, 240))
            frame = gif.convert("RGBA")
            self.assertEqual(frame.getpixel((120, 10))[3], 0)
            self.assertEqual(frame.getpixel((120, 120))[3], 255)

    def test_invalid_time_rejected_without_rounding(self):
        self.data["frames"][0]["duration_ms"] = 135
        with self.assertRaisesRegex(ValueError, "multiples of 10"):
            self.run_export()

    def test_existing_directory_preserved(self):
        folder = self.root / "output"
        folder.mkdir()
        (folder / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.run_export()
        self.assertEqual((folder / "keep.txt").read_text(), "keep")

    def test_static_sequence_rejected(self):
        for entry in self.data["frames"]:
            entry["file"] = "0.png"
        with self.assertRaisesRegex(ValueError, "no visible changes"):
            self.run_export()

    def test_oversize_reports_failure_without_changing_timing(self):
        old_limit = module.LIMIT
        module.LIMIT = 1
        try:
            result = self.run_export()
        finally:
            module.LIMIT = old_limit
        self.assertFalse(result["size_passed"])
        self.assertEqual(result["duration_ms"], 600)
        self.assertEqual(len(result["palette_attempts"]), 4)


if __name__ == "__main__":
    unittest.main()
