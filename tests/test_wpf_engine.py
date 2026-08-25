from __future__ import annotations

import unittest

from PIL import Image

from nba2k_jersey_modder.modern.font_catalog import build_number_preview
from tools import wpf_engine


class WpfEngineTests(unittest.TestCase):
    def test_ping_and_template_catalog(self) -> None:
        self.assertEqual({"version": 1}, wpf_engine.METHODS["ping"]({}))
        catalog = wpf_engine.template_catalog({})
        self.assertIn("Retro U", catalog["Jersey"])
        self.assertIn("Jersey UV", catalog["Jersey"]["Retro U"])
        self.assertIn("Shorts normal", catalog["Shorts"]["Retro shorts"])

    def test_default_project_renders_at_game_texture_size(self) -> None:
        result = wpf_engine.render({"project": {}, "kind": "preview"})
        self.assertEqual(2048, result["width"])
        self.assertEqual(2048, result["height"])

    def test_number_cache_preview_uses_readable_five_by_two_layout(self) -> None:
        sheet = Image.new("RGBA", (1000, 100), (0, 0, 0, 0))
        for digit in range(10):
            color = (digit * 20, 10, 200, 255)
            for x in range(digit * 100, (digit + 1) * 100):
                for y in range(100):
                    sheet.putpixel((x, y), color)
        preview = build_number_preview(sheet)
        self.assertEqual((1280, 512), preview.size)
        self.assertEqual((0, 10, 200, 255), preview.getpixel((128, 128)))
        self.assertEqual((100, 10, 200, 255), preview.getpixel((128, 384)))


if __name__ == "__main__":
    unittest.main()
