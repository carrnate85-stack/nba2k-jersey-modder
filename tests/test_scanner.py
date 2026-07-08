import tempfile
import unittest
from pathlib import Path
import struct
import zipfile

from nba2k_jersey_modder.app import (
    _fit_transparent_image_to_square,
    _align_image_to_visible_center,
    _loaded_number_digit_keys,
    _nudge_image,
    _place_image_visible_center,
    _recolor_font_image,
    _remove_sampled_color_background,
    _replace_trim_color,
    _trim_transparent_padding,
)
from nba2k_jersey_modder.dds import save_bc1_dds
from nba2k_jersey_modder.font_iff import (
    build_font_number_sheet,
    extract_number_sheet_from_font_iff,
    inspect_font_number_texture,
    split_number_sheet_digits,
    write_number_sheet_to_font_iff,
)
from nba2k_jersey_modder.iff_patch import Replacement, apply_replacements, can_replace_resource
from nba2k_jersey_modder.generator import (
    BackgroundCleanupSettings,
    GeneratorInputs,
    LogoPlacement,
    TrimPlacementSettings,
    generate_jersey_texture,
    generate_layered_jersey_psd,
    image_placement_rects,
    logo_target_zones,
    remove_detected_background,
    remove_image_background,
    render_jersey_normal_map,
    render_jersey_region_map,
    upscale_logo_image,
    _overlay_at_zone,
)
from nba2k_jersey_modder.scanner import ResourceHit
from nba2k_jersey_modder.scanner import scan_iff
from nba2k_jersey_modder.template import (
    JERSEY_NORMAL_TEMPLATE_IMAGE,
    JERSEY_REGION_TEMPLATE_IMAGE,
    JERSEY_REGION_TEMPLATE_ZONES,
    JERSEY_TEMPLATE_OPTIONS,
    JerseyTemplate,
    MASTER_TEMPLATE_IMAGE,
    MASTER_TEMPLATE_ZONES,
    SHORTS_TEMPLATE_RETRO_IMAGE,
    SHORTS_TEMPLATE_RETRO_ZONES,
    TemplateZone,
    detect_v1_color_zones,
    detect_v3_color_zones,
    find_hex_color_zone_bbox,
    load_template,
    save_template,
)
from nba2k_jersey_modder.trim_creator import (
    correct_trim_strip,
    create_trim_strip_from_line,
    create_trim_strips_from_mockup,
)
from nba2k_jersey_modder.tweak_iff import (
    FRONT_NUMBER_HASHES,
    inspect_front_number_tweak,
    write_front_number_tweak,
)


def _fake_tweak_scalar(hash_id: str, value: float, minimum: float, maximum: float) -> bytes:
    return struct.pack(
        "<I8sffffff",
        136,
        bytes.fromhex(hash_id),
        0.0,
        0.0,
        0.0,
        value,
        minimum,
        maximum,
    )


class ScannerTests(unittest.TestCase):
    def test_scan_pairs_dds_and_txtr_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "jersey.iff"
            sample.write_bytes(
                b"header\0"
                b"uniform_home.dds\0"
                b"payload\0"
                b"uniform_home.txtr\0"
                b"tail"
            )

            result = scan_iff(sample)
            sample_size = sample.stat().st_size

        self.assertEqual(result.size, sample_size)
        self.assertTrue(
            any(resource.name == "uniform_home.dds" for resource in result.resources)
        )
        self.assertTrue(
            any(resource.name == "uniform_home.txtr" for resource in result.resources)
        )
        self.assertEqual(len(result.texture_pairs), 1)
        self.assertEqual(result.texture_pairs[0].key, "uniform_home")
        self.assertEqual(result.texture_pairs[0].status, "Matched")

    def test_scan_detects_embedded_dds_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "jersey.iff"
            dds_header = bytearray(128)
            dds_header[0:4] = b"DDS "
            dds_header[4:8] = (124).to_bytes(4, "little")
            dds_header[12:16] = (16).to_bytes(4, "little")
            dds_header[16:20] = (16).to_bytes(4, "little")
            sample.write_bytes(b"chunk" + bytes(dds_header) + b"end")

            result = scan_iff(sample)

        dds_hits = [resource for resource in result.resources if resource.kind == "DDS"]
        self.assertEqual(len(dds_hits), 1)
        self.assertEqual(dds_hits[0].offset, 5)
        self.assertEqual(dds_hits[0].source, "DDS header")

    def test_named_dds_reference_uses_embedded_dds_header_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "jersey.iff"
            dds_header = bytearray(128)
            dds_header[0:4] = b"DDS "
            dds_header[4:8] = (124).to_bytes(4, "little")
            dds_header[12:16] = (16).to_bytes(4, "little")
            dds_header[16:20] = (16).to_bytes(4, "little")
            sample.write_bytes(
                b"uniform_home.dds\0"
                b"uniform_home.txtr\0"
                b"chunk"
                + bytes(dds_header)
            )

            result = scan_iff(sample)

        pair = result.texture_pairs[0]
        self.assertEqual(pair.key, "uniform_home")
        self.assertEqual(pair.dds_hits[0].name, "uniform_home.dds")
        self.assertEqual(pair.dds_hits[0].source, "DDS header matched to filename")
        self.assertIsNotNone(pair.dds_hits[0].size)

    def test_scan_detects_rdat_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "jersey.iff"
            sample.write_bytes(b"header\0appearance.rdat\0tail")

            result = scan_iff(sample)

        rdat_hits = [resource for resource in result.resources if resource.kind == "RDAT"]
        self.assertEqual(len(rdat_hits), 1)
        self.assertEqual(rdat_hits[0].name, "appearance.rdat")
        self.assertEqual(rdat_hits[0].source, "filename reference")

    def test_texture_pairs_show_each_filename_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "jersey.iff"
            sample.write_bytes(
                b"uniform_home.dds\0"
                b"uniform_home.txtr\0"
                b"uniform_home.dds\0"
                b"uniform_home.txtr\0"
            )

            result = scan_iff(sample)

        self.assertEqual(len(result.texture_pairs), 1)
        self.assertEqual(len(result.texture_pairs[0].dds_hits), 1)
        self.assertEqual(len(result.texture_pairs[0].txtr_hits), 1)

    def test_zip_style_iff_reads_internal_dds_and_txtr_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "jersey.iff"
            with zipfile.ZipFile(sample, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("jersey_color.8674543f2801b4e2.dds", b"DDS data")
                archive.writestr("jersey_color.TXTR", b"txtr data")
                archive.writestr("_home.RDAT", b"rdat data")

            result = scan_iff(sample)

        self.assertEqual(len(result.texture_pairs), 1)
        pair = result.texture_pairs[0]
        self.assertEqual(pair.key, "jersey_color")
        self.assertEqual(pair.dds_hits[0].name, "jersey_color.8674543f2801b4e2.dds")
        self.assertEqual(pair.txtr_hits[0].name, "jersey_color.TXTR")
        self.assertEqual(pair.dds_hits[0].source, "archive entry")
        self.assertTrue(can_replace_resource(pair.dds_hits[0]))


class IffPatchTests(unittest.TestCase):
    def test_apply_replacements_pads_smaller_dds_inside_original_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.iff"
            output = tmp_path / "output.iff"
            replacement = tmp_path / "replacement.dds"
            source.write_bytes(b"before" + b"DDS original-data" + b"after")
            replacement.write_bytes(b"DDS new")
            resource = ResourceHit(
                kind="DDS",
                offset=6,
                name="embedded.dds",
                size=len(b"DDS original-data"),
                source="DDS header",
            )

            apply_replacements(source, output, [Replacement(resource, replacement)])

            patched = output.read_bytes()

        self.assertEqual(len(patched), len(b"before" + b"DDS original-data" + b"after"))
        self.assertIn(b"DDS new", patched)
        self.assertTrue(patched.endswith(b"after"))

    def test_apply_replacements_rewrites_zip_style_iff_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source.iff"
            output = tmp_path / "output.iff"
            replacement = tmp_path / "replacement.dds"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("jersey_color.12345678.dds", b"DDS old")
                archive.writestr("jersey_color.TXTR", b"txtr data")
            replacement.write_bytes(b"DDS new archive")
            result = scan_iff(source)
            resource = result.texture_pairs[0].dds_hits[0]

            apply_replacements(source, output, [Replacement(resource, replacement)])

            with zipfile.ZipFile(output, "r") as archive:
                patched_dds = archive.read("jersey_color.12345678.dds")
                txtr = archive.read("jersey_color.TXTR")

        self.assertEqual(patched_dds, b"DDS new archive")
        self.assertEqual(txtr, b"txtr data")


class TweakIffTests(unittest.TestCase):
    def test_inspect_and_write_front_number_controls_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "source_tweak.iff"
            output = tmp_path / "output_tweak.iff"
            tweak_data = (
                _fake_tweak_scalar(FRONT_NUMBER_HASHES["x"], -0.16, -10.0, 10.0)
                + _fake_tweak_scalar(FRONT_NUMBER_HASHES["width"], 4.4, 0.001, 40.0)
                + _fake_tweak_scalar(FRONT_NUMBER_HASHES["y"], -0.12, -10.0, 10.0)
                + _fake_tweak_scalar(FRONT_NUMBER_HASHES["height"], 7.3, 0.001, 40.0)
            )
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("unitweak.FxTweakables", tweak_data)
                archive.writestr("keep.bin", b"unchanged")

            info = inspect_front_number_tweak(source)
            self.assertAlmostEqual(info.x.value, -0.16, places=5)
            self.assertAlmostEqual(info.width.value, 4.4, places=5)

            write_front_number_tweak(
                source,
                output,
                x=-0.33,
                y=-0.09,
                width=5.5,
                height=11.0,
            )
            patched = inspect_front_number_tweak(output)

            self.assertAlmostEqual(patched.x.value, -0.33, places=5)
            self.assertAlmostEqual(patched.y.value, -0.09, places=5)
            self.assertAlmostEqual(patched.width.value, 5.5, places=5)
            self.assertAlmostEqual(patched.height.value, 11.0, places=5)
            with zipfile.ZipFile(output, "r") as archive:
                self.assertEqual(archive.read("keep.bin"), b"unchanged")


class TemplateTests(unittest.TestCase):
    def test_save_and_load_template_zones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "template.json"
            template = JerseyTemplate(
                image_path="jersey_template.png",
                zones=(
                    TemplateZone(
                        name="front_wordmark",
                        zone_type="wordmark",
                        x=100,
                        y=200,
                        width=300,
                        height=80,
                        color="#ff3366",
                    ),
                ),
            )

            save_template(path, template)
            loaded = load_template(path)

        self.assertEqual(loaded.image_path, "jersey_template.png")
        self.assertEqual(loaded.zones[0].name, "front_wordmark")
        self.assertEqual(loaded.zones[0].width, 300)

    def test_detect_v1_color_zones(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "template.png"
            image = Image.new("RGB", (120, 120), (239, 240, 239))
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 30, 50), fill=(24, 32, 201))
            draw.rectangle((40, 10, 80, 30), fill=(0, 0, 0))
            image.save(path)

            zones = detect_v1_color_zones(path)

        by_name = {zone.name: zone for zone in zones}
        self.assertEqual(by_name["left_side_panel"].x, 10)
        self.assertEqual(by_name["left_side_panel"].width, 21)
        self.assertEqual(by_name["front_wordmark"].height, 21)

    def test_find_hex_color_zone_bbox_detects_custom_zone(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "template.png"
            image = Image.new("RGB", (80, 70), (240, 240, 240))
            draw = ImageDraw.Draw(image)
            draw.rectangle((12, 15, 30, 44), fill=(255, 51, 102))
            image.save(path)

            bbox = find_hex_color_zone_bbox(path, "#ff3366")

        self.assertEqual(bbox, (12, 15, 19, 30))

    def test_detect_v3_color_zones_splits_back_components(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "template3.png"
            image = Image.new("RGB", (320, 320), (239, 173, 30))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 80, 99, 319), fill=(5, 240, 255))
            draw.rectangle((220, 80, 319, 319), fill=(5, 240, 255))
            draw.rectangle((100, 80, 219, 319), fill=(5, 255, 5))
            draw.rectangle((130, 130, 190, 170), fill=(0, 0, 0))
            image.save(path)

            zones = detect_v3_color_zones(path)

        by_name = {zone.name: zone for zone in zones}
        self.assertEqual(by_name["front_jersey_base"].x, 100)
        self.assertIn("back_jersey_base_left", by_name)
        self.assertIn("back_jersey_base_right", by_name)
        self.assertEqual(by_name["front_wordmark"].zone_type, "wordmark")

    def test_bundled_master_template_exists_and_loads(self) -> None:
        self.assertTrue(MASTER_TEMPLATE_IMAGE.exists())
        self.assertTrue(MASTER_TEMPLATE_ZONES.exists())

        template = load_template(MASTER_TEMPLATE_ZONES)
        by_name = {zone.name: zone for zone in template.zones}

        self.assertIn("front_jersey_base", by_name)
        self.assertIn("back_jersey_base_left", by_name)
        self.assertIn("back_jersey_base_right", by_name)
        self.assertIn("left_side_panel", by_name)
        self.assertIn("right_side_panel", by_name)
        self.assertGreater(by_name["left_side_panel"].layer, by_name["front_jersey_base"].layer)

    def test_bundled_region_template_exists_and_loads(self) -> None:
        self.assertTrue(JERSEY_REGION_TEMPLATE_IMAGE.exists())
        self.assertTrue(JERSEY_REGION_TEMPLATE_ZONES.exists())
        self.assertIn("Jersey region", JERSEY_TEMPLATE_OPTIONS)

        template = load_template(JERSEY_REGION_TEMPLATE_ZONES)
        by_name = {zone.name: zone for zone in template.zones}

        self.assertIn("jersey_region_main_cloth", by_name)
        self.assertIn("jersey_region_dark_band", by_name)

    def test_bundled_normal_template_is_available_for_jerseys(self) -> None:
        self.assertTrue(JERSEY_NORMAL_TEMPLATE_IMAGE.exists())
        self.assertIn("Jersey normal", JERSEY_TEMPLATE_OPTIONS)
        image_path, zones_path = JERSEY_TEMPLATE_OPTIONS["Jersey normal"]

        self.assertEqual(image_path, JERSEY_NORMAL_TEMPLATE_IMAGE)
        self.assertEqual(zones_path, MASTER_TEMPLATE_ZONES)

    def test_bundled_retro_shorts_template_exists_and_loads(self) -> None:
        self.assertTrue(SHORTS_TEMPLATE_RETRO_IMAGE.exists())
        self.assertTrue(SHORTS_TEMPLATE_RETRO_ZONES.exists())

        template = load_template(SHORTS_TEMPLATE_RETRO_ZONES)
        by_name = {zone.name: zone for zone in template.zones}

        self.assertTrue(any(name.startswith("shorts_waistband") for name in by_name))
        self.assertIn("shorts_left_panel", by_name)
        self.assertIn("shorts_right_panel", by_name)
        self.assertIn("shorts_belt_buckle_logo", by_name)


class TrimCreatorTests(unittest.TestCase):
    def test_create_trim_strips_from_mockup_detects_three_trim_areas(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mockup = tmp_path / "mockup.png"
            output_dir = tmp_path / "strips"
            image = Image.new("RGB", (240, 240), (235, 235, 235))
            draw = ImageDraw.Draw(image)
            draw.polygon(
                ((70, 45), (170, 45), (210, 220), (30, 220)),
                fill=(245, 245, 245),
            )
            draw.rectangle((100, 48, 140, 60), fill=(200, 20, 40))
            draw.rectangle((55, 80, 68, 170), fill=(20, 120, 220))
            draw.rectangle((172, 80, 185, 170), fill=(20, 180, 70))
            image.save(mockup)

            results = create_trim_strips_from_mockup(mockup, output_dir, strip_size=(128, 16))
            names = {result.name for result in results}
            output_paths_exist = [result.output_path.exists() for result in results]
            by_name = {result.name: result for result in results}
            with Image.open(by_name["left_arm_hole_trim"].output_path).convert("RGBA") as left_strip:
                left_edge = left_strip.getpixel((0, 8))
                left_far_edge = left_strip.getpixel((127, 8))
            with Image.open(by_name["collar_trim"].output_path).convert("RGBA") as collar_strip:
                collar_far_edge = collar_strip.getpixel((127, 8))

        self.assertIn("collar_trim", names)
        self.assertIn("left_arm_hole_trim", names)
        self.assertIn("right_arm_hole_trim", names)
        self.assertTrue(all(output_paths_exist))
        self.assertEqual(left_edge[:3], (20, 120, 220))
        self.assertEqual(left_far_edge[:3], (20, 120, 220))
        self.assertEqual(collar_far_edge[:3], (200, 20, 40))

    def test_circular_collar_trim_unwraps_to_straight_color_bands(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mockup = tmp_path / "curved_collar.png"
            output_dir = tmp_path / "strips"
            image = Image.new("RGB", (220, 180), (235, 235, 235))
            draw = ImageDraw.Draw(image)
            draw.pieslice((40, 20, 180, 160), 200, 340, fill=(210, 30, 40))
            draw.pieslice((50, 30, 170, 150), 200, 340, fill=(30, 90, 220))
            draw.pieslice((65, 45, 155, 135), 200, 340, fill=(235, 235, 235))
            draw.line((110, 24, 110, 72), fill=(0, 0, 0), width=1)
            image.save(mockup)

            results = create_trim_strips_from_mockup(mockup, output_dir, strip_size=(160, 24))
            by_name = {result.name: result for result in results}
            with Image.open(by_name["collar_trim"].output_path) as opened:
                strip = opened.convert("RGBA")
            inner_band = strip.getpixel((80, 4))
            outer_band = strip.getpixel((80, 20))
            far_outer_band = strip.getpixel((150, 20))

        self.assertEqual(inner_band[:3], (30, 90, 220))
        self.assertEqual(outer_band[:3], (210, 30, 40))
        self.assertEqual(far_outer_band[:3], (210, 30, 40))

    def test_line_trim_picker_creates_clean_strip_from_sample_line(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mockup = tmp_path / "line_sample.png"
            output = tmp_path / "line_trim.png"
            image = Image.new("RGB", (40, 40), (235, 235, 235))
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 30, 20), fill=(240, 190, 20))
            draw.rectangle((10, 21, 30, 30), fill=(10, 40, 90))
            draw.point((20, 15), fill=(0, 0, 0))
            image.save(mockup)

            create_trim_strip_from_line(
                mockup,
                output,
                (20, 10),
                (20, 30),
                strip_size=(96, 24),
            )
            strip = Image.open(output).convert("RGBA")

        self.assertEqual(strip.getpixel((0, 4))[:3], (240, 190, 20))
        self.assertEqual(strip.getpixel((95, 4))[:3], (240, 190, 20))
        self.assertEqual(strip.getpixel((0, 20))[:3], (10, 40, 90))
        self.assertEqual(strip.getpixel((95, 20))[:3], (10, 40, 90))

    def test_line_trim_picker_can_crop_generated_strip(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mockup = tmp_path / "line_sample.png"
            output = tmp_path / "cropped_line_trim.png"
            image = Image.new("RGB", (40, 40), (235, 235, 235))
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 30, 20), fill=(240, 190, 20))
            draw.rectangle((10, 21, 30, 30), fill=(10, 40, 90))
            image.save(mockup)

            create_trim_strip_from_line(
                mockup,
                output,
                (20, 10),
                (20, 30),
                strip_size=(96, 24),
                crop_top=4,
                crop_bottom=6,
            )
            strip = Image.open(output).convert("RGBA")

        self.assertEqual(strip.size, (96, 14))

    def test_line_trim_picker_negative_crop_expands_sampled_photo_area(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            mockup = tmp_path / "line_sample.png"
            output = tmp_path / "expanded_line_trim.png"
            image = Image.new("RGB", (40, 44), (235, 235, 235))
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 8, 30, 9), fill=(180, 20, 30))
            draw.rectangle((10, 10, 30, 20), fill=(240, 190, 20))
            draw.rectangle((10, 21, 30, 30), fill=(10, 40, 90))
            draw.rectangle((10, 31, 30, 33), fill=(20, 160, 80))
            image.save(mockup)

            create_trim_strip_from_line(
                mockup,
                output,
                (20, 10),
                (20, 30),
                strip_size=(96, 24),
                crop_top=-2,
                crop_bottom=-3,
            )
            strip = Image.open(output).convert("RGBA")

        self.assertEqual(strip.size, (96, 29))
        self.assertEqual(strip.getpixel((0, 0))[:3], (180, 20, 30))
        self.assertEqual(strip.getpixel((95, 28))[:3], (20, 160, 80))

    def test_trim_corrector_fills_gaps_and_even_lines(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source = tmp_path / "strip.png"
            output = tmp_path / "strip_corrected.png"
            yellow = (240, 190, 20)
            navy = (10, 40, 90)
            image = Image.new("RGBA", (64, 12), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 2, 63, 4), fill=(*yellow, 255))
            draw.rectangle((20, 3, 26, 3), fill=(0, 0, 0, 0))
            draw.rectangle((0, 6, 63, 7), fill=(*yellow, 255))
            draw.rectangle((0, 8, 63, 10), fill=(*navy, 255))
            draw.point((3, 8), fill=(200, 20, 20, 255))
            image.save(source)

            correct_trim_strip(source, output)
            corrected = Image.open(output).convert("RGBA")

        self.assertEqual(corrected.getpixel((23, 3))[:3], yellow)
        self.assertEqual(corrected.getpixel((23, 5))[:3], yellow)
        self.assertEqual(corrected.getpixel((3, 8))[:3], navy)
        self.assertEqual(corrected.getpixel((0, 0))[3], 0)

    def test_auto_background_removes_colored_edge_connected_area(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (32, 24), (30, 90, 180, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 7, 21, 16), fill=(245, 190, 20, 255))

        cleaned = remove_detected_background(image, tolerance=20)

        self.assertEqual(cleaned.getpixel((1, 1))[3], 0)
        self.assertEqual(cleaned.getpixel((15, 11))[:3], (245, 190, 20))
        self.assertEqual(cleaned.getpixel((15, 11))[3], 255)

    def test_logo_upscale_increases_resolution_and_preserves_alpha(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (8, 6), (255, 0, 0, 128))

        upscaled = upscale_logo_image(image, scale_factor=4, sharpen=False)

        self.assertEqual(upscaled.size, (32, 24))
        self.assertGreater(upscaled.getpixel((16, 12))[3], 0)

    def test_trim_color_replacement_respects_tolerance_and_alpha(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
        image.putpixel((0, 0), (240, 190, 20, 255))
        image.putpixel((1, 0), (235, 185, 25, 128))
        image.putpixel((2, 0), (10, 40, 90, 255))

        corrected = _replace_trim_color(
            image,
            (240, 190, 20),
            (200, 20, 40),
            8,
        )

        self.assertEqual(corrected.getpixel((0, 0)), (200, 20, 40, 255))
        self.assertEqual(corrected.getpixel((1, 0)), (200, 20, 40, 128))
        self.assertEqual(corrected.getpixel((2, 0)), (10, 40, 90, 255))


class GeneratorTests(unittest.TestCase):
    def test_extract_number_sheet_from_font_iff_reads_font_number_color(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            font_iff = tmp_path / "font.iff"
            sheet = Image.new("RGBA", (40, 4), (0, 0, 0, 0))
            for index in range(10):
                for x in range(index * 4, index * 4 + 4):
                    for y in range(4):
                        sheet.putpixel((x, y), (index, 20, 30, 255))
            dds_path = tmp_path / "sheet.dds"
            save_bc1_dds(sheet, dds_path)
            with zipfile.ZipFile(font_iff, "w") as archive:
                archive.writestr(
                    "font_number_color.1234567890abcdef.dds",
                    dds_path.read_bytes(),
                )

            extracted = extract_number_sheet_from_font_iff(font_iff)
            digits = split_number_sheet_digits(extracted)

        self.assertEqual(extracted.size, (40, 4))
        self.assertEqual(len(digits), 10)
        self.assertEqual(digits[0].size, (4, 4))
        self.assertEqual(digits[7].getpixel((0, 0))[3], 255)

    def test_write_number_sheet_to_font_iff_replaces_number_color_dds(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_iff = tmp_path / "font.iff"
            output_iff = tmp_path / "font_modded.iff"
            original_dds = tmp_path / "original.dds"
            save_bc1_dds(Image.new("RGBA", (40, 4), (10, 20, 30, 255)), original_dds)
            original_dds_bytes = original_dds.read_bytes()
            with zipfile.ZipFile(source_iff, "w") as archive:
                archive.writestr("font_color_info.RDAT", b"keep")
                archive.writestr(
                    "font_number_color.1234567890abcdef.dds",
                    original_dds_bytes,
                )

            info = inspect_font_number_texture(source_iff)
            digit_paths = {}
            for index in range(10):
                digit_path = tmp_path / f"digit_{index}.png"
                Image.new("RGBA", (4, 4), (index, 40, 50, 255)).save(digit_path)
                digit_paths[str(index)] = digit_path
            sheet = build_font_number_sheet(digit_paths, (info.width, info.height))

            write_number_sheet_to_font_iff(source_iff, output_iff, sheet)

            with zipfile.ZipFile(output_iff) as archive:
                replaced = archive.read("font_number_color.1234567890abcdef.dds")
                kept = archive.read("font_color_info.RDAT")

        self.assertEqual(kept, b"keep")
        self.assertTrue(replaced.startswith(b"DDS "))
        self.assertEqual(replaced[84:88], b"DXT1")
        self.assertNotEqual(replaced, original_dds_bytes)

    def test_write_number_sheet_to_font_iff_can_overwrite_source_safely(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_iff = tmp_path / "font.iff"
            original_dds = tmp_path / "original.dds"
            save_bc1_dds(Image.new("RGBA", (40, 4), (10, 20, 30, 255)), original_dds)
            original_dds_bytes = original_dds.read_bytes()
            with zipfile.ZipFile(source_iff, "w") as archive:
                archive.writestr("font_color_info.RDAT", b"keep")
                archive.writestr(
                    "font_number_color.1234567890abcdef.dds",
                    original_dds_bytes,
                )

            info = inspect_font_number_texture(source_iff)
            sheet = Image.new("RGBA", (info.width, info.height), (220, 30, 40, 255))

            write_number_sheet_to_font_iff(source_iff, source_iff, sheet)

            with zipfile.ZipFile(source_iff) as archive:
                replaced = archive.read("font_number_color.1234567890abcdef.dds")
                kept = archive.read("font_color_info.RDAT")

        self.assertEqual(kept, b"keep")
        self.assertTrue(replaced.startswith(b"DDS "))
        self.assertNotEqual(replaced, original_dds_bytes)

    def test_save_bc1_dds_writes_dxt1_texture(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "generated.dds"
            image = Image.new("RGBA", (8, 8), (220, 30, 40, 255))

            save_bc1_dds(image, output)

            data = output.read_bytes()

        self.assertEqual(data[:4], b"DDS ")
        self.assertEqual(struct.unpack_from("<I", data, 4)[0], 124)
        self.assertEqual(struct.unpack_from("<I", data, 16)[0], 8)
        self.assertEqual(struct.unpack_from("<I", data, 12)[0], 8)
        self.assertEqual(struct.unpack_from("<I", data, 28)[0], 4)
        self.assertEqual(data[84:88], b"DXT1")
        self.assertEqual(len(data), 184)

    def test_generate_jersey_texture_fills_base_and_side_panel(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output = tmp_path / "generated.png"
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 20, 20, "#05ff05", 0),
                    TemplateZone("left_side_panel", "stripe", 5, 5, 10, 10, "#1820c9", 20),
                    TemplateZone("collar_background", "trim", 0, 22, 12, 6, "#f5b11a", 25),
                    TemplateZone("collar_trim", "trim", 21, 0, 8, 8, "#d118e8", 30),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    collar_background_color="#ffcc00",
                    collar_trim_color="#123456",
                ),
                output,
                size=(32, 32),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((1, 1))[:3], (17, 34, 51))
        self.assertEqual(image.getpixel((6, 6))[:3], (171, 205, 239))
        self.assertEqual(image.getpixel((1, 23))[:3], (255, 204, 0))
        self.assertEqual(image.getpixel((22, 1))[:3], (18, 52, 86))

    def test_generate_jersey_texture_no_color_leaves_zone_transparent(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output = tmp_path / "generated.png"
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("left_side_panel", "stripe", 2, 2, 8, 8, "#1820c9", 20),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="",
                    right_panel_color="#fedcba",
                ),
                output,
                size=(16, 16),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((3, 3))[3], 0)

    def test_side_panel_image_can_render_outside_zone_guide(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            panel = tmp_path / "panel.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (10, 10), (255, 0, 0, 255)).save(panel)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("left_side_panel", "stripe", 5, 5, 10, 10, "#1820c9", 20),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="",
                    right_panel_color="#fedcba",
                    left_panel_image=panel,
                    trim_placements={
                        "left_side_panel": TrimPlacementSettings(offset_x=-4)
                    },
                ),
                output,
                size=(20, 20),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((2, 8)), (255, 0, 0, 255))

    def test_generate_jersey_texture_places_front_wordmark(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wordmark = tmp_path / "wordmark.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (8, 4), (255, 0, 0, 255)).save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("front_wordmark", "wordmark", 10, 10, 20, 10, "#000000", 40),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    front_wordmark_image=wordmark,
                ),
                output,
                size=(48, 48),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((16, 13))[:3], (255, 0, 0))

    def test_generate_jersey_texture_moves_front_wordmark(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wordmark = tmp_path / "wordmark.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (8, 4), (255, 0, 0, 255)).save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("front_wordmark", "wordmark", 10, 10, 20, 10, "#000000", 40),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    front_wordmark_image=wordmark,
                    front_wordmark_offset_x=4,
                    front_wordmark_offset_y=2,
                ),
                output,
                size=(48, 48),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((16, 13))[3], 0)
        self.assertEqual(image.getpixel((20, 15))[:3], (255, 0, 0))

    def test_generate_jersey_texture_allows_front_wordmark_outside_bounds(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wordmark = tmp_path / "wordmark.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (8, 4), (255, 0, 0, 255)).save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("front_wordmark", "wordmark", 10, 10, 20, 10, "#000000", 40),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    front_wordmark_image=wordmark,
                    front_wordmark_offset_x=-12,
                    front_wordmark_offset_y=-8,
                    front_wordmark_scale_percent=200,
                ),
                output,
                size=(48, 48),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((2, 3))[:3], (255, 0, 0))

    def test_generate_jersey_texture_places_logo_at_selected_zone(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logo = tmp_path / "logo.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (4, 4), (255, 200, 0, 255)).save(logo)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_left_chest_logo", "logo", 4, 4, 8, 8, "#ffffff", 50),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    logo_placements=(
                        LogoPlacement(logo, "front_left_chest_logo"),
                    ),
                ),
                output,
                size=(24, 24),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((6, 6))[:3], (255, 200, 0))

    def test_image_placement_rects_reports_scaled_movable_logo(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logo = tmp_path / "logo.png"
            Image.new("RGBA", (4, 4), (255, 200, 0, 255)).save(logo)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_left_chest_logo", "logo", 4, 4, 8, 8, "#ffffff", 50),
                ),
            )

            placements = image_placement_rects(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    logo_placements=(
                        LogoPlacement(
                            logo,
                            "front_left_chest_logo",
                            offset_x=3,
                            offset_y=-2,
                            scale_percent=200,
                        ),
                    ),
                ),
            )

        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0].key, "logo:0")
        self.assertEqual((placements[0].x, placements[0].y), (7, 2))
        self.assertEqual((placements[0].width, placements[0].height), (8, 8))

    def test_logo_target_zones_uses_defaults_without_custom_logo_zones(self) -> None:
        template = JerseyTemplate(
            image_path="",
            zones=(TemplateZone("front_jersey_base", "base", 0, 0, 10, 10, "#ffffff", 0),),
        )

        targets = logo_target_zones(template)

        self.assertIn("front_left_chest_logo", {zone.name for zone in targets})

    def test_generate_retro_shorts_template_fills_panels_and_logo_target(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "shorts.png"
            template = load_template(SHORTS_TEMPLATE_RETRO_ZONES)
            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="",
                    back_color="",
                    left_panel_color="#ff0000",
                    right_panel_color="#00ff00",
                    collar_background_color="#0000ff",
                ),
                output,
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((10, 10)), (0, 0, 255, 255))
        self.assertEqual(image.getpixel((10, 200)), (255, 0, 0, 255))
        self.assertEqual(image.getpixel((10, 1200)), (0, 255, 0, 255))
        self.assertEqual(image.getpixel((1450, 1500)), (0, 0, 0, 0))
        self.assertEqual(
            {zone.name for zone in logo_target_zones(template)},
            {"shorts_belt_buckle_logo"},
        )

    def test_side_panel_image_is_web_editable_with_rotation(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "panel.png"
            Image.new("RGBA", (20, 10), (255, 0, 0, 255)).save(image_path)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("left_side_panel", "stripe", 100, 200, 100, 80, "#0000ff", 10),
                ),
            )
            placements = image_placement_rects(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    left_panel_image=image_path,
                    trim_placements={
                        "left_side_panel": TrimPlacementSettings(
                            offset_x=7,
                            offset_y=-3,
                            scale_percent=150,
                            rotation_degrees=25,
                        )
                    },
                ),
            )

        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0].key, "left_side_panel")
        self.assertEqual(placements[0].clip_x, 100)
        self.assertEqual(placements[0].clip_y, 200)
        self.assertEqual(placements[0].rotation_degrees, 25)
        self.assertEqual(placements[0].width, 30)

    def test_side_panel_image_supports_independent_width_and_height_scale(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "panel.png"
            Image.new("RGBA", (20, 10), (255, 0, 0, 255)).save(image_path)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("left_side_panel", "stripe", 100, 200, 100, 80, "#0000ff", 10),
                ),
            )
            placements = image_placement_rects(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    left_panel_image=image_path,
                    trim_placements={
                        "left_side_panel": TrimPlacementSettings(
                            scale_width_percent=150,
                            scale_height_percent=300,
                        )
                    },
                ),
            )

        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0].width, 30)
        self.assertEqual(placements[0].height, 30)

    def test_render_jersey_region_map_marks_panels_and_decals(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wordmark = tmp_path / "wordmark.png"
            logo = tmp_path / "logo.png"
            wordmark_image = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
            ImageDraw.Draw(wordmark_image).rectangle((10, 10, 110, 50), fill=(255, 255, 255, 255))
            wordmark_image.save(wordmark)
            logo_image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
            logo_image.save(logo)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_wordmark", "wordmark", 900, 600, 400, 220, "#000000", 30),
                    TemplateZone("left_side_panel", "stripe", 100, 1000, 200, 600, "#0000ff", 10),
                    TemplateZone("right_side_panel", "stripe", 1700, 1000, 200, 600, "#ff0000", 10),
                    TemplateZone("front_left_chest_logo", "logo", 1010, 610, 180, 180, "#ffffff", 50),
                ),
            )

            region = render_jersey_region_map(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ff0000",
                    right_panel_color="#ffffff",
                    front_wordmark_image=wordmark,
                    logo_placements=(LogoPlacement(logo, "front_left_chest_logo"),),
                ),
                JERSEY_REGION_TEMPLATE_IMAGE,
            )

        self.assertEqual(region.size, (1024, 1024))
        self.assertEqual(region.getpixel((60, 550)), (192, 0, 102, 255))
        self.assertEqual(region.getpixel((540, 340)), (132, 0, 216, 255))
        self.assertEqual(region.getpixel((10, 300)), (203, 0, 102, 255))

    def test_render_jersey_region_map_skips_inactive_side_panels(self) -> None:
        template = JerseyTemplate(
            image_path="",
            zones=(
                TemplateZone("left_side_panel", "stripe", 100, 1000, 200, 600, "#0000ff", 10),
            ),
        )

        region = render_jersey_region_map(
            template,
            GeneratorInputs(
                front_color="#ffffff",
                back_color="#ffffff",
                left_panel_color="#ffffff",
                right_panel_color="#ffffff",
            ),
            JERSEY_REGION_TEMPLATE_IMAGE,
        )

        self.assertEqual(region.getpixel((60, 550)), (203, 0, 102, 255))

    def test_render_jersey_normal_map_adds_artwork_detail(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            normal_template = tmp_path / "normal.png"
            wordmark = tmp_path / "wordmark.png"
            Image.new("RGBA", (64, 64), (128, 128, 255, 255)).save(normal_template)
            wordmark_image = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
            ImageDraw.Draw(wordmark_image).rectangle(
                (48, 48, 464, 208),
                fill=(255, 255, 255, 255),
            )
            wordmark_image.save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_wordmark", "wordmark", 512, 512, 512, 256, "#000000", 10),
                ),
            )

            normal = render_jersey_normal_map(
                template,
                GeneratorInputs(
                    "#ffffff",
                    "#ffffff",
                    "#ffffff",
                    "#ffffff",
                    front_wordmark_image=wordmark,
                ),
                normal_template,
            )

        self.assertEqual(normal.size, (64, 64))
        self.assertTrue(
            any(
                normal.getpixel((x, y)) != (128, 128, 255, 255)
                for y in range(64)
                for x in range(64)
            )
        )

    def test_render_jersey_normal_map_ignores_background_colors(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            normal_template = tmp_path / "normal.png"
            base = Image.new("RGBA", (64, 64), (128, 128, 255, 255))
            base.save(normal_template)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("left_side_panel", "stripe", 8, 8, 20, 40, "#0000ff", 10),
                    TemplateZone("collar_trim", "trim", 4, 2, 56, 6, "#ff00ff", 10),
                ),
            )

            normal = render_jersey_normal_map(
                template,
                GeneratorInputs(
                    "#ffffff",
                    "#ffffff",
                    "#ff0000",
                    "#00ff00",
                    collar_trim_color="#0000ff",
                ),
                normal_template,
            )

        self.assertEqual(normal.tobytes(), base.tobytes())

    def test_render_jersey_normal_map_can_disable_logo_strength(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            normal_template = tmp_path / "normal.png"
            wordmark = tmp_path / "wordmark.png"
            base = Image.new("RGBA", (64, 64), (128, 128, 255, 255))
            base.save(normal_template)
            wordmark_image = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
            ImageDraw.Draw(wordmark_image).rectangle(
                (48, 48, 464, 208),
                fill=(255, 255, 255, 255),
            )
            wordmark_image.save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_wordmark", "wordmark", 512, 512, 512, 256, "#000000", 10),
                ),
            )

            normal = render_jersey_normal_map(
                template,
                GeneratorInputs(
                    "#ffffff",
                    "#ffffff",
                    "#ffffff",
                    "#ffffff",
                    front_wordmark_image=wordmark,
                ),
                normal_template,
                normal_strength=0,
            )

        self.assertEqual(normal.tobytes(), base.tobytes())

    def test_scaled_logo_uses_single_resize_from_original(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        original = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
        pixels = original.load()
        for y in range(original.height):
            for x in range(original.width):
                pixels[x, y] = ((x * 7) % 256, (y * 11) % 256, (x + y) % 256, 255)
        expected = original.copy()
        expected.thumbnail((200, 200), Image.Resampling.LANCZOS)

        rendered, _x, _y = _overlay_at_zone(
            original.copy(),
            TemplateZone("front_left_chest_logo", "logo", 0, 0, 100, 100, "#ffffff", 50),
            GeneratorInputs(
                front_color="#ffffff",
                back_color="#ffffff",
                left_panel_color="#ffffff",
                right_panel_color="#ffffff",
            ),
            logo=LogoPlacement(Path("logo.png"), "front_left_chest_logo", scale_percent=200),
        )

        self.assertEqual(rendered.size, expected.size)
        self.assertEqual(rendered.tobytes(), expected.tobytes())

    def test_wrap_logo_type_stretches_across_x_axis(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logo = tmp_path / "wrap.png"
            Image.new("RGBA", (4, 2), (255, 200, 0, 255)).save(logo)
            template = JerseyTemplate(image_path="", zones=())

            placements = image_placement_rects(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    logo_placements=(
                        LogoPlacement(
                            logo,
                            "wrap_across_front_back_logo",
                            offset_x=300,
                            offset_y=10,
                            scale_percent=200,
                            stretch_x=True,
                        ),
                    ),
                ),
            )

        self.assertEqual(len(placements), 1)
        self.assertEqual(placements[0].width, 2048)
        self.assertEqual(placements[0].height, 2048)
        self.assertEqual(placements[0].x, 0)
        self.assertEqual(placements[0].y, -184)

    def test_front_wordmark_renders_above_logos(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logo = tmp_path / "logo.png"
            wordmark = tmp_path / "wordmark.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (4, 4), (255, 200, 0, 255)).save(logo)
            Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_wordmark", "wordmark", 4, 4, 8, 8, "#000000", 40),
                    TemplateZone("front_left_chest_logo", "logo", 4, 4, 8, 8, "#ffffff", 50),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    front_wordmark_image=wordmark,
                    logo_placements=(LogoPlacement(logo, "front_left_chest_logo"),),
                ),
                output,
                size=(24, 24),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((7, 7))[:3], (255, 0, 0))

    def test_fabric_overlay_darkens_generated_png(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            overlay = tmp_path / "overlay.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(overlay)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("front_jersey_base", "base", 0, 0, 8, 8, "#ffffff", 0),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    fabric_overlay_image=overlay,
                    fabric_overlay_opacity=100,
                    fabric_overlay_blend_mode="multiply",
                ),
                output,
                size=(8, 8),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((2, 2))[:3], (0, 0, 0))

    def test_dynamic_layer_order_can_place_fabric_below_logo(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            overlay = tmp_path / "overlay.png"
            logo = tmp_path / "logo.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(overlay)
            Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(logo)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 8, 8, "#ffffff", 0),
                    TemplateZone("front_left_chest_logo", "logo", 0, 0, 8, 8, "#ffffff", 50),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    logo_placements=(LogoPlacement(logo, "front_left_chest_logo"),),
                    fabric_overlay_image=overlay,
                    fabric_overlay_opacity=100,
                    fabric_overlay_blend_mode="multiply",
                    dynamic_layer_order=("fabric_overlay", "logo:0"),
                ),
                output,
                size=(8, 8),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((3, 3))[:3], (255, 0, 0))

    def test_fabric_overlay_multiply_skips_trim_zones(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            overlay = tmp_path / "overlay.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(overlay)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 8, 8, "#ffffff", 0),
                    TemplateZone("collar_trim", "trim", 2, 2, 4, 4, "#ffffff", 30),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    collar_trim_color="#ffffff",
                    fabric_overlay_image=overlay,
                    fabric_overlay_opacity=100,
                    fabric_overlay_blend_mode="multiply",
                ),
                output,
                size=(8, 8),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((1, 1))[:3], (0, 0, 0))
        self.assertEqual(image.getpixel((3, 3))[:3], (255, 255, 255))

    def test_fabric_overlay_exports_as_psd_layer(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            overlay = tmp_path / "overlay.png"
            output = tmp_path / "generated.psd"
            Image.new("RGBA", (4, 4), (0, 0, 0, 255)).save(overlay)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("front_jersey_base", "base", 0, 0, 8, 8, "#ffffff", 0),),
            )

            generate_layered_jersey_psd(
                template,
                GeneratorInputs(
                    front_color="#ffffff",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    fabric_overlay_image=overlay,
                    fabric_overlay_opacity=100,
                    fabric_overlay_blend_mode="multiply",
                ),
                output,
                size=(8, 8),
            )
            data = output.read_bytes()

        self.assertIn(b"Fabric / Wrinkle Overlay", data)
        self.assertIn(b"mul ", data)

    def test_generate_jersey_texture_places_trim_image(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            trim = tmp_path / "trim.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (2, 2), (0, 120, 255, 255)).save(trim)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("collar_trim", "trim", 2, 2, 10, 10, "#000000", 30),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    collar_trim_image=trim,
                ),
                output,
                size=(24, 24),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((5, 5))[:3], (0, 120, 255))
        self.assertEqual(image.getpixel((11, 11))[:3], (0, 120, 255))

    def test_trim_image_adjustment_is_clipped_to_template_box(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            trim = tmp_path / "trim.png"
            output = tmp_path / "generated.png"
            Image.new("RGBA", (2, 2), (0, 120, 255, 255)).save(trim)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 12, 12, "#000000", 0),
                    TemplateZone("collar_trim", "trim", 4, 4, 4, 4, "#000000", 30),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    collar_trim_image=trim,
                    trim_placements={
                        "collar_trim": TrimPlacementSettings(
                            offset_x=-3,
                            offset_y=-3,
                            scale_percent=200,
                        ),
                    },
                ),
                output,
                size=(12, 12),
            )
            image = Image.open(output).convert("RGBA")
            placements = image_placement_rects(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    collar_trim_image=trim,
                    trim_placements={
                        "collar_trim": TrimPlacementSettings(
                            offset_x=-3,
                            offset_y=-3,
                            scale_percent=200,
                        ),
                    },
                ),
            )

        self.assertEqual(image.getpixel((3, 4))[:3], (17, 34, 51))
        self.assertEqual(image.getpixel((4, 4))[:3], (0, 120, 255))
        self.assertEqual(placements[0].key, "collar_trim")
        self.assertEqual(
            (
                placements[0].clip_x,
                placements[0].clip_y,
                placements[0].clip_width,
                placements[0].clip_height,
            ),
            (4, 4, 4, 4),
        )

    def test_generate_layered_jersey_psd_writes_layers_and_preview(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            output = tmp_path / "generated.psd"
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 12, 12, "#05ff05", 0),
                    TemplateZone("collar_trim", "trim", 4, 4, 6, 6, "#d118e8", 30),
                ),
            )

            generate_layered_jersey_psd(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    collar_trim_color="#ff00ff",
                ),
                output,
                size=(16, 16),
            )
            data = output.read_bytes()
            with Image.open(output) as opened:
                image = opened.convert("RGBA")

        self.assertEqual(data[:4], b"8BPS")
        self.assertIn(b"Front Jersey Base", data)
        self.assertIn(b"Collar Trim", data)
        self.assertEqual(image.size, (16, 16))
        self.assertEqual(image.getpixel((1, 1))[:3], (17, 34, 51))
        self.assertEqual(image.getpixel((5, 5))[:3], (255, 0, 255))

    def test_generate_jersey_texture_removes_white_image_background(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            wordmark = tmp_path / "wordmark.png"
            output = tmp_path / "generated.png"
            mark = Image.new("RGBA", (10, 10), (255, 255, 255, 255))
            ImageDraw.Draw(mark).rectangle((3, 3, 6, 6), fill=(255, 0, 0, 255))
            mark.save(wordmark)
            template = JerseyTemplate(
                image_path="",
                zones=(TemplateZone("front_wordmark", "wordmark", 10, 10, 20, 20, "#000000", 40),),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#445566",
                    left_panel_color="#abcdef",
                    right_panel_color="#fedcba",
                    front_wordmark_image=wordmark,
                    remove_white_background=True,
                ),
                output,
                size=(48, 48),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((16, 16))[3], 0)
        self.assertEqual(image.getpixel((20, 20))[:3], (255, 0, 0))
        self.assertEqual(image.getpixel((20, 20))[3], 255)

    def test_layer_background_cleanup_only_applies_to_selected_layer(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logo = tmp_path / "logo.png"
            output = tmp_path / "generated.png"
            mark = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
            ImageDraw.Draw(mark).rectangle((1, 1, 2, 2), fill=(255, 0, 0, 255))
            mark.save(logo)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 12, 6, "#ffffff", 0),
                    TemplateZone("front_left_chest_logo", "logo", 0, 0, 4, 4, "#ffffff", 50),
                    TemplateZone("front_right_chest_logo", "logo", 6, 0, 4, 4, "#ffffff", 50),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    logo_placements=(
                        LogoPlacement(logo, "front_left_chest_logo"),
                        LogoPlacement(logo, "front_right_chest_logo"),
                    ),
                    layer_background_cleanup={
                        "logo:0": BackgroundCleanupSettings(remove_white=True),
                    },
                ),
                output,
                size=(12, 6),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((0, 0))[:3], (17, 34, 51))
        self.assertEqual(image.getpixel((6, 0))[:3], (255, 255, 255))
        self.assertEqual(image.getpixel((1, 1))[:3], (255, 0, 0))

    def test_layer_auto_background_cleanup_removes_colored_logo_background(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            logo = tmp_path / "logo.png"
            output = tmp_path / "generated.png"
            mark = Image.new("RGBA", (6, 6), (30, 90, 180, 255))
            ImageDraw.Draw(mark).rectangle((2, 2, 3, 3), fill=(245, 190, 20, 255))
            mark.save(logo)
            template = JerseyTemplate(
                image_path="",
                zones=(
                    TemplateZone("front_jersey_base", "base", 0, 0, 8, 8, "#ffffff", 0),
                    TemplateZone("front_left_chest_logo", "logo", 1, 1, 6, 6, "#ffffff", 50),
                ),
            )

            generate_jersey_texture(
                template,
                GeneratorInputs(
                    front_color="#112233",
                    back_color="#ffffff",
                    left_panel_color="#ffffff",
                    right_panel_color="#ffffff",
                    logo_placements=(LogoPlacement(logo, "front_left_chest_logo"),),
                    layer_background_cleanup={
                        "logo:0": BackgroundCleanupSettings(auto_background=True, tolerance=20),
                    },
                ),
                output,
                size=(8, 8),
            )
            image = Image.open(output).convert("RGBA")

        self.assertEqual(image.getpixel((1, 1))[:3], (17, 34, 51))
        self.assertEqual(image.getpixel((3, 3))[:3], (245, 190, 20))

    def test_remove_image_background_preserves_inside_lettering_holes(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (9, 9), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 6, 6), fill=(255, 0, 0, 255))
        draw.rectangle((4, 4, 4, 4), fill=(255, 255, 255, 255))

        cleaned = remove_image_background(image, remove_white=True, tolerance=8)

        self.assertEqual(cleaned.getpixel((0, 0))[3], 0)
        self.assertEqual(cleaned.getpixel((4, 4)), (255, 255, 255, 255))

    def test_remove_image_background_can_remove_all_matching_pixels(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (9, 9), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 6, 6), fill=(255, 0, 0, 255))
        draw.rectangle((4, 4, 4, 4), fill=(255, 255, 255, 255))

        cleaned = remove_image_background(
            image,
            remove_white=True,
            outside_only=False,
            tolerance=8,
        )

        self.assertEqual(cleaned.getpixel((0, 0))[3], 0)
        self.assertEqual(cleaned.getpixel((4, 4))[3], 0)

    def test_remove_image_background_removes_black_pixels(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
        image.putpixel((1, 0), (255, 0, 0, 255))

        cleaned = remove_image_background(
            image,
            remove_black=True,
            outside_only=False,
            tolerance=8,
        )

        self.assertEqual(cleaned.getpixel((0, 0))[3], 0)
        self.assertEqual(cleaned.getpixel((1, 0)), (255, 0, 0, 255))

    def test_remove_sampled_color_background_preserves_inside_holes_by_default(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        sampled = (20, 120, 180)
        image = Image.new("RGBA", (9, 9), (*sampled, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 6, 6), fill=(255, 0, 0, 255))
        draw.rectangle((4, 4, 4, 4), fill=(*sampled, 255))

        cleaned = _remove_sampled_color_background(image, sampled, tolerance=4)

        self.assertEqual(cleaned.getpixel((0, 0))[3], 0)
        self.assertEqual(cleaned.getpixel((4, 4)), (*sampled, 255))

    def test_remove_sampled_color_background_can_remove_all_matching_pixels(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        sampled = (20, 120, 180)
        image = Image.new("RGBA", (9, 9), (*sampled, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 6, 6), fill=(255, 0, 0, 255))
        draw.rectangle((4, 4, 4, 4), fill=(*sampled, 255))

        cleaned = _remove_sampled_color_background(
            image,
            sampled,
            outside_only=False,
            tolerance=4,
        )

        self.assertEqual(cleaned.getpixel((0, 0))[3], 0)
        self.assertEqual(cleaned.getpixel((4, 4))[3], 0)

    def test_trim_transparent_padding_removes_empty_space(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((8, 6, 11, 13), fill=(255, 0, 0, 255))

        trimmed = _trim_transparent_padding(image, padding=2)

        self.assertEqual(trimmed.size, (8, 12))
        self.assertEqual(trimmed.getpixel((2, 2)), (255, 0, 0, 255))
        self.assertEqual(trimmed.getpixel((0, 0))[3], 0)

    def test_loaded_number_digit_keys_only_counts_existing_digit_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            digit_3 = tmp_path / "digit_3.png"
            digit_8 = tmp_path / "digit_8.png"
            digit_3.write_bytes(b"digit")
            digit_8.write_bytes(b"digit")

            loaded = _loaded_number_digit_keys(
                {
                    "0": tmp_path / "missing_0.png",
                    "3": digit_3,
                    "8": digit_8,
                    "12": tmp_path / "not_a_game_digit.png",
                }
            )

        self.assertEqual(loaded, {"3", "8"})

    def test_fit_transparent_image_to_square_centers_logo(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((10, 8, 69, 31), fill=(255, 0, 0, 255))

        fitted = _fit_transparent_image_to_square(image, 1024, padding_ratio=0.08)

        self.assertEqual(fitted.size, (1024, 1024))
        self.assertEqual(fitted.getpixel((0, 0))[3], 0)
        self.assertGreater(fitted.getchannel("A").getbbox()[0], 0)
        self.assertGreater(fitted.getchannel("A").getbbox()[1], 0)

    def test_nudge_image_shifts_inside_same_canvas(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (6, 6), (0, 0, 0, 0))
        image.putpixel((2, 2), (255, 0, 0, 255))

        nudged = _nudge_image(image, 1, -1)

        self.assertEqual(nudged.size, image.size)
        self.assertEqual(nudged.getpixel((3, 1)), (255, 0, 0, 255))
        self.assertEqual(nudged.getpixel((2, 2))[3], 0)

    def test_align_image_to_visible_center_matches_template_center(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        template = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        ImageDraw.Draw(template).rectangle((8, 6, 11, 13), fill=(255, 0, 0, 255))
        candidate = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        ImageDraw.Draw(candidate).rectangle((5, 9, 8, 16), fill=(255, 0, 0, 255))

        aligned = _align_image_to_visible_center(candidate, (9.5, 9.5))

        self.assertEqual(aligned.getchannel("A").getbbox(), template.getchannel("A").getbbox())

    def test_place_image_visible_center_creates_font_cell(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        cropped_digit = Image.new("RGBA", (8, 12), (0, 0, 0, 0))
        ImageDraw.Draw(cropped_digit).rectangle((2, 1, 5, 10), fill=(255, 0, 0, 255))

        cell = _place_image_visible_center(cropped_digit, (20, 20), (12.5, 9.5))

        self.assertEqual(cell.size, (20, 20))
        self.assertEqual(cell.getchannel("A").getbbox(), (11, 5, 15, 15))

    def test_recolor_font_image_detects_outline_from_alpha_edges(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((1, 1, 7, 7), fill=(120, 120, 120, 255))
        draw.rectangle((3, 3, 5, 5), fill=(240, 240, 240, 128))

        recolored = _recolor_font_image(image, (0, 0, 255), (255, 255, 0))

        edge_red, edge_green, edge_blue, edge_alpha = recolored.getpixel((1, 4))
        center_red, center_green, center_blue, center_alpha = recolored.getpixel((4, 4))

        self.assertEqual(edge_alpha, 255)
        self.assertEqual(center_alpha, 128)
        self.assertLess(edge_red, 80)
        self.assertLess(edge_green, 80)
        self.assertGreater(edge_blue, 175)
        self.assertGreater(center_red, 175)
        self.assertGreater(center_green, 175)
        self.assertLess(center_blue, 80)
        self.assertEqual(recolored.getpixel((0, 0))[3], 0)

    def test_recolor_font_image_can_leave_fill_or_outline_original(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((1, 1, 7, 7), fill=(120, 120, 120, 255))
        draw.rectangle((3, 3, 5, 5), fill=(240, 240, 240, 255))

        no_fill = _recolor_font_image(image, (0, 0, 255), None)
        no_outline = _recolor_font_image(image, None, (255, 255, 0))

        no_fill_edge = no_fill.getpixel((1, 4))[:3]
        no_outline_center = no_outline.getpixel((4, 4))[:3]

        self.assertLess(no_fill_edge[0], 20)
        self.assertLess(no_fill_edge[1], 20)
        self.assertGreater(no_fill_edge[2], 235)
        self.assertEqual(no_fill.getpixel((4, 4))[:3], (240, 240, 240))
        no_outline_edge = no_outline.getpixel((1, 4))[:3]
        self.assertLess(abs(no_outline_edge[0] - 120), 10)
        self.assertLess(abs(no_outline_edge[1] - 120), 10)
        self.assertLess(abs(no_outline_edge[2] - 120), 10)
        self.assertGreater(no_outline_center[0], 235)
        self.assertGreater(no_outline_center[1], 235)
        self.assertLess(no_outline_center[2], 20)

    def test_recolor_font_image_edge_protection_keeps_fill_from_edges(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (9, 9), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((1, 1, 7, 7), fill=(120, 120, 120, 255))
        ImageDraw.Draw(image).rectangle((3, 3, 5, 5), fill=(240, 240, 240, 255))

        low_protection = _recolor_font_image(
            image,
            (0, 0, 255),
            (255, 255, 0),
            edge_protection=0.0,
        )
        high_protection = _recolor_font_image(
            image,
            (0, 0, 255),
            (255, 255, 0),
            edge_protection=1.0,
        )

        low_edge = low_protection.getpixel((2, 4))[:3]
        high_edge = high_protection.getpixel((2, 4))[:3]
        high_center = high_protection.getpixel((4, 4))[:3]

        self.assertGreater(low_edge[0], high_edge[0])
        self.assertGreater(low_edge[1], high_edge[1])
        self.assertGreater(high_edge[2], low_edge[2])
        self.assertGreater(high_center[0], 175)
        self.assertGreater(high_center[1], 175)

    def test_recolor_font_image_preserves_antialiased_alpha(self) -> None:
        try:
            from PIL import Image, ImageDraw
        except ImportError:
            self.skipTest("Pillow not available")

        image = Image.new("RGBA", (11, 11), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 8, 8), fill=(90, 90, 90, 180))
        draw.rectangle((3, 3, 7, 7), fill=(240, 240, 240, 255))
        draw.rectangle((4, 4, 6, 6), fill=(250, 250, 250, 255))

        recolored = _recolor_font_image(
            image,
            (10, 20, 220),
            (245, 210, 40),
            edge_protection=0.9,
        )

        self.assertEqual(recolored.getpixel((2, 5))[3], 180)
        self.assertEqual(recolored.getpixel((5, 5))[3], 255)
        edge = recolored.getpixel((2, 5))[:3]
        center = recolored.getpixel((5, 5))[:3]
        self.assertGreater(edge[2], edge[0])
        self.assertGreater(center[0], center[2])
        self.assertGreater(center[1], center[2])


if __name__ == "__main__":
    unittest.main()
