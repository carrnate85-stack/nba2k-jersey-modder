from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from nba2k_jersey_modder.logo_web_session import LogoWebSession


class LogoWebSessionTests(unittest.TestCase):
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
            with Image.open(selected["path"]) as output:
                self.assertGreater(output.width, 80)
                self.assertEqual(0, output.convert("RGBA").getpixel((0, 0))[3])

            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(2, len(saved["items"]))
            self.assertEqual(selected_id, saved["selectedId"])

    @staticmethod
    def _box(left: int, top: int, right: int, bottom: int):
        return [
            {"x": left, "y": top}, {"x": right, "y": top},
            {"x": right, "y": bottom}, {"x": left, "y": bottom},
        ]


if __name__ == "__main__":
    unittest.main()
