from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from nba2k_jersey_modder.logo_web_session import LogoWebSession


class LogoWebSessionTests(unittest.TestCase):
    def test_imports_finished_logo_as_editable_staged_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference = folder / "reference.png"
            imported = folder / "finished_logo.png"
            Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(reference)
            Image.new("RGBA", (96, 48), (18, 60, 140, 255)).save(imported)

            session = LogoWebSession(reference, folder / "state.json")
            project = session.import_image({
                "path": str(imported),
                "target": "front_center_chest_logo",
            })
            item = project["items"][0]
            self.assertEqual("Center Chest Logo", item["typeLabel"])
            self.assertEqual(str(imported.resolve()), item["sourcePath"])
            with Image.open(item["path"]) as output:
                self.assertEqual((96, 48), output.size)

            updated = session.update({
                "id": item["id"],
                "target": "back_neck_logo",
                "scale": 2,
            })
            changed = updated["items"][0]
            self.assertEqual("Back Neck Logo", changed["typeLabel"])
            with Image.open(changed["path"]) as output:
                self.assertEqual((192, 96), output.size)

    def test_stages_multiple_logos_and_reprocesses_selected_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            reference = folder / "reference.png"
            image = Image.new("RGB", (120, 80), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 45, 55), fill="#cc1234")
            draw.rectangle((70, 15, 108, 60), fill="#123c8c")
            image.save(reference)

            state = folder / "state.json"
            session = LogoWebSession(reference, state)
            first = session.stage({
                "points": self._box(5, 5, 50, 60),
                "target": "front_wordmark",
            })
            second = session.stage({
                "points": self._box(65, 10, 112, 65),
                "target": "front_left_chest_logo",
            })

            self.assertEqual(2, len(second["items"]))
            self.assertEqual("front_wordmark", first["items"][0]["target"])
            selected_id = second["selectedId"]
            updated = session.update({
                "id": selected_id,
                "target": "front_center_chest_logo",
                "removeWhite": True,
                "outsideOnly": True,
                "tolerance": 24,
                "scale": 2,
            })
            selected = next(item for item in updated["items"] if item["id"] == selected_id)
            self.assertEqual("Center Chest Logo", selected["typeLabel"])
            self.assertTrue(selected["removeWhite"])
            self.assertTrue(Path(selected["thumbnailPath"]).exists())
            with Image.open(selected["path"]) as output:
                self.assertGreater(output.width, 80)
                self.assertEqual(0, output.convert("RGBA").getpixel((0, 0))[3])

            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(2, len(saved["items"]))
            self.assertEqual(selected_id, saved["selectedId"])
            returned = session.request_return()
            self.assertEqual(2, returned["items"])
            self.assertTrue(json.loads(state.read_text(encoding="utf-8"))["returnRequested"])

    @staticmethod
    def _box(left: int, top: int, right: int, bottom: int):
        return [
            {"x": left, "y": top}, {"x": right, "y": top},
            {"x": right, "y": bottom}, {"x": left, "y": bottom},
        ]


if __name__ == "__main__":
    unittest.main()
