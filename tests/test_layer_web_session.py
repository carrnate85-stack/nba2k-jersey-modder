from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from nba2k_jersey_modder.layer_web_session import LayerWebSession
from nba2k_jersey_modder.modern.document import ProjectDocument


class LayerWebSessionTests(unittest.TestCase):
    def test_paint_bucket_updates_and_undoes_template_base_color(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            project_path = folder / "project.json"
            document = ProjectDocument()
            document.save(project_path)
            session = LayerWebSession(project_path, folder / "state.json")
            template = session.service.template(session.document)
            zone = next(item for item in template.zones if item.name == "front_jersey_base")
            design_width = max(2048, max(item.x + item.width for item in template.zones))
            design_height = max(2048, max(item.y + item.height for item in template.zones))

            result = session._web_editor_paint({
                "key": "base_colors",
                "x": (zone.x + zone.width / 2) / design_width,
                "y": (zone.y + zone.height / 2) / design_height,
                "color": "#123456",
            })
            self.assertTrue(result["changed"])
            self.assertEqual(session.document.generator["colors"]["front_color"], "#123456")
            self.assertTrue(session._web_editor_project()["canUndoBasePaint"])

            undo = session._web_editor_undo_paint({"key": "base_colors"})
            self.assertTrue(undo["ok"])
            self.assertEqual(session.document.generator["colors"]["front_color"], "#ffffff")

    def test_paint_bucket_recolors_and_undoes_a_logo_layer(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            logo = folder / "logo.png"
            Image.new("RGBA", (12, 8), (10, 180, 170, 255)).save(logo)
            project_path = folder / "project.json"
            document = ProjectDocument()
            document.generator["logos"] = [{
                "path": str(logo), "targetName": "front_center_chest_logo",
                "offsetX": 0, "offsetY": 0, "scalePercent": 100,
                "scaleWidthPercent": 100, "scaleHeightPercent": 100,
            }]
            document.save(project_path)

            session = LayerWebSession(project_path, folder / "state.json")
            before = next(
                item for item in session._web_editor_project()["overlays"] if item["key"] == "logo:0"
            )
            self.assertTrue(before["canPaint"])
            self.assertFalse(before["canUndoPaint"])

            result = session._web_editor_paint({
                "key": "logo:0", "x": 0.5, "y": 0.5,
                "color": "#ff00aa", "tolerance": 0,
            })
            self.assertTrue(result["changed"])
            painted_path = Path(session.document.generator["logos"][0]["path"])
            self.assertNotEqual(painted_path, logo)
            with Image.open(painted_path) as painted:
                self.assertEqual(painted.convert("RGBA").getpixel((6, 4)), (255, 0, 170, 255))
            after = next(
                item for item in session._web_editor_project()["overlays"] if item["key"] == "logo:0"
            )
            self.assertTrue(after["canUndoPaint"])

            undo = session._web_editor_undo_paint({"key": "logo:0"})
            self.assertTrue(undo["ok"])
            self.assertEqual(Path(session.document.generator["logos"][0]["path"]), logo)

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
            self.assertTrue(overlay["canLockAspect"])
            self.assertTrue(overlay["lockAspect"])
            session._web_editor_update({
                "key": "logo:0", "x": overlay["x"] + 12, "y": overlay["y"] + 7,
                "width": overlay["width"], "height": overlay["height"], "rotation": 0,
                "lockAspect": False,
            })
            session._web_editor_return()

            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["project"]["generator"]["logos"][0]["offsetX"], 12)
            self.assertEqual(state["project"]["generator"]["logos"][0]["offsetY"], 7)
            self.assertFalse(state["project"]["generator"]["logos"][0]["lockAspect"])
            self.assertTrue(state["returnRequested"])

            ProjectDocument(state["project"]).save(project_path)
            reopened = LayerWebSession(project_path, folder / "reopened-state.json")
            reopened_overlay = next(
                item for item in reopened._web_editor_project()["overlays"] if item["key"] == "logo:0"
            )
            self.assertFalse(reopened_overlay["lockAspect"])


if __name__ == "__main__":
    unittest.main()
