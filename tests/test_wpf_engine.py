from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
