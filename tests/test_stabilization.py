import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from nba2k_jersey_modder.modern.document import ProjectDocument
from nba2k_jersey_modder.modern.services import GeneratorService
from tools import wpf_engine

class StabilizationTests(unittest.TestCase):
    def test_normal_texture_alias_uses_normal_renderer(self):
        with patch('nba2k_jersey_modder.modern.services.render_jersey_normal_map', return_value=Image.new('RGB', (2, 2))) as normal:
            GeneratorService().render_texture(ProjectDocument(), 'Normal Texture', 0)
            self.assertEqual(normal.call_args.kwargs['normal_strength'], 0)

    def test_zero_strength_survives_bridge(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wpf_engine, 'WORK', Path(directory)), patch.object(wpf_engine.SERVICE, 'render_texture', return_value=Image.new('RGB', (2, 2))) as render:
            wpf_engine.render({'kind': 'Normal Texture', 'strength': 0})
            self.assertEqual(render.call_args.args[2], 0)

    def test_future_project_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'newer'):
            ProjectDocument({'projectVersion': 999})

    def test_portable_asset_resolves_from_project_location(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            asset = folder / 'assets/logos/test.png'
            asset.parent.mkdir(parents=True)
            Image.new('RGBA', (2, 2), 'red').save(asset)
            payload = ProjectDocument().payload
            payload['generator']['images']['front_wordmark_image'] = 'assets/logos/test.png'
            file = folder / 'project.json'
            file.write_text(json.dumps(payload))
            self.assertEqual(ProjectDocument.load(file).to_generator_inputs().front_wordmark_image, asset)

    def test_invalid_hex_is_clear_error(self):
        with self.assertRaisesRegex(ValueError, 'six-digit'):
            wpf_engine._rgb('#12')
