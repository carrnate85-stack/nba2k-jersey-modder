from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from nba2k_jersey_modder.modern.document import ProjectDocument
from nba2k_jersey_modder.modern.font_catalog import describe_manifest_font
from nba2k_jersey_modder.modern.services import GeneratorService
from nba2k_jersey_modder.game_manifest import ManifestEntry


class ModernProjectDocumentTests(unittest.TestCase):
    def test_new_project_uses_visible_jersey_defaults(self) -> None:
        document = ProjectDocument()
        self.assertEqual(document.garment, "Jersey")
        self.assertEqual(document.template_name, "Retro U")
        self.assertEqual(document.generator["colors"]["front_color"], "#ffffff")
        self.assertEqual(document.generator["colors"]["left_panel_color"], "")
        self.assertEqual(document.generator["colors"]["shorts_left_panel_color"], "")
        self.assertTrue(document.generator["uvOverlay"]["enabled"])
        self.assertEqual(document.generator["uvOverlay"]["color"], "black")
        self.assertIsNone(document.generator["trimPathPattern"])
        self.assertEqual(document.generator["trimPathDesigns"], [])

    def test_version_one_project_is_normalized_without_losing_design_data(self) -> None:
        document = ProjectDocument({
            "projectVersion": 1,
            "generator": {
                "garment": "Jersey",
                "colors": {"front_color": "#112233"},
                "images": {},
            },
        })
        self.assertEqual(document.generator["colors"]["front_color"], "#112233")
        self.assertIn("back_color", document.generator["colors"])
        self.assertIn("uvOverlay", document.generator)
        self.assertEqual(document.generator["uvOverlay"]["color"], "black")
        self.assertEqual(document.payload["projectVersion"], 3)

    def test_shorts_inputs_use_dedicated_panel_images(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            jersey_panel = Path(folder) / "jersey.png"
            shorts_panel = Path(folder) / "shorts.png"
            Image.new("RGBA", (2, 2), "red").save(jersey_panel)
            Image.new("RGBA", (2, 2), "blue").save(shorts_panel)
            document = ProjectDocument()
            document.generator["garment"] = "Shorts"
            document.generator["images"]["left_panel_image"] = str(jersey_panel)
            document.generator["images"]["shorts_left_panel_image"] = str(shorts_panel)
            document.generator["colors"]["left_panel_color"] = "#112233"
            document.generator["colors"]["shorts_left_panel_color"] = "#445566"
            inputs = document.to_generator_inputs()
            self.assertEqual(inputs.left_panel_image, shorts_panel)
            self.assertEqual(inputs.left_panel_color, "#445566")

    def test_legacy_shared_panel_colors_are_copied_then_independent(self) -> None:
        document = ProjectDocument({
            "generator": {
                "garment": "Shorts",
                "colors": {"left_panel_color": "#123456", "right_panel_color": "#654321"},
                "images": {},
            },
        })
        colors = document.generator["colors"]
        self.assertEqual(colors["shorts_left_panel_color"], "#123456")
        self.assertEqual(colors["shorts_right_panel_color"], "#654321")
        colors["shorts_left_panel_color"] = "#abcdef"
        self.assertEqual(colors["left_panel_color"], "#123456")
        self.assertEqual(document.to_generator_inputs().left_panel_color, "#abcdef")

    def test_preview_can_tint_uv_lines_black_or_white(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            uv_path = Path(folder) / "uv.png"
            overlay = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
            overlay.putpixel((0, 0), (0, 0, 0, 255))
            overlay.save(uv_path)
            service = GeneratorService()
            service.render_color = lambda _document: Image.new("RGB", (2, 1), (50, 80, 110))
            service.uv_path = lambda _document: uv_path
            document = ProjectDocument()
            document.generator["uvOverlay"].update(enabled=True, opacity=100, color="white")
            white = service.render_preview(document)
            self.assertEqual(white.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(white.getpixel((1, 0)), (50, 80, 110))

            document.generator["uvOverlay"]["color"] = "black"
            black = service.render_preview(document)
            self.assertEqual(black.getpixel((0, 0)), (0, 0, 0))

    def test_manifest_font_description_adds_team_and_uniform_search_terms(self) -> None:
        entry = ManifestEntry(
            "clothing/clothing_resource_u006lac_current_city_font.iff",
            "0A", 0, 100,
        )
        self.assertEqual(
            describe_manifest_font(entry),
            ("LA Clippers", "Current City", "LAC"),
        )


if __name__ == "__main__":
    unittest.main()
