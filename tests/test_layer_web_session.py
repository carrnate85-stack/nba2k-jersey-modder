from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from nba2k_jersey_modder.layer_web_session import LayerWebSession
from nba2k_jersey_modder.modern.document import ProjectDocument


class LayerWebSessionTests(unittest.TestCase):
    def test_updates_logo_and_records_return_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            logo = folder / "logo.png"
            wordmark = folder / "wordmark.png"
            trim = folder / "trim.png"
            Image.new("RGBA", (120, 80), (10, 180, 170, 255)).save(logo)
            Image.new("RGBA", (300, 90), (220, 20, 60, 255)).save(wordmark)
            Image.new("RGBA", (400, 36), (18, 60, 140, 255)).save(trim)
            project_path = folder / "project.json"
            document = ProjectDocument()
            document.generator["images"]["front_wordmark_image"] = str(wordmark)
            document.generator["images"]["collar_trim_image"] = str(trim)
            document.generator["logos"] = [{
                "path": str(logo), "targetName": "front_center_chest_logo",
                "offsetX": 0, "offsetY": 0, "scalePercent": 100,
                "scaleWidthPercent": 100, "scaleHeightPercent": 100,
            }]
            document.save(project_path)

            state_path = folder / "state.json"
            session = LayerWebSession(project_path, state_path)
            project = session._web_editor_project()
            overlay_keys = {item["key"] for item in project["overlays"]}
            self.assertIn("front_wordmark", overlay_keys)
            self.assertIn("collar_trim", overlay_keys)
            self.assertIn("logo:0", overlay_keys)
            overlay = next(item for item in project["overlays"] if item["key"] == "logo:0")
            session._web_editor_update({
                "key": "logo:0", "x": overlay["x"] + 12, "y": overlay["y"] + 7,
                "width": overlay["width"], "height": overlay["height"], "rotation": 0,
            })
            session._web_editor_return()

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["project"]["generator"]["logos"][0]["offsetX"], 12)
            self.assertEqual(state["project"]["generator"]["logos"][0]["offsetY"], 7)
            self.assertTrue(state["returnRequested"])


if __name__ == "__main__":
    unittest.main()
