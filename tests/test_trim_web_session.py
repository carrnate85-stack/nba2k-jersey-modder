from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from nba2k_jersey_modder.trim_web_session import TrimWebSession


class TrimWebSessionTests(unittest.TestCase):
    def test_imports_finished_trim_without_reextracting_from_mockup(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference = folder / "mockup.png"
            imported = folder / "finished_trim.png"
            Image.new("RGB", (20, 20), "white").save(reference)
            trim = Image.new("RGBA", (320, 30), (0, 0, 0, 0))
            draw = ImageDraw.Draw(trim)
            draw.rectangle((0, 5, 319, 24), fill="#d1123f")
            trim.save(imported)

            session = TrimWebSession(reference, folder / "state.json")
            self.assertIn(
                {"label": "Trim Path", "target": "trim_path_pattern"},
                session.project()["trimTypes"],
            )
            project = session.import_image({
                "path": str(imported),
                "target": "waistband_image",
            })
            item = project["items"][0]
            self.assertEqual("Waistband", item["typeLabel"])
            self.assertTrue(item["imported"])
            self.assertFalse(item["correct"])
            with Image.open(item["path"]) as output:
                self.assertEqual((320, 30), output.size)

            updated = session.update({
                "id": item["id"],
                "target": "collar_trim_image",
                "cropTop": 2,
                "cropBottom": 3,
                "scale": 1,
            })
            changed = updated["items"][0]
            self.assertEqual("Collar Trim", changed["typeLabel"])
            with Image.open(changed["path"]) as output:
                self.assertEqual((320, 25), output.size)

    def test_stages_multiple_lines_and_reprocesses_trim_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference = folder / "mockup.png"
            image = Image.new("RGB", (140, 100), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 20, 139, 29), fill="#d1123f")
            draw.rectangle((0, 30, 139, 39), fill="#ffffff")
            draw.rectangle((0, 40, 139, 55), fill="#103978")
            image.save(reference)

            state = folder / "state.json"
            session = TrimWebSession(reference, state)
            first = session.stage({
                "start": {"x": 70, "y": 18}, "end": {"x": 70, "y": 58},
                "target": "collar_trim_image",
            })
            second = session.stage({
                "start": {"x": 30, "y": 18}, "end": {"x": 30, "y": 58},
                "target": "waistband_image",
            })
            self.assertEqual(2, len(second["items"]))
            self.assertEqual("Collar Trim", first["items"][0]["typeLabel"])

            selected_id = second["selectedId"]
            updated = session.update({
                "id": selected_id, "target": "left_arm_hole_trim_image",
                "cropTop": -4, "cropBottom": 3, "correct": True,
                "sharpen": True, "colorCorrect": True, "scale": 2,
            })
            item = next(value for value in updated["items"] if value["id"] == selected_id)
            self.assertEqual("Left Arm Hole Trim", item["typeLabel"])
            self.assertEqual(-4, item["cropTop"])
            self.assertTrue(Path(item["path"]).exists())
            self.assertTrue(Path(item["thumbnailPath"]).exists())
            with Image.open(item["path"]) as output:
                self.assertGreater(output.width, 1024)

            self.assertEqual(2, session.request_return()["items"])
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertTrue(saved["returnRequested"])

    def test_restores_trim_and_feathers_each_requested_edge(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference = folder / "mockup.png"
            imported = folder / "trim.png"
            Image.new("RGB", (40, 40), "white").save(reference)
            trim = Image.new("RGBA", (120, 24), (190, 25, 55, 255))
            ImageDraw.Draw(trim).rectangle((0, 12, 119, 23), fill=(20, 70, 150, 255))
            trim.save(imported)
            first = TrimWebSession(reference, folder / "first" / "state.json")
            staged = first.import_image({"path": str(imported), "target": "waistband_image"})
            restored_session = TrimWebSession(
                reference,
                folder / "second" / "state.json",
                {"items": staged["items"], "selectedId": staged["selectedId"]},
            )

            updated = restored_session.update({
                "id": staged["selectedId"],
                "featherLeft": 8, "featherRight": 8,
                "featherTop": 4, "featherBottom": 4,
                "flipVertical": True,
            })
            item = updated["items"][0]
            self.assertTrue(item["flipVertical"])
            with Image.open(item["path"]) as output:
                rgba = output.convert("RGBA")
                alpha = rgba.getchannel("A")
                self.assertEqual(0, alpha.getpixel((0, output.height // 2)))
                self.assertEqual(0, alpha.getpixel((output.width - 1, output.height // 2)))
                self.assertEqual(0, alpha.getpixel((output.width // 2, 0)))
                self.assertEqual(0, alpha.getpixel((output.width // 2, output.height - 1)))
                self.assertEqual(255, alpha.getpixel((output.width // 2, output.height // 2)))
                self.assertEqual((20, 70, 150), rgba.getpixel((output.width // 2, 6))[:3])
                self.assertEqual((190, 25, 55), rgba.getpixel((output.width // 2, 18))[:3])

    def test_live_preview_skips_upscale_then_return_finalizes_full_quality(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference = folder / "mockup.png"
            imported = folder / "trim.png"
            Image.new("RGB", (40, 40), "white").save(reference)
            Image.new("RGBA", (200, 30), (30, 80, 170, 255)).save(imported)
            session = TrimWebSession(reference, folder / "state.json")
            staged = session.import_image({"path": str(imported), "target": "waistband_image"})
            item_id = staged["selectedId"]

            previewed = session.update({"id": item_id, "scale": 4, "previewOnly": True})
            final_path = Path(previewed["items"][0]["path"])
            with Image.open(BytesIO(session.preview_bytes(item_id)[0])) as preview:
                self.assertEqual((200, 30), preview.size)
            with Image.open(final_path) as unchanged_final:
                self.assertEqual((200, 30), unchanged_final.size)

            session.request_return()
            with Image.open(final_path) as finalized:
                self.assertEqual((800, 120), finalized.size)


if __name__ == "__main__":
    unittest.main()
