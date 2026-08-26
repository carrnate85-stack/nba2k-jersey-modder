from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from nba2k_jersey_modder.trim_web_session import TrimWebSession


class TrimWebSessionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
