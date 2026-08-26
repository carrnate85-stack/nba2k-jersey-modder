from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from nba2k_jersey_modder.modern.document import ProjectDocument
from nba2k_jersey_modder.trim_path_web_session import TrimPathWebSession


class TrimPathWebSessionTests(unittest.TestCase):
    def test_saves_scoped_cropped_layers_and_records_return(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            pattern = folder / "trim.png"
            Image.new("RGBA", (320, 48), (210, 20, 60, 255)).save(pattern)
            project_path = folder / "project.json"
            document = ProjectDocument()
            document.save(project_path)
            state_path = folder / "state.json"
            session = TrimPathWebSession(project_path, pattern, state_path, folder)

            project = session._trim_path_lab_web_project()
            self.assertEqual(project["garment"], "Jersey")
            self.assertEqual(project["templateName"], "Retro U")
            self.assertTrue(project["uvOverlay"]["available"])

            layer = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
            layer.paste((220, 25, 65, 255), (120, 240, 520, 300))
            stream = BytesIO()
            layer.save(stream, "PNG")
            encoded = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
            result = session._trim_path_lab_send_to_generator({
                "garment": "Jersey",
                "templateName": "Retro U",
                "layers": [{"name": "Waist Curve", "png": encoded}],
            })
            self.assertEqual(result, {"ok": True, "count": 1})

            state = json.loads(state_path.read_text(encoding="utf-8"))
            saved = state["project"]["generator"]["trimPathLayers"][0]
            self.assertEqual((saved["x"], saved["y"]), (120, 240))
            self.assertEqual((saved["width"], saved["height"]), (400, 60))
            self.assertTrue(Path(saved["path"]).is_file())
            self.assertEqual(Path(saved["path"]).parent, folder / "assets" / "trims" / "paths")

            session._trim_path_lab_return()
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(state["returnRequested"])


if __name__ == "__main__":
    unittest.main()
