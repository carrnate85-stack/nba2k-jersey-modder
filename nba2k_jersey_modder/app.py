from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
import webbrowser
import zipfile

from . import __app_name__, __version__
from .dds import save_bc1_dds
from .font_iff import (
    FontNumberTextureInfo,
    build_font_number_sheet,
    extract_number_sheet_from_font_iff,
    inspect_font_number_texture,
    split_number_sheet_digits,
    write_number_sheet_to_font_iff,
)
from .generator import (
    BackgroundCleanupSettings,
    GeneratorInputs,
    LogoPlacement,
    TrimPlacementSettings,
    fabric_overlay_layer,
    generate_jersey_texture,
    generate_layered_jersey_psd,
    image_placement_rects,
    logo_target_zones,
    render_jersey_normal_map,
    render_jersey_texture,
    render_jersey_region_map,
)
from .iff_patch import (
    Replacement,
    apply_replacements,
    can_replace_embedded_resource,
    can_replace_resource,
)
from .scanner import IffScanResult, ResourceHit, TexturePair, scan_iff
from .template import (
    JERSEY_REGION_TEMPLATE_IMAGE,
    JERSEY_NORMAL_TEMPLATE_IMAGE,
    JERSEY_TEMPLATE_OPTIONS,
    JERSEY_UV_TEMPLATE_IMAGE,
    JerseyTemplate,
    MASTER_TEMPLATE_IMAGE,
    MASTER_TEMPLATE_ZONES,
    SHORTS_TEMPLATE_OPTIONS,
    TemplateZone,
    create_uv_overlay_from_template,
    find_hex_color_zone_bbox,
    load_template,
    save_template,
)
from .trim_creator import (
    TrimStrip,
    correct_trim_strip,
    create_trim_strip_from_line,
)
from .tweak_iff import (
    FrontNumberTweak,
    inspect_front_number_tweak,
    write_front_number_tweak,
)
from .web_editor import WebEditorServer

HEX_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FABRIC_OVERLAY_DIR = PROJECT_ROOT / "assets" / "overlays"
TRIM_LIBRARY_DIR = PROJECT_ROOT / "trim_library"
BLENDER_PREVIEW_BLEND = PROJECT_ROOT / "blendermodels" / "jerseyretroU.blend"
BLENDER_PREVIEW_SCRIPT = PROJECT_ROOT / "tools" / "blender_apply_jersey_preview.py"
BLENDER_EXECUTABLE_CANDIDATES = (
    Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"),
)
JERSEY_CUT_OPTIONS = ("Retro U",)
JERSEY_CUT_TEMPLATE_OPTIONS = {
    "Retro U": MASTER_TEMPLATE_ZONES,
}
JERSEY_CUT_IMAGE_OPTIONS = {
    "Retro U": MASTER_TEMPLATE_IMAGE,
}
JERSEY_CUT_UV_OPTIONS = {
    "Retro U": JERSEY_UV_TEMPLATE_IMAGE,
}
TRIM_GENERATOR_KEYS = {
    "left_arm_hole_trim": "left_arm_hole_trim_image",
    "right_arm_hole_trim": "right_arm_hole_trim_image",
    "collar_trim": "collar_trim_image",
}
SIDE_PANEL_GENERATOR_KEYS = {
    "left_side_panel": "left_panel_image",
    "right_side_panel": "right_panel_image",
    "shorts_left_panel": "left_panel_image",
    "shorts_right_panel": "right_panel_image",
}
FABRIC_OVERLAY_PRESETS = {
    "None": None,
    "Light mesh": FABRIC_OVERLAY_DIR / "light_mesh.png",
    "Subtle wrinkles": FABRIC_OVERLAY_DIR / "subtle_wrinkles.png",
    "Heavy wrinkles": FABRIC_OVERLAY_DIR / "heavy_wrinkles.png",
}


def _human_label(name: str) -> str:
    return name.replace("_", " ").title()


def _logo_type_label(name: str) -> str:
    labels = {
        "wrap_across_front_back_logo": "Wrap Logo",
        "front_left_chest_logo": "Left Chest Logo",
        "front_right_chest_logo": "Right Chest Logo",
        "front_center_chest_logo": "Center Chest Logo",
        "front_wordmark": "Front Wordmark",
        "back_neck_logo": "Back Neck Logo",
        "back_center_logo": "Back Center Logo",
        "shorts_belt_buckle_logo": "Belt Buckle Logo",
    }
    return labels.get(name, _human_label(name))


LOGO_CREATOR_TARGET_DISPLAY_ORDER = (
    "front_center_chest_logo",
    "front_left_chest_logo",
    "front_right_chest_logo",
    "front_wordmark",
    "wrap_across_front_back_logo",
    "back_neck_logo",
    "back_center_logo",
    "shorts_belt_buckle_logo",
)


class JerseyModderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{__app_name__} {__version__}")
        self.geometry("1180x760")
        self.minsize(980, 620)
        self.ui_thread = threading.current_thread()

        self.scan_result: IffScanResult | None = None
        self._pair_index: dict[str, TexturePair] = {}
        self._texture_row_index: dict[str, tuple[ResourceHit | None, ResourceHit | None]] = {}
        self._rdat_resource_index: dict[str, ResourceHit] = {}
        self.pending_replacements: dict[int, Replacement] = {}
        self.texture_file_overrides: dict[tuple[str, int, str], Path] = {}
        self.rdat_path: Path | None = None
        self.rdat_archive_entry: str | None = None
        self.rdat_encoding = "utf-8"
        self.rdat_dirty = False
        self.template_image_path: Path | None = None
        self.template_image: tk.PhotoImage | None = None
        self.template_original_size: tuple[int, int] | None = None
        self.template_zoom = 1.0
        self.template_zones: list[TemplateZone] = []
        self.template_drag_start: tuple[int, int] | None = None
        self.template_preview_id: int | None = None
        self.template_mouse_coord_var = tk.StringVar(value="Mouse: --")
        self.template_garment_var = tk.StringVar(value="Jersey")
        self.template_jersey_cut_var = tk.StringVar(value="Retro U")
        self.template_jersey_template_var = tk.StringVar(value="Jersey color")
        self.template_shorts_template_var = tk.StringVar(value="Retro shorts")
        self.zone_x_var = tk.IntVar(value=0)
        self.zone_y_var = tk.IntVar(value=0)
        self.zone_width_var = tk.IntVar(value=0)
        self.zone_height_var = tk.IntVar(value=0)
        self.zone_layer_var = tk.IntVar(value=10)
        self.generator_paths: dict[str, Path | None] = {
            "left_panel_image": None,
            "right_panel_image": None,
            "front_wordmark_image": None,
            "left_arm_hole_trim_image": None,
            "right_arm_hole_trim_image": None,
            "collar_trim_image": None,
        }
        self.generator_garment_var = tk.StringVar(value="Jersey")
        self.generator_jersey_cut_var = tk.StringVar(value="Retro U")
        self.generator_shorts_template_var = tk.StringVar(value="Retro shorts")
        self.generator_remove_white_var = tk.BooleanVar(value=False)
        self.generator_remove_black_var = tk.BooleanVar(value=False)
        self.generator_outside_only_var = tk.BooleanVar(value=True)
        self.generator_tolerance_var = tk.IntVar(value=32)
        self.front_wordmark_offset_x_var = tk.IntVar(value=0)
        self.front_wordmark_offset_y_var = tk.IntVar(value=0)
        self.front_wordmark_scale_var = tk.IntVar(value=100)
        self.generator_logo_placements: list[LogoPlacement] = []
        self.generator_trim_placements: dict[str, TrimPlacementSettings] = {}
        self.generator_logo_target_names: dict[str, str] = {}
        self.generator_logo_type_var = tk.StringVar(value="")
        self.generator_color_labels: dict[str, ttk.Label] = {}
        self.fabric_overlay_var = tk.StringVar(value="None")
        self.fabric_overlay_blend_var = tk.StringVar(value="multiply")
        self.fabric_overlay_opacity_var = tk.IntVar(value=0)
        self.web_editor_layer_order: list[str] = []
        self.web_editor_layer_cleanup: dict[str, BackgroundCleanupSettings] = {}
        self.custom_fabric_overlay_path: Path | None = None
        self.generated_texture_path: Path | None = None
        self.generated_preview_image: tk.PhotoImage | None = None
        self.generated_preview_base_image = None
        self.generator_preview_image_item: int | None = None
        self.texture_creator_preview_path: Path | None = None
        self.texture_creator_source_path: Path | None = None
        self.texture_creator_preview_image: tk.PhotoImage | None = None
        self.texture_creator_preview_info_var = tk.StringVar(value="No output generated.")
        self.texture_creator_garment_var = tk.StringVar(value="Jersey")
        self.texture_creator_jersey_cut_var = tk.StringVar(value="Retro U")
        self.texture_creator_shorts_template_var = tk.StringVar(value="Retro shorts")
        self.texture_creator_texture_type_var = tk.StringVar(value="Color Texture")
        self.texture_creator_source_var = tk.StringVar(value="Current generator design")
        self.texture_creator_normal_strength_var = tk.IntVar(value=15)
        self.texture_creator_normal_strength_label_var = tk.StringVar(value="15%")
        self.texture_creator_blender_normal_var = tk.BooleanVar(value=True)
        self.blender_preview_live_refresh = False
        self.blender_preview_refresh_after_id: str | None = None
        self.blender_preview_refresh_running = False
        self.generator_number_preview_image: tk.PhotoImage | None = None
        self.generator_number_preview_enabled_var = tk.BooleanVar(value=True)
        self.generator_number_preview_text_var = tk.StringVar(value="15")
        self.generator_number_preview_x_var = tk.IntVar(value=1160)
        self.generator_number_preview_y_var = tk.IntVar(value=780)
        self.generator_number_preview_scale_var = tk.IntVar(value=100)
        self.generator_uv_overlay_var = tk.BooleanVar(value=False)
        self.generator_uv_overlay_opacity_var = tk.IntVar(value=45)
        self.generator_uv_overlay_opacity_label_var = tk.StringVar(value="45%")
        self.generator_uv_overlay_image: tk.PhotoImage | None = None
        self.generator_uv_overlay_cache: dict | None = None
        self.generator_preview_rect: tuple[int, int, int, int] | None = None
        self.generator_preview_scale = 1.0
        self.generator_image_rects: dict[str, tuple[int, int, int, int]] = {}
        self.generator_drag_state: dict | None = None
        self.generator_selected_image_key: str | None = None
        self.generator_preview_refresh_after_id: str | None = None
        self.generator_preview_refresh_running = False
        self.generator_overlay_refresh_after_id: str | None = None
        self.texture_creator_refresh_after_id: str | None = None
        self.texture_creator_refresh_running = False
        self.web_editor_server: WebEditorServer | None = None
        self.trim_creator_image_path: Path | None = None
        self.trim_creator_preview_image: tk.PhotoImage | None = None
        self.trim_creator_strip_preview_image: tk.PhotoImage | None = None
        self.trim_creator_line_preview_path: Path | None = None
        self.trim_creator_current_strip_preview_path: Path | None = None
        self.trim_creator_results: list[TrimStrip] = []
        self.trim_creator_zoom = 1.0
        self.trim_creator_image_rect: tuple[int, int, int, int] | None = None
        self.trim_creator_line: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.trim_creator_pending_line_start: tuple[int, int] | None = None
        self.trim_creator_line_drag_start: tuple[int, int] | None = None
        self.trim_creator_line_drag_mode = "new"
        self.trim_creator_line_drag_original: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.trim_creator_target_var = tk.StringVar(value="collar_trim")
        self.trim_creator_nudge_target_var = tk.StringVar(value="Whole line")
        self.trim_creator_crop_top_var = tk.IntVar(value=0)
        self.trim_creator_crop_bottom_var = tk.IntVar(value=0)
        self.trim_creator_preview_bg_var = tk.StringVar(value="Black")
        self.trim_creator_upscale_var = tk.StringVar(value="2x")
        self.trim_creator_sharpen_var = tk.BooleanVar(value=True)
        self.trim_creator_zoom_label_var = tk.StringVar(value="100%")
        self.trim_library_target_var = tk.StringVar(value="collar_trim")
        self.trim_library_preview_image: tk.PhotoImage | None = None
        self.logo_creator_image_path: Path | None = None
        self.logo_creator_preview_image: tk.PhotoImage | None = None
        self.logo_creator_logo_preview_image: tk.PhotoImage | None = None
        self.logo_creator_image_rect: tuple[int, int, int, int] | None = None
        self.logo_creator_lasso_points: list[tuple[int, int]] = []
        self.logo_creator_drag_start: tuple[int, int] | None = None
        self.logo_creator_output_path: Path | None = None
        self.logo_creator_web_reference_path: Path | None = None
        self.logo_creator_preview_visible_var = tk.BooleanVar(value=False)
        self.logo_ai_staged_paths: list[tuple[str, Path]] = []
        self.logo_creator_type_var = tk.StringVar(value="")
        self.logo_creator_bg_var = tk.StringVar(value="Black")
        self.logo_creator_auto_bg_var = tk.BooleanVar(value=False)
        self.logo_creator_remove_white_var = tk.BooleanVar(value=False)
        self.logo_creator_remove_black_var = tk.BooleanVar(value=False)
        self.logo_creator_remove_sampled_color_var = tk.BooleanVar(value=False)
        self.logo_creator_sampled_color_var = tk.StringVar(value="#ffffff")
        self.logo_creator_pick_color_mode = False
        self.logo_creator_outside_only_var = tk.BooleanVar(value=True)
        self.logo_creator_tolerance_var = tk.IntVar(value=32)
        self.logo_creator_upscale_var = tk.StringVar(value="4x")
        self.logo_creator_canvas_size_var = tk.StringVar(value="1024 x 1024")
        self.logo_creator_sharpen_var = tk.BooleanVar(value=True)
        self.number_creator_digit_paths: dict[str, Path] = {}
        self.number_creator_original_digit_paths: dict[str, Path] = {}
        self.number_creator_digit_var = tk.StringVar(value="0")
        self.number_creator_auto_bg_var = tk.BooleanVar(value=True)
        self.number_creator_remove_white_var = tk.BooleanVar(value=True)
        self.number_creator_remove_black_var = tk.BooleanVar(value=False)
        self.number_creator_outside_only_var = tk.BooleanVar(value=True)
        self.number_creator_tolerance_var = tk.IntVar(value=32)
        self.number_creator_upscale_var = tk.StringVar(value="2x")
        self.number_creator_sharpen_var = tk.BooleanVar(value=True)
        self.number_creator_preview_image: tk.PhotoImage | None = None
        self.number_creator_sheet_path: Path | None = None
        self.number_creator_reference_path: Path | None = None
        self.number_creator_reference_preview_image: tk.PhotoImage | None = None
        self.number_creator_reference_rect: tuple[int, int, int, int] | None = None
        self.number_creator_reference_zoom = 1.0
        self.number_creator_reference_zoom_label_var = tk.StringVar(value="100%")
        self.number_creator_pick_mode_var = tk.StringVar(value="Box")
        self.number_creator_box_start: tuple[int, int] | None = None
        self.number_creator_box_end: tuple[int, int] | None = None
        self.number_creator_lasso_points: list[tuple[int, int]] = []
        self.number_creator_dragging = False
        self.number_creator_font_info: FontNumberTextureInfo | None = None
        self.number_creator_font_digit_centers: dict[str, tuple[float, float]] = {}
        self.number_creator_font_digit_bounds: dict[str, tuple[int, int, int, int]] = {}
        self.number_creator_font_status_var = tk.StringVar(value="No font IFF loaded")
        self.number_creator_nudge_x_var = tk.IntVar(value=0)
        self.number_creator_nudge_y_var = tk.IntVar(value=0)
        self.number_recolor_light_var = tk.StringVar(value="#ffffff")
        self.number_recolor_dark_var = tk.StringVar(value="#000000")
        self.number_recolor_no_light_var = tk.BooleanVar(value=True)
        self.number_recolor_no_dark_var = tk.BooleanVar(value=True)
        self.number_recolor_edge_protection_var = tk.IntVar(value=75)
        self.number_recolor_edge_protection_label_var = tk.StringVar(value="75%")
        self.number_recolor_outline_thickness_var = tk.IntVar(value=0)
        self.number_recolor_outline_thickness_label_var = tk.StringVar(value="0 px")
        self.tweak_file_path: Path | None = None
        self.tweak_info: FrontNumberTweak | None = None
        self.tweak_x_var = tk.DoubleVar(value=0.0)
        self.tweak_y_var = tk.DoubleVar(value=0.0)
        self.tweak_width_var = tk.DoubleVar(value=1.0)
        self.tweak_height_var = tk.DoubleVar(value=1.0)
        self.tweak_slider_vars: dict[str, tk.DoubleVar] = {
            "x": tk.DoubleVar(value=0.0),
            "y": tk.DoubleVar(value=0.0),
            "width": tk.DoubleVar(value=1.0),
            "height": tk.DoubleVar(value=1.0),
        }
        self.tweak_slider_ranges: dict[str, tuple[float, float]] = {
            "x": (-0.5, 0.5),
            "y": (-0.5, 0.5),
            "width": (1.0, 15.0),
            "height": (1.0, 20.0),
        }
        self.tweak_lock_size_var = tk.BooleanVar(value=False)
        self.tweak_locked_size_ratio = 1.0
        self.tweak_lock_syncing = False
        self.tweak_original_values: dict[str, float] = {}
        self.tweak_status_var = tk.StringVar(
            value="Load a clothing resource tweak .iff to edit the front number position."
        )
        self.tweak_value_vars: dict[str, tk.StringVar] = {
            "x": tk.StringVar(value="0.000000"),
            "y": tk.StringVar(value="0.000000"),
            "width": tk.StringVar(value="1.000000"),
            "height": tk.StringVar(value="1.000000"),
        }

        self._configure_style()
        self._build_menu()
        self._build_layout()

    def _configure_style(self) -> None:
        self.style = ttk.Style(self)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")
        self.style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        self.style.configure("Muted.TLabel", foreground="#5f6673")
        self.style.configure("Status.TLabel", foreground="#323842")

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Import .iff...", command=self.open_iff)
        file_menu.add_command(label="Open .rdat...", command=self.open_rdat)
        file_menu.add_command(label="Save .rdat", command=self.save_rdat)
        file_menu.add_command(label="Save .rdat As...", command=self.save_rdat_as)
        file_menu.add_separator()
        file_menu.add_command(
            label="Save Modified .iff As...",
            command=self.save_modified_iff_as,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        self.config(menu=menu)

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root)
        header.pack(fill=tk.X)

        title_block = ttk.Frame(header)
        title_block.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(title_block, text="NBA 2K Jersey Modder", style="Title.TLabel").pack(
            anchor=tk.W
        )
        self.file_label = ttk.Label(
            title_block,
            text="Import a jersey mod .iff file to inspect embedded resources.",
            style="Muted.TLabel",
        )
        self.file_label.pack(anchor=tk.W, pady=(4, 0))

        ttk.Button(header, text="Import .iff", command=self.open_iff).pack(side=tk.RIGHT)

        self.summary = ttk.Label(root, text="No file loaded.", style="Status.TLabel")
        self.summary.pack(anchor=tk.W, pady=(14, 10))

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        self._build_generator_tab()
        self._build_logo_creator_tab()
        self._build_trim_creator_tab()
        self._build_trim_library_tab()
        self._build_number_set_creator_tab()
        self._build_tweak_editor_tab()
        self._build_texture_creator_tab()
        self._build_rdat_tab()
        self._build_textures_tab()
        self._build_template_tab()
        self.after_idle(
            lambda: self.generate_jersey_preview(select_tab=False, update_status=False)
        )

    def _build_textures_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="IFF Textures")

        columns = ("dds", "txtr", "status", "dds_offset", "txtr_offset", "source")
        self.textures = ttk.Treeview(tab, columns=columns, show="headings")
        self.textures.heading("dds", text=".dds")
        self.textures.heading("txtr", text=".txtr")
        self.textures.heading("status", text="Match")
        self.textures.heading("dds_offset", text=".dds Offset")
        self.textures.heading("txtr_offset", text=".txtr Offset")
        self.textures.heading("source", text="Detected From")
        self.textures.column("dds", width=280, minwidth=180)
        self.textures.column("txtr", width=280, minwidth=180)
        self.textures.column("status", width=100, anchor=tk.CENTER)
        self.textures.column("dds_offset", width=120, anchor=tk.E)
        self.textures.column("txtr_offset", width=120, anchor=tk.E)
        self.textures.column("source", width=180)

        self.textures["displaycolumns"] = columns
        self.textures.bind("<Double-1>", self._open_texture_from_click)

        header = ttk.Frame(tab)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(header, text="Import .iff", command=self.open_iff).pack(side=tk.LEFT)

        toolbar = ttk.Frame(header)
        toolbar.pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="Open DDS", command=lambda: self.open_selected_texture("DDS")).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Open TXTR", command=lambda: self.open_selected_texture("TXTR")).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(
            toolbar,
            text="Import DDS Replacement",
            command=self.import_texture_replacement,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Save Modified .iff As",
            command=self.save_modified_iff_as,
        ).pack(side=tk.LEFT, padx=(8, 0))

        table_scroll_y = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.textures.yview)
        table_scroll_x = ttk.Scrollbar(tab, orient=tk.HORIZONTAL, command=self.textures.xview)
        self.textures.configure(
            yscrollcommand=table_scroll_y.set,
            xscrollcommand=table_scroll_x.set,
        )

        self.textures.grid(row=1, column=0, sticky="nsew")
        table_scroll_y.grid(row=1, column=1, sticky="ns")
        table_scroll_x.grid(row=2, column=0, sticky="ew")

        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

    def _build_template_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.template_tab = tab
        self.tabs.add(tab, text="Template Editor")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text="Master").pack(side=tk.LEFT)
        self.template_garment_box = ttk.Combobox(
            toolbar,
            textvariable=self.template_garment_var,
            values=("Jersey", "Shorts"),
            state="readonly",
            width=10,
        )
        self.template_garment_box.pack(side=tk.LEFT, padx=(6, 8))
        self.template_cut_slot = ttk.Frame(toolbar)
        self.template_cut_slot.pack(side=tk.LEFT, padx=(0, 8))
        self.template_jersey_cut_box = ttk.Combobox(
            self.template_cut_slot,
            textvariable=self.template_jersey_cut_var,
            values=JERSEY_CUT_OPTIONS,
            state="readonly",
            width=14,
        )
        self.template_shorts_template_box = ttk.Combobox(
            self.template_cut_slot,
            textvariable=self.template_shorts_template_var,
            values=tuple(SHORTS_TEMPLATE_OPTIONS),
            state="readonly",
            width=14,
        )
        self.template_map_label = ttk.Label(toolbar, text="Map")
        self.template_map_label.pack(side=tk.LEFT, padx=(0, 6))
        self.template_jersey_template_box = ttk.Combobox(
            toolbar,
            textvariable=self.template_jersey_template_var,
            values=tuple(JERSEY_TEMPLATE_OPTIONS),
            state="readonly",
            width=14,
        )
        self.template_jersey_template_box.pack(side=tk.LEFT, padx=(0, 8))
        self.template_garment_box.bind("<<ComboboxSelected>>", self._on_template_master_choice_changed)
        self.template_jersey_cut_box.bind(
            "<<ComboboxSelected>>",
            self._on_template_master_choice_changed,
        )
        self.template_jersey_template_box.bind(
            "<<ComboboxSelected>>",
            self._on_template_master_choice_changed,
        )
        self.template_shorts_template_box.bind(
            "<<ComboboxSelected>>",
            self._on_template_master_choice_changed,
        )
        self._sync_template_master_controls()
        ttk.Button(
            toolbar,
            text="Load Master Template",
            command=self.load_master_template,
        ).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Load Image", command=self.load_template_image).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Load Zones", command=self.load_template_zones).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save Zones", command=self.save_template_zones).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save Master", command=self.save_master_template_zones).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save UV Map", command=self.save_template_uv_map).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Fit", command=self.fit_template_to_view).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="100%", command=self.template_zoom_actual).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="-", command=lambda: self.adjust_template_zoom(0.8)).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="+", command=lambda: self.adjust_template_zoom(1.25)).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        self.template_status = ttk.Label(
            toolbar,
            text="Load a PNG/JPG template exported from Photoshop.",
            style="Muted.TLabel",
        )
        self.template_status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(16, 0))

        controls = ttk.Frame(tab)
        controls.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(controls, text="Zone name").grid(row=0, column=0, sticky=tk.W)
        self.zone_name_var = tk.StringVar(value="front_wordmark")
        ttk.Entry(controls, textvariable=self.zone_name_var).grid(
            row=1, column=0, sticky="ew", pady=(2, 8)
        )

        ttk.Label(controls, text="Zone type").grid(row=2, column=0, sticky=tk.W)
        self.zone_type_var = tk.StringVar(value="wordmark")
        ttk.Combobox(
            controls,
            textvariable=self.zone_type_var,
            values=(
                "base",
                "wordmark",
                "number",
                "name",
                "logo",
                "patch",
                "stripe",
                "trim",
                "pattern",
                "mask",
            ),
            state="readonly",
        ).grid(row=3, column=0, sticky="ew", pady=(2, 8))

        color_row = ttk.Frame(controls)
        color_row.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        self.zone_color_var = tk.StringVar(value="#ff3366")
        self.zone_color_swatch = tk.Label(
            color_row,
            text="",
            width=4,
            background=self.zone_color_var.get(),
            relief=tk.SOLID,
            borderwidth=1,
        )
        self.zone_color_swatch.pack(side=tk.LEFT)
        ttk.Button(color_row, text="Choose Color", command=self.choose_zone_color).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Entry(color_row, textvariable=self.zone_color_var, width=10).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(
            color_row,
            text="Create Zone From Hex",
            command=self.create_template_zone_from_hex,
        ).pack(side=tk.LEFT, padx=(8, 0))

        edit_frame = ttk.LabelFrame(controls, text="Selected zone", padding=8)
        edit_frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        for column, (label, variable) in enumerate(
            (
                ("X", self.zone_x_var),
                ("Y", self.zone_y_var),
                ("W", self.zone_width_var),
                ("H", self.zone_height_var),
                ("Layer", self.zone_layer_var),
            )
        ):
            ttk.Label(edit_frame, text=label).grid(row=0, column=column, sticky="w")
            tk.Spinbox(
                edit_frame,
                from_=-9999 if label in {"X", "Y"} else 1,
                to=9999,
                increment=1,
                width=6,
                textvariable=variable,
            ).grid(row=1, column=column, sticky="ew", padx=(0, 4))
            edit_frame.columnconfigure(column, weight=1)
        ttk.Button(
            edit_frame,
            text="Apply Zone Edits",
            command=self.apply_selected_template_zone_edits,
        ).grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 0))

        ttk.Button(
            controls,
            text="Delete Selected Zone",
            command=self.delete_selected_template_zone,
        ).grid(row=6, column=0, sticky="ew", pady=(0, 8))

        self.zone_list = ttk.Treeview(
            controls,
            columns=("type", "color", "layer", "x", "y", "w", "h"),
            show="tree headings",
            height=12,
        )
        self.zone_list.heading("#0", text="Zone")
        self.zone_list.heading("type", text="Type")
        self.zone_list.heading("color", text="Hex")
        self.zone_list.heading("layer", text="Layer")
        self.zone_list.heading("x", text="X")
        self.zone_list.heading("y", text="Y")
        self.zone_list.heading("w", text="W")
        self.zone_list.heading("h", text="H")
        self.zone_list.column("#0", width=130)
        self.zone_list.column("type", width=80)
        self.zone_list.column("color", width=76)
        self.zone_list.column("layer", width=55, anchor=tk.E)
        for column in ("x", "y", "w", "h"):
            self.zone_list.column(column, width=48, anchor=tk.E)
        self.zone_list.grid(row=7, column=0, sticky="nsew")
        self.zone_list.bind("<<TreeviewSelect>>", self._on_template_zone_select)
        self.zone_list.bind("<Double-1>", self._open_template_zone_popup_from_click)
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(7, weight=1)

        canvas_frame = ttk.Frame(tab)
        canvas_frame.grid(row=1, column=1, sticky="nsew")
        canvas_header = ttk.Frame(canvas_frame)
        canvas_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(
            canvas_header,
            textvariable=self.template_mouse_coord_var,
            style="Status.TLabel",
        ).pack(side=tk.LEFT)
        self.template_canvas = tk.Canvas(canvas_frame, background="#20242b")
        self.template_canvas.bind("<ButtonPress-1>", self._template_drag_start)
        self.template_canvas.bind("<B1-Motion>", self._template_drag_move)
        self.template_canvas.bind("<ButtonRelease-1>", self._template_drag_end)
        self.template_canvas.bind("<Motion>", self._update_template_mouse_coordinates)
        self.template_canvas.bind("<Leave>", self._clear_template_mouse_coordinates)
        self.template_canvas.bind("<Configure>", self._template_canvas_configured)
        y_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.VERTICAL, command=self.template_canvas.yview
        )
        x_scroll = ttk.Scrollbar(
            canvas_frame, orient=tk.HORIZONTAL, command=self.template_canvas.xview
        )
        self.template_canvas.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        self.template_canvas.grid(row=1, column=0, sticky="nsew")
        y_scroll.grid(row=1, column=1, sticky="ns")
        x_scroll.grid(row=2, column=0, sticky="ew")
        canvas_frame.rowconfigure(1, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        tab.columnconfigure(0, minsize=380)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

    def _build_trim_creator_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.trim_creator_tab = tab
        self.tabs.add(tab, text="Trim Creator")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Upload Jersey Mockup",
            command=self.load_trim_creator_mockup,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            toolbar,
            text="Stage Current Trim",
            command=self.generate_trim_creator_line_strip,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(toolbar, text="Target").grid(row=0, column=2, sticky="e", padx=(12, 4))
        ttk.Combobox(
            toolbar,
            textvariable=self.trim_creator_target_var,
            values=("collar_trim", "left_arm_hole_trim", "right_arm_hole_trim"),
            state="readonly",
            width=18,
        ).grid(row=0, column=3, sticky="ew")
        ttk.Button(
            toolbar,
            text="Zoom -",
            command=lambda: self.zoom_trim_creator_preview(0.67),
        ).grid(row=0, column=4, sticky="ew", padx=(12, 0))
        ttk.Label(toolbar, textvariable=self.trim_creator_zoom_label_var).grid(
            row=0,
            column=5,
            padx=(6, 0),
        )
        ttk.Button(
            toolbar,
            text="Zoom +",
            command=lambda: self.zoom_trim_creator_preview(1.5),
        ).grid(row=0, column=6, sticky="ew", padx=(6, 0))
        self.trim_creator_status = ttk.Label(
            toolbar,
            text="Upload a jersey mockup image to detect collar and armhole trim.",
            style="Muted.TLabel",
            wraplength=360,
        )
        self.trim_creator_status.grid(row=1, column=0, columnspan=7, sticky="ew", pady=(6, 0))
        toolbar.columnconfigure(3, weight=1)
        toolbar.bind(
            "<Configure>",
            lambda event: self.trim_creator_status.configure(
                wraplength=max(220, event.width - 20)
            ),
        )

        left = ttk.Frame(tab)
        left.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        trim_preview_panel = ttk.LabelFrame(left, text="Trim preview", padding=8)
        trim_preview_panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        preview_controls = ttk.Frame(trim_preview_panel)
        preview_controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(preview_controls, text="Background").pack(side=tk.RIGHT, padx=(8, 0))
        preview_bg = ttk.Combobox(
            preview_controls,
            textvariable=self.trim_creator_preview_bg_var,
            values=("Black", "White"),
            state="readonly",
            width=7,
        )
        preview_bg.pack(side=tk.RIGHT)
        preview_bg.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.update_trim_preview_background(),
        )
        self.trim_creator_strip_preview = tk.Canvas(
            trim_preview_panel,
            height=96,
            background=self._trim_preview_background_color(),
            highlightthickness=0,
        )
        self.trim_creator_strip_preview.grid(row=1, column=0, sticky="ew")
        trim_preview_panel.columnconfigure(0, weight=1)

        selected_actions = ttk.LabelFrame(left, text="Selected strip", padding=8)
        selected_actions.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        strip_actions = (
            ("Save As", self.save_selected_trim_strip_as),
            ("Remove", self.remove_selected_trim_strips),
            ("Preview / Crop", self.open_selected_trim_crop_editor),
            ("Use in Generator", self.use_selected_trim_strip_in_generator),
            ("Correct", self.correct_selected_trim_strip),
            ("Color Correct", self.open_selected_trim_color_corrector),
            ("Upscale", self.upscale_selected_trim_strip),
            ("Create AI Pack", self.create_trim_ai_reference_pack),
            ("Import AI Trim", self.import_ai_trim_strip),
        )
        for index, (label, command) in enumerate(strip_actions):
            row, column = divmod(index, 2)
            ttk.Button(selected_actions, text=label, command=command).grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 6, 0),
                pady=(0 if row == 0 else 6, 0),
            )
        selected_actions.columnconfigure(0, weight=1)
        selected_actions.columnconfigure(1, weight=1)

        staged_trims = ttk.LabelFrame(left, text="Staged Trims", padding=8)
        staged_trims.grid(row=2, column=0, sticky="nsew")
        self.trim_creator_list = ttk.Treeview(
            staged_trims,
            columns=("bbox", "file"),
            show="tree headings",
            height=18,
        )
        self.trim_creator_list.heading("#0", text="Trim")
        self.trim_creator_list.heading("bbox", text="Selection")
        self.trim_creator_list.heading("file", text="Strip PNG")
        self.trim_creator_list.column("#0", width=120, minwidth=80)
        self.trim_creator_list.column("bbox", width=110, minwidth=80)
        self.trim_creator_list.column("file", width=160, minwidth=110)
        self.trim_creator_list.grid(row=0, column=0, sticky="nsew")
        self.trim_creator_list.bind("<<TreeviewSelect>>", self._on_trim_creator_result_select)
        self.trim_creator_list.bind("<Double-1>", self._open_trim_creator_editor_from_click)
        self.trim_creator_list.bind("<Delete>", lambda _event: self.remove_selected_trim_strips())
        staged_trims.rowconfigure(0, weight=1)
        staged_trims.columnconfigure(0, weight=1)

        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        preview_frame = ttk.Frame(tab)
        preview_frame.grid(row=1, column=0, sticky="nsew")
        ttk.Button(
            preview_frame,
            text="Open Web Selector",
            command=self.open_trim_creator_web_selector,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.trim_creator_canvas = tk.Canvas(preview_frame, background="#20242b")
        self.trim_creator_canvas.configure(cursor="crosshair")
        self.trim_creator_canvas.grid(row=1, column=0, sticky="nsew")
        trim_v_scroll = ttk.Scrollbar(
            preview_frame,
            orient=tk.VERTICAL,
            command=self.trim_creator_canvas.yview,
        )
        trim_v_scroll.grid(row=1, column=1, sticky="ns")
        trim_h_scroll = ttk.Scrollbar(
            preview_frame,
            orient=tk.HORIZONTAL,
            command=self.trim_creator_canvas.xview,
        )
        trim_h_scroll.grid(row=2, column=0, sticky="ew")
        self.trim_creator_canvas.configure(
            xscrollcommand=trim_h_scroll.set,
            yscrollcommand=trim_v_scroll.set,
        )
        self.trim_creator_canvas.bind("<ButtonPress-1>", self._trim_creator_line_click)
        self.trim_creator_canvas.bind("<MouseWheel>", self._trim_creator_mousewheel_zoom)
        self.trim_creator_canvas.bind("<Left>", lambda _event: self.nudge_trim_creator_line(-1, 0))
        self.trim_creator_canvas.bind("<Right>", lambda _event: self.nudge_trim_creator_line(1, 0))
        self.trim_creator_canvas.bind("<Up>", lambda _event: self.nudge_trim_creator_line(0, -1))
        self.trim_creator_canvas.bind("<Down>", lambda _event: self.nudge_trim_creator_line(0, 1))
        self.trim_creator_canvas.bind(
            "<Configure>",
            lambda _event: self._show_trim_creator_preview(),
        )
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, minsize=340)
        tab.rowconfigure(1, weight=1)

    def _build_trim_library_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.trim_library_tab = tab
        self.tabs.add(tab, text="Trim Library")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Save Selected Trim",
            command=self.save_selected_trim_to_library,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Refresh",
            command=self.refresh_trim_library,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(toolbar, text="Apply to").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Combobox(
            toolbar,
            textvariable=self.trim_library_target_var,
            values=("collar_trim", "left_arm_hole_trim", "right_arm_hole_trim"),
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Apply to Generator",
            command=self.apply_selected_trim_library_item,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.trim_library_status = ttk.Label(
            toolbar,
            text="Saved trim strips are stored here for reuse.",
            style="Muted.TLabel",
        )
        self.trim_library_status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(16, 0))

        self.trim_library_list = ttk.Treeview(
            tab,
            columns=("file",),
            show="tree headings",
            height=18,
        )
        self.trim_library_list.heading("#0", text="Name")
        self.trim_library_list.heading("file", text="File")
        self.trim_library_list.column("#0", width=260, minwidth=180)
        self.trim_library_list.column("file", width=420, minwidth=220)
        self.trim_library_list.grid(row=1, column=0, sticky="nsew")
        self.trim_library_list.bind("<<TreeviewSelect>>", self._on_trim_library_select)
        self.trim_library_list.bind("<Double-1>", lambda _event: self.apply_selected_trim_library_item())

        preview_frame = ttk.LabelFrame(tab, text="Preview", padding=8)
        preview_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        preview_tools = ttk.Frame(preview_frame)
        preview_tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(preview_tools, text="Background").pack(side=tk.LEFT)
        preview_bg = ttk.Combobox(
            preview_tools,
            textvariable=self.trim_creator_preview_bg_var,
            values=("Black", "White"),
            state="readonly",
            width=8,
        )
        preview_bg.pack(side=tk.LEFT, padx=(8, 0))
        preview_bg.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._show_selected_trim_library_preview(),
        )
        self.trim_library_preview = tk.Canvas(preview_frame, background="#000000", height=220)
        self.trim_library_preview.grid(row=1, column=0, sticky="nsew")
        self.trim_library_preview.bind(
            "<Configure>",
            lambda _event: self._show_selected_trim_library_preview(),
        )
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, minsize=360, weight=1)
        tab.rowconfigure(1, weight=1)
        self.refresh_trim_library()

    def _build_logo_creator_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.logo_creator_tab = tab
        self.tabs.add(tab, text="Logo Creator")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Upload Reference",
            command=self.load_logo_creator_reference,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Refresh Logo Preview",
            command=self.update_logo_creator_preview,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Save Logo PNG As",
            command=self.save_logo_creator_png_as,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Send to Generator",
            command=self.send_logo_creator_to_generator,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.logo_creator_status = ttk.Label(
            toolbar,
            text="Upload a reference photo, then lasso around the logo.",
            style="Muted.TLabel",
        )
        self.logo_creator_status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(16, 0))

        left = ttk.Frame(tab)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        ttk.Button(
            left,
            text="Open Web Selector",
            command=self.open_logo_creator_web_selector,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        reference_frame = ttk.LabelFrame(left, text="Reference", padding=6)
        reference_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        canvas_frame = ttk.Frame(reference_frame)
        canvas_frame.grid(row=0, column=0, sticky="nsew")
        self.logo_creator_canvas = tk.Canvas(canvas_frame, background="#20242b")
        logo_y_scroll = ttk.Scrollbar(
            canvas_frame,
            orient=tk.VERTICAL,
            command=self.logo_creator_canvas.yview,
        )
        logo_x_scroll = ttk.Scrollbar(
            canvas_frame,
            orient=tk.HORIZONTAL,
            command=self.logo_creator_canvas.xview,
        )
        self.logo_creator_canvas.configure(
            yscrollcommand=logo_y_scroll.set,
            xscrollcommand=logo_x_scroll.set,
        )
        self.logo_creator_canvas.grid(row=0, column=0, sticky="nsew")
        logo_y_scroll.grid(row=0, column=1, sticky="ns")
        logo_x_scroll.grid(row=1, column=0, sticky="ew")
        self.logo_creator_canvas.bind("<ButtonPress-1>", self._logo_creator_lasso_start)
        self.logo_creator_canvas.bind("<B1-Motion>", self._logo_creator_lasso_move)
        self.logo_creator_canvas.bind("<ButtonRelease-1>", self._logo_creator_lasso_end)
        self.logo_creator_canvas.bind(
            "<Configure>",
            lambda _event: self._show_logo_creator_reference(),
        )
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        reference_frame.rowconfigure(0, weight=1)
        reference_frame.columnconfigure(0, weight=1)

        preview_controls = ttk.Frame(left)
        preview_controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.logo_creator_preview_toggle_button = ttk.Button(
            preview_controls,
            text="Show Preview",
            command=self.toggle_logo_creator_preview,
        )
        self.logo_creator_preview_toggle_button.pack(side=tk.LEFT)
        ttk.Label(preview_controls, text="Background").pack(side=tk.LEFT, padx=(12, 0))
        bg_choice = ttk.Combobox(
            preview_controls,
            textvariable=self.logo_creator_bg_var,
            values=("Black", "White", "Checker"),
            state="readonly",
            width=8,
        )
        bg_choice.pack(side=tk.LEFT, padx=(8, 0))
        bg_choice.bind("<<ComboboxSelected>>", lambda _event: self._show_logo_creator_logo_preview())

        logo_preview_frame = ttk.LabelFrame(left, text="Created Logo Preview", padding=6)
        logo_preview_frame.grid(row=3, column=0, sticky="nsew")
        self.logo_creator_logo_preview_frame = logo_preview_frame
        self.logo_creator_logo_preview = tk.Canvas(
            logo_preview_frame,
            height=320,
            background="#000000",
            highlightthickness=0,
        )
        self.logo_creator_logo_preview.grid(row=0, column=0, sticky="nsew")
        self.logo_creator_logo_preview.bind(
            "<Configure>",
            lambda _event: self._show_logo_creator_logo_preview(),
        )
        logo_preview_frame.rowconfigure(0, weight=1)
        logo_preview_frame.columnconfigure(0, weight=1)
        self._sync_logo_creator_preview_visibility()
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=0)
        left.columnconfigure(0, weight=1)

        side = ttk.Frame(tab)
        side.grid(row=1, column=1, sticky="nsew")
        ttk.Label(side, text="Logo type", style="Status.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 4),
        )
        logo_labels = self._logo_target_labels(include_front_wordmark=True)
        if logo_labels and not self.logo_creator_type_var.get():
            self.logo_creator_type_var.set(logo_labels[0])
        ttk.Combobox(
            side,
            textvariable=self.logo_creator_type_var,
            values=logo_labels,
            state="readonly",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        cleanup = ttk.LabelFrame(side, text="Cleanup", padding=8)
        cleanup.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ttk.Checkbutton(
            cleanup,
            text="Auto background",
            variable=self.logo_creator_auto_bg_var,
            command=self.update_logo_creator_preview,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            cleanup,
            text="Remove white",
            variable=self.logo_creator_remove_white_var,
            command=self.update_logo_creator_preview,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            cleanup,
            text="Remove black",
            variable=self.logo_creator_remove_black_var,
            command=self.update_logo_creator_preview,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        sampled_row = ttk.Frame(cleanup)
        sampled_row.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        ttk.Checkbutton(
            sampled_row,
            text="Remove sampled",
            variable=self.logo_creator_remove_sampled_color_var,
            command=self.update_logo_creator_preview,
        ).pack(side=tk.LEFT)
        self.logo_creator_sampled_color_swatch = tk.Label(
            sampled_row,
            text="",
            width=5,
            background=self.logo_creator_sampled_color_var.get(),
            relief=tk.SOLID,
            borderwidth=1,
        )
        self.logo_creator_sampled_color_swatch.pack(side=tk.RIGHT)
        ttk.Button(
            sampled_row,
            text="Copy",
            command=self.copy_logo_creator_sampled_hex,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        sampled_entry = ttk.Entry(
            sampled_row,
            width=9,
            textvariable=self.logo_creator_sampled_color_var,
        )
        sampled_entry.pack(side=tk.RIGHT, padx=(0, 8))
        sampled_entry.bind("<FocusOut>", lambda _event: self.normalize_logo_creator_sampled_hex())
        sampled_entry.bind("<Return>", lambda _event: self.normalize_logo_creator_sampled_hex())
        ttk.Button(
            sampled_row,
            text="Pick From Image",
            command=self.enable_logo_creator_color_dropper,
        ).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Checkbutton(
            cleanup,
            text="Outside only",
            variable=self.logo_creator_outside_only_var,
            command=self.update_logo_creator_preview,
        ).grid(row=4, column=0, sticky="w", pady=(4, 0))
        tolerance_row = ttk.Frame(cleanup)
        tolerance_row.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(tolerance_row, text="Tolerance").pack(side=tk.LEFT)
        tk.Spinbox(
            tolerance_row,
            from_=0,
            to=255,
            increment=1,
            width=6,
            textvariable=self.logo_creator_tolerance_var,
            command=self.update_logo_creator_preview,
        ).pack(side=tk.RIGHT)
        cleanup.columnconfigure(0, weight=1)

        upscale = ttk.LabelFrame(side, text="Upscale", padding=8)
        upscale.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        upscale_row = ttk.Frame(upscale)
        upscale_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(upscale_row, text="Output size").pack(side=tk.LEFT)
        upscale_choice = ttk.Combobox(
            upscale_row,
            textvariable=self.logo_creator_upscale_var,
            values=("1x", "2x", "4x"),
            state="readonly",
            width=6,
        )
        upscale_choice.pack(side=tk.RIGHT)
        upscale_choice.bind("<<ComboboxSelected>>", lambda _event: self.update_logo_creator_preview())
        ttk.Checkbutton(
            upscale,
            text="Sharpen after upscale",
            variable=self.logo_creator_sharpen_var,
            command=self.update_logo_creator_preview,
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        canvas_row = ttk.Frame(upscale)
        canvas_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(canvas_row, text="Canvas").pack(side=tk.LEFT)
        canvas_choice = ttk.Combobox(
            canvas_row,
            textvariable=self.logo_creator_canvas_size_var,
            values=("512 x 512", "1024 x 1024", "2048 x 2048"),
            state="readonly",
            width=12,
        )
        canvas_choice.pack(side=tk.RIGHT)
        canvas_choice.bind("<<ComboboxSelected>>", lambda _event: self.update_logo_creator_preview())
        upscale.columnconfigure(0, weight=1)

        ai = ttk.LabelFrame(side, text="Staged Logos", padding=8)
        ai.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(
            ai,
            text="Stage Current Logo",
            command=self.stage_current_logo_for_ai_pack,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            ai,
            text="Send Staged to Generator",
            command=self.send_staged_logos_to_generator,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            ai,
            text="Create AI Logo Pack",
            command=self.create_logo_ai_reference_pack,
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            ai,
            text="Import AI Logo",
            command=self.import_ai_logo_creator_png,
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.logo_ai_stage_list = ttk.Treeview(
            ai,
            columns=("type", "file"),
            show="headings",
            height=4,
        )
        self.logo_ai_stage_list.heading("type", text="Type")
        self.logo_ai_stage_list.heading("file", text="File")
        self.logo_ai_stage_list.column("type", width=120, minwidth=90)
        self.logo_ai_stage_list.column("file", width=160, minwidth=120)
        self.logo_ai_stage_list.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        stage_buttons = ttk.Frame(ai)
        stage_buttons.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            stage_buttons,
            text="Remove Selected",
            command=self.remove_selected_logo_ai_stage,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(
            stage_buttons,
            text="Clear",
            command=self.clear_logo_ai_stage,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        ttk.Label(
            ai,
            text="Stage several logo previews, then send them to Generator or export one AI pack.",
            style="Muted.TLabel",
            wraplength=300,
        ).grid(row=6, column=0, sticky="ew", pady=(8, 0))
        ai.columnconfigure(0, weight=1)

        side.columnconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, minsize=320)
        tab.rowconfigure(1, weight=1)

    def _build_number_set_creator_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.number_creator_tab = tab
        self.tabs.add(tab, text="Font Recolor")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Import Font IFF",
            command=self.import_number_font_iff,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Save Recolored Font IFF As",
            command=self.save_number_creator_back_to_font_iff,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.number_creator_status = ttk.Label(
            toolbar,
            text="Import a font .iff, recolor the existing numbers, then save a new font .iff.",
            style="Muted.TLabel",
        )
        self.number_creator_status.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(16, 0))

        side = ttk.Frame(tab)
        side.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        recolor = ttk.LabelFrame(side, text="Font Recolor", padding=8)
        recolor.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        light_row = ttk.Frame(recolor)
        light_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(light_row, text="Light / fill").pack(side=tk.LEFT)
        ttk.Checkbutton(
            light_row,
            text="No change",
            variable=self.number_recolor_no_light_var,
            command=self._refresh_number_recolor_swatches,
        ).pack(side=tk.LEFT, padx=(10, 0))
        self.number_recolor_light_swatch = tk.Label(light_row, width=3, background="#ffffff", relief=tk.SUNKEN)
        self.number_recolor_light_swatch.pack(side=tk.RIGHT)
        ttk.Button(
            light_row,
            text="Pick",
            command=lambda: self.choose_number_recolor_color("light"),
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Entry(light_row, textvariable=self.number_recolor_light_var, width=10).pack(side=tk.RIGHT)
        self.number_recolor_light_var.trace_add(
            "write",
            lambda *_args: self._on_number_recolor_hex_changed("light"),
        )

        edge_protection_row = ttk.Frame(recolor)
        edge_protection_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(edge_protection_row, text="Edge protection").pack(side=tk.LEFT)
        ttk.Label(
            edge_protection_row,
            textvariable=self.number_recolor_edge_protection_label_var,
            style="Muted.TLabel",
            width=5,
        ).pack(side=tk.RIGHT)
        ttk.Scale(
            edge_protection_row,
            from_=0,
            to=100,
            variable=self.number_recolor_edge_protection_var,
            command=self._on_number_recolor_edge_protection_changed,
        ).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 8))

        thickness_row = ttk.Frame(recolor)
        thickness_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(thickness_row, text="Outline thickness").pack(side=tk.LEFT)
        ttk.Label(
            thickness_row,
            textvariable=self.number_recolor_outline_thickness_label_var,
            style="Muted.TLabel",
            width=5,
        ).pack(side=tk.RIGHT)
        ttk.Scale(
            thickness_row,
            from_=0,
            to=3,
            variable=self.number_recolor_outline_thickness_var,
            command=self._on_number_recolor_outline_thickness_changed,
        ).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 8))

        dark_row = ttk.Frame(recolor)
        dark_row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(dark_row, text="Dark / outline").pack(side=tk.LEFT)
        ttk.Checkbutton(
            dark_row,
            text="No change",
            variable=self.number_recolor_no_dark_var,
            command=self._refresh_number_recolor_swatches,
        ).pack(side=tk.LEFT, padx=(10, 0))
        self.number_recolor_dark_swatch = tk.Label(dark_row, width=3, background="#000000", relief=tk.SUNKEN)
        self.number_recolor_dark_swatch.pack(side=tk.RIGHT)
        ttk.Button(
            dark_row,
            text="Pick",
            command=lambda: self.choose_number_recolor_color("dark"),
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Entry(dark_row, textvariable=self.number_recolor_dark_var, width=10).pack(side=tk.RIGHT)
        self.number_recolor_dark_var.trace_add(
            "write",
            lambda *_args: self._on_number_recolor_hex_changed("dark"),
        )
        action_row = ttk.Frame(recolor)
        action_row.grid(row=4, column=0, sticky="ew")
        ttk.Button(
            action_row,
            text="Apply Recolor",
            command=self.apply_number_font_recolor,
        ).pack(side=tk.LEFT)
        ttk.Button(
            action_row,
            text="Restore Original Colors",
            command=self.restore_number_font_original_colors,
        ).pack(side=tk.LEFT, padx=(8, 0))
        recolor.columnconfigure(0, weight=1)
        self._refresh_number_recolor_swatches()

        font_tools = ttk.LabelFrame(side, text="Font IFF", padding=8)
        font_tools.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            font_tools,
            textvariable=self.number_creator_font_status_var,
            style="Muted.TLabel",
            wraplength=330,
        ).grid(row=0, column=0, sticky="ew")
        font_tools.columnconfigure(0, weight=1)

        preview_frame = ttk.Frame(tab)
        preview_frame.grid(row=1, column=1, sticky="nsew")
        ttk.Label(
            preview_frame,
            text="Font preview",
            style="Status.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.number_creator_preview = tk.Canvas(
            preview_frame,
            background="#20242b",
            highlightthickness=0,
        )
        self.number_creator_preview.grid(row=1, column=0, sticky="nsew")
        preview_frame.rowconfigure(1, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        side.columnconfigure(0, weight=1)
        tab.columnconfigure(0, minsize=390)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

    def _build_tweak_editor_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tweak_editor_tab = tab
        self.tabs.add(tab, text="Tweak Editor")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            toolbar,
            text="Load Tweak IFF",
            command=self.load_tweak_iff,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar,
            text="Save Edited Tweak IFF As",
            command=self.save_tweak_iff_as,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            toolbar,
            text="Reset To Loaded Values",
            command=self.reset_tweak_values,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(
            tab,
            textvariable=self.tweak_status_var,
            style="Muted.TLabel",
            wraplength=820,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        options = ttk.Frame(tab)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(
            options,
            text="Lock width/height ratio",
            variable=self.tweak_lock_size_var,
            command=self.toggle_tweak_size_lock,
        ).pack(side=tk.LEFT)
        ttk.Label(
            options,
            text="Keeps the current number shape while resizing.",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(10, 0))

        controls = ttk.LabelFrame(tab, text="Front Jersey Number", padding=10)
        controls.grid(row=3, column=0, sticky="ew")
        self._add_tweak_control_row(
            controls,
            0,
            "X position",
            self.tweak_x_var,
            "x",
            -0.5,
            0.5,
            "Left moves left, right moves right.",
        )
        self._add_tweak_control_row(
            controls,
            1,
            "Y position",
            self.tweak_y_var,
            "y",
            -0.5,
            0.5,
            "Left moves down, right moves up.",
        )
        self._add_tweak_control_row(
            controls,
            2,
            "Width / size",
            self.tweak_width_var,
            "width",
            1.0,
            15.0,
            "Left is smaller, right is wider/bigger.",
        )
        self._add_tweak_control_row(
            controls,
            3,
            "Height / size",
            self.tweak_height_var,
            "height",
            1.0,
            20.0,
            "Left is smaller, right is taller/bigger.",
        )
        controls.columnconfigure(1, weight=1)

        info = ttk.LabelFrame(tab, text="Detected Fields", padding=10)
        info.grid(row=4, column=0, sticky="nsew", pady=(12, 0))
        columns = ("hash", "offset", "bounds")
        self.tweak_fields = ttk.Treeview(info, columns=columns, show="tree headings", height=5)
        self.tweak_fields.heading("#0", text="Control")
        self.tweak_fields.heading("hash", text="Hash")
        self.tweak_fields.heading("offset", text="Offset")
        self.tweak_fields.heading("bounds", text="Allowed Range")
        self.tweak_fields.column("#0", width=160)
        self.tweak_fields.column("hash", width=190)
        self.tweak_fields.column("offset", width=90, anchor=tk.E)
        self.tweak_fields.column("bounds", width=160)
        self.tweak_fields.grid(row=0, column=0, sticky="nsew")
        info.columnconfigure(0, weight=1)
        info.rowconfigure(0, weight=1)

        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(4, weight=1)

    def _add_tweak_control_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.DoubleVar,
        key: str,
        minimum: float,
        maximum: float,
        hint: str,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=(0, 8))
        scale = ttk.Scale(
            parent,
            from_=minimum,
            to=maximum,
            variable=self.tweak_slider_vars[key],
            command=lambda _value, current_key=key: self._on_tweak_slider_changed(current_key),
        )
        scale.grid(row=row, column=1, sticky="ew", padx=(10, 8), pady=(0, 8))
        entry = ttk.Entry(parent, textvariable=self.tweak_value_vars[key], width=12)
        entry.grid(row=row, column=2, sticky=tk.E, pady=(0, 8))
        entry.bind("<Return>", lambda _event, current_key=key: self.apply_tweak_entry(current_key))
        entry.bind("<FocusOut>", lambda _event, current_key=key: self.apply_tweak_entry(current_key))
        ttk.Label(parent, text=hint, style="Muted.TLabel").grid(
            row=row,
            column=3,
            sticky=tk.W,
            padx=(10, 0),
            pady=(0, 8),
        )

    def _build_generator_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.generator_tab = tab
        self.tabs.add(tab, text="Generator")

        controls_shell, controls = self._make_vertical_scroller(tab)
        controls_shell.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.generator_color_vars: dict[str, tk.StringVar] = {
            "front_color": tk.StringVar(value="#ffffff"),
            "back_color": tk.StringVar(value="#ffffff"),
            "left_panel_color": tk.StringVar(value=""),
            "right_panel_color": tk.StringVar(value=""),
            "collar_background_color": tk.StringVar(value="#ffffff"),
            "left_arm_hole_trim_color": tk.StringVar(value="#ffffff"),
            "right_arm_hole_trim_color": tk.StringVar(value="#ffffff"),
            "collar_trim_color": tk.StringVar(value="#ffffff"),
        }
        self.generator_file_labels: dict[str, ttk.Label] = {}
        self.generator_color_row_frames: dict[str, ttk.Frame] = {}
        self.generator_upload_row_frames: dict[str, ttk.Frame] = {}
        self.generator_jersey_only_widgets: list[tk.Widget] = []

        row = 0
        ttk.Label(controls, text="Template", style="Status.TLabel").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        row += 1
        template_frame = ttk.Frame(controls)
        template_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(template_frame, text="Type").grid(row=0, column=0, sticky=tk.W)
        self.generator_garment_box = ttk.Combobox(
            template_frame,
            textvariable=self.generator_garment_var,
            values=("Jersey", "Shorts"),
            state="readonly",
            width=12,
        )
        self.generator_garment_box.grid(row=0, column=1, sticky="ew", padx=(8, 12))
        self.generator_jersey_cut_label = ttk.Label(template_frame, text="Jersey")
        self.generator_jersey_cut_label.grid(row=0, column=2, sticky=tk.W)
        self.generator_jersey_cut_box = ttk.Combobox(
            template_frame,
            textvariable=self.generator_jersey_cut_var,
            values=JERSEY_CUT_OPTIONS,
            state="readonly",
            width=16,
        )
        self.generator_jersey_cut_box.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        self.generator_shorts_template_label = ttk.Label(template_frame, text="Shorts")
        self.generator_shorts_template_label.grid(row=0, column=2, sticky=tk.W)
        self.generator_shorts_template_box = ttk.Combobox(
            template_frame,
            textvariable=self.generator_shorts_template_var,
            values=tuple(SHORTS_TEMPLATE_OPTIONS),
            state="readonly",
            width=16,
        )
        self.generator_shorts_template_box.grid(row=0, column=3, sticky="ew", padx=(8, 0))
        self.generator_garment_box.bind("<<ComboboxSelected>>", self._on_generator_template_changed)
        self.generator_jersey_cut_box.bind(
            "<<ComboboxSelected>>",
            self._on_generator_template_changed,
        )
        self.generator_shorts_template_box.bind(
            "<<ComboboxSelected>>",
            self._on_generator_template_changed,
        )
        template_frame.columnconfigure(1, weight=1)
        template_frame.columnconfigure(3, weight=1)
        row += 1
        uv_overlay_frame = ttk.Frame(controls)
        uv_overlay_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        ttk.Checkbutton(
            uv_overlay_frame,
            text="UV overlay",
            variable=self.generator_uv_overlay_var,
            command=self._redraw_generator_preview_overlays,
        ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(uv_overlay_frame, text="Opacity").grid(
            row=0,
            column=1,
            sticky=tk.W,
            padx=(12, 6),
        )
        ttk.Scale(
            uv_overlay_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.generator_uv_overlay_opacity_var,
            command=self._on_generator_uv_overlay_opacity_changed,
        ).grid(row=0, column=2, sticky="ew")
        ttk.Label(
            uv_overlay_frame,
            textvariable=self.generator_uv_overlay_opacity_label_var,
            width=5,
        ).grid(row=0, column=3, sticky=tk.E, padx=(8, 0))
        uv_overlay_frame.columnconfigure(2, weight=1)
        row += 1

        ttk.Separator(controls).grid(row=row, column=0, sticky="ew", pady=12)
        row += 1
        self.generator_base_colors_label = ttk.Label(
            controls,
            text="Base colors",
            style="Status.TLabel",
        )
        self.generator_base_colors_label.grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        row += 1
        for key, label in (
            ("front_color", "Front"),
            ("back_color", "Back"),
            ("left_panel_color", "Left side panel"),
            ("right_panel_color", "Right side panel"),
            ("collar_background_color", "Collar background"),
        ):
            self._add_generator_color_row(controls, row, key, label)
            if key in {"front_color", "back_color"}:
                self.generator_jersey_only_widgets.append(self.generator_color_row_frames[key])
            row += 1

        trim_separator = ttk.Separator(controls)
        trim_separator.grid(row=row, column=0, sticky="ew", pady=12)
        self.generator_jersey_only_widgets.append(trim_separator)
        row += 1
        trim_label = ttk.Label(controls, text="Trim colors", style="Status.TLabel")
        trim_label.grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        self.generator_jersey_only_widgets.append(trim_label)
        row += 1
        for key, label in (
            ("left_arm_hole_trim_color", "Left arm hole"),
            ("right_arm_hole_trim_color", "Right arm hole"),
            ("collar_trim_color", "Collar trim"),
        ):
            self._add_generator_color_row(controls, row, key, label)
            self.generator_jersey_only_widgets.append(self.generator_color_row_frames[key])
            row += 1

        ttk.Separator(controls).grid(row=row, column=0, sticky="ew", pady=12)
        row += 1
        ttk.Label(controls, text="Images", style="Status.TLabel").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        row += 1
        for key, label in (
            ("front_wordmark_image", "Front wordmark image"),
            ("left_panel_image", "Left side panel image"),
            ("right_panel_image", "Right side panel image"),
            ("collar_trim_image", "Collar trim image"),
            ("left_arm_hole_trim_image", "Left arm hole image"),
            ("right_arm_hole_trim_image", "Right arm hole image"),
        ):
            self._add_generator_upload_row(controls, row, key, label)
            if key in {
                "front_wordmark_image",
                "left_arm_hole_trim_image",
                "right_arm_hole_trim_image",
                "collar_trim_image",
            }:
                self.generator_jersey_only_widgets.append(self.generator_upload_row_frames[key])
            row += 1

        ttk.Separator(controls).grid(row=row, column=0, sticky="ew", pady=12)
        row += 1
        ttk.Label(controls, text="Logos", style="Status.TLabel").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        row += 1
        self._build_logo_controls(controls, row)
        row += 1

        ttk.Separator(controls).grid(row=row, column=0, sticky="ew", pady=12)
        row += 1
        ttk.Label(controls, text="Fabric / wrinkle overlay", style="Status.TLabel").grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        row += 1
        self._build_fabric_overlay_controls(controls, row)
        row += 1

        number_separator = ttk.Separator(controls)
        number_separator.grid(row=row, column=0, sticky="ew", pady=12)
        self.generator_jersey_only_widgets.append(number_separator)
        row += 1
        number_label = ttk.Label(controls, text="Preview number", style="Status.TLabel")
        number_label.grid(
            row=row, column=0, sticky=tk.W, pady=(0, 8)
        )
        self.generator_jersey_only_widgets.append(number_label)
        row += 1
        self._build_generator_number_preview_controls(controls, row)
        self.generator_jersey_only_widgets.append(self.generator_number_preview_frame)
        row += 1

        ttk.Separator(controls).grid(row=row, column=0, sticky="ew", pady=12)
        row += 1
        ttk.Button(
            controls,
            text="Generate Preview",
            command=self.generate_jersey_preview,
        ).grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        ttk.Button(
            controls,
            text="Save Generated PNG As",
            command=self.save_generated_texture_as,
        ).grid(row=row, column=0, sticky="ew")
        row += 1
        ttk.Button(
            controls,
            text="Save DDS BC1 As",
            command=self.save_generated_dds_as,
        ).grid(row=row, column=0, sticky="ew", pady=(8, 0))
        row += 1
        ttk.Button(
            controls,
            text="Save Layered PSD As",
            command=self.save_layered_psd_as,
        ).grid(row=row, column=0, sticky="ew", pady=(8, 0))

        controls.columnconfigure(0, weight=1)

        preview_frame = ttk.Frame(tab)
        preview_frame.grid(row=0, column=1, sticky="nsew")
        ttk.Button(
            preview_frame,
            text="Open Web Editor",
            command=self.open_web_editor,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.generator_status = ttk.Label(
            preview_frame,
            text="Generate a first-draft jersey_color texture from the built-in master template.",
            style="Muted.TLabel",
        )
        self.generator_status.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.generator_preview = tk.Canvas(preview_frame, background="#20242b")
        self.generator_preview.bind("<ButtonPress-1>", self._generator_preview_press)
        self.generator_preview.bind("<B1-Motion>", self._generator_preview_drag)
        self.generator_preview.bind("<ButtonRelease-1>", self._generator_preview_release)
        self.generator_preview.grid(row=2, column=0, sticky="nsew")
        preview_frame.rowconfigure(2, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        tab.columnconfigure(0, minsize=430)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        self._sync_generator_template_controls(refresh_preview=False)

    def _build_texture_creator_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.texture_creator_tab = tab
        self.tabs.add(tab, text="Texture Creator")

        controls = ttk.Frame(tab)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ttk.Label(controls, text="Texture Creator", style="Title.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 6)
        )
        ttk.Label(
            controls,
            text="Build a normal texture or region texture from the generator, or bring an edited file back from Photoshop.",
            style="Muted.TLabel",
            wraplength=360,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 14))

        options = ttk.LabelFrame(controls, text="Setup", padding=10)
        options.grid(row=2, column=0, sticky="ew")
        ttk.Label(options, text="Garment").grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        garment = ttk.Combobox(
            options,
            textvariable=self.texture_creator_garment_var,
            values=("Jersey", "Shorts"),
            state="readonly",
            width=22,
        )
        garment.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=(0, 8))
        self.texture_creator_cut_label = ttk.Label(options, text="Jersey")
        self.texture_creator_cut_label.grid(row=1, column=0, sticky=tk.W, pady=(0, 8))
        self.texture_creator_jersey_cut_box = ttk.Combobox(
            options,
            textvariable=self.texture_creator_jersey_cut_var,
            values=JERSEY_CUT_OPTIONS,
            state="readonly",
            width=22,
        )
        self.texture_creator_jersey_cut_box.grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 8)
        )
        self.texture_creator_shorts_template_box = ttk.Combobox(
            options,
            textvariable=self.texture_creator_shorts_template_var,
            values=tuple(SHORTS_TEMPLATE_OPTIONS),
            state="readonly",
            width=22,
        )
        self.texture_creator_shorts_template_box.grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(0, 8)
        )
        ttk.Label(options, text="Texture").grid(row=2, column=0, sticky=tk.W, pady=(0, 8))
        texture_type = ttk.Combobox(
            options,
            textvariable=self.texture_creator_texture_type_var,
            values=("Color Texture", "Region Texture", "Normal Map"),
            state="readonly",
            width=22,
        )
        texture_type.grid(row=2, column=1, sticky="ew", padx=(10, 0), pady=(0, 8))
        ttk.Label(options, text="Source").grid(row=3, column=0, sticky=tk.W)
        source = ttk.Combobox(
            options,
            textvariable=self.texture_creator_source_var,
            values=("Current generator design", "Uploaded file"),
            state="readonly",
            width=22,
        )
        source.grid(row=3, column=1, sticky="ew", padx=(10, 0))
        texture_type.bind("<<ComboboxSelected>>", self._on_texture_creator_options_changed)
        source.bind("<<ComboboxSelected>>", self._on_texture_creator_options_changed)
        garment.bind("<<ComboboxSelected>>", self._on_texture_creator_template_changed)
        self.texture_creator_jersey_cut_box.bind(
            "<<ComboboxSelected>>",
            self._on_texture_creator_template_changed,
        )
        self.texture_creator_shorts_template_box.bind(
            "<<ComboboxSelected>>",
            self._on_texture_creator_template_changed,
        )
        options.columnconfigure(1, weight=1)
        self._sync_texture_creator_template_controls()

        normal_options = ttk.LabelFrame(controls, text="Normal map", padding=10)
        normal_options.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(normal_options, text="Logo strength").pack(side=tk.LEFT)
        ttk.Scale(
            normal_options,
            from_=0,
            to=100,
            variable=self.texture_creator_normal_strength_var,
            command=self._on_texture_creator_normal_strength_changed,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 8))
        ttk.Label(
            normal_options,
            textvariable=self.texture_creator_normal_strength_label_var,
            style="Muted.TLabel",
            width=5,
        ).pack(side=tk.RIGHT)
        ttk.Checkbutton(
            normal_options,
            text="Use in Blender preview",
            variable=self.texture_creator_blender_normal_var,
            command=self._on_texture_creator_blender_normal_changed,
        ).pack(side=tk.LEFT, padx=(12, 0))

        actions = ttk.Frame(controls)
        actions.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(
            actions,
            text="Create From Generator",
            command=self.create_texture_from_generator,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            actions,
            text="Upload PNG / DDS / PSD / PDS",
            command=self.upload_texture_creator_source,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            actions,
            text="Open Blender Preview",
            command=self.open_blender_preview,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            actions,
            text="Save PNG As",
            command=self.save_texture_creator_png_as,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            actions,
            text="Save DDS BC1 As",
            command=self.save_texture_creator_dds_as,
        ).grid(row=4, column=0, sticky="ew")
        actions.columnconfigure(0, weight=1)

        self.texture_creator_status = ttk.Label(
            controls,
            text="Create from the generator or upload an edited texture to preview and export.",
            style="Muted.TLabel",
            wraplength=360,
        )
        self.texture_creator_status.grid(row=5, column=0, sticky="ew", pady=(14, 0))

        preview_frame = ttk.Frame(tab)
        preview_frame.grid(row=0, column=1, sticky="nsew")
        ttk.Label(preview_frame, text="Output Preview", style="Status.TLabel").grid(
            row=0,
            column=0,
            sticky=tk.W,
            pady=(0, 4),
        )
        ttk.Label(
            preview_frame,
            textvariable=self.texture_creator_preview_info_var,
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.texture_creator_preview = tk.Canvas(preview_frame, background="#20242b")
        self.texture_creator_preview.grid(row=2, column=0, sticky="nsew")
        self.texture_creator_preview.bind(
            "<Configure>",
            lambda _event: self._show_texture_creator_preview(),
        )
        preview_frame.rowconfigure(2, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        controls.columnconfigure(0, weight=1)
        tab.columnconfigure(0, minsize=390)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

    def _make_vertical_scroller(
        self,
        parent: ttk.Frame,
    ) -> tuple[ttk.Frame, ttk.Frame]:
        shell = ttk.Frame(parent)
        canvas = tk.Canvas(shell, borderwidth=0, highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor=tk.NW)

        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)

        def update_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        def scroll_with_wheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content_width)
        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", scroll_with_wheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))

        return shell, content

    def _add_generator_color_row(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
    ) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self.generator_color_row_frames[key] = frame
        label_widget = ttk.Label(frame, text=label)
        label_widget.pack(side=tk.LEFT)
        self.generator_color_labels[key] = label_widget
        initial_color = self.generator_color_vars[key].get()
        swatch = tk.Label(
            frame,
            text="" if initial_color else "None",
            width=7,
            background=initial_color or "#f0f0f0",
            relief=tk.SOLID,
            borderwidth=1,
        )
        swatch.pack(side=tk.RIGHT)
        ttk.Button(
            frame,
            text="Pick",
            command=lambda: self.choose_generator_color(key, swatch),
        ).pack(side=tk.RIGHT, padx=(0, 8))
        entry = ttk.Entry(
            frame,
            width=10,
            textvariable=self.generator_color_vars[key],
        )
        entry.pack(side=tk.RIGHT, padx=(0, 8))
        entry.bind(
            "<FocusOut>",
            lambda _event: self.normalize_generator_color_entry(key, swatch),
        )
        entry.bind(
            "<Return>",
            lambda _event: self.normalize_generator_color_entry(key, swatch),
        )
        ttk.Button(
            frame,
            text="No Color",
            command=lambda: self.clear_generator_color(key, swatch),
        ).pack(side=tk.RIGHT, padx=(0, 8))

    def _add_generator_upload_row(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
    ) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self.generator_upload_row_frames[key] = frame
        ttk.Button(
            frame,
            text=label,
            command=lambda: self.upload_generator_image(key),
        ).pack(side=tk.LEFT)
        ttk.Button(
            frame,
            text="Clear",
            command=lambda: self.clear_generator_image(key),
        ).pack(side=tk.LEFT, padx=(8, 0))
        file_label = ttk.Label(frame, text="none", style="Muted.TLabel")
        file_label.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)
        self.generator_file_labels[key] = file_label

    def _current_generator_template_path(self) -> Path:
        if self.generator_garment_var.get() == "Shorts":
            _image_path, zones_path = SHORTS_TEMPLATE_OPTIONS.get(
                self.generator_shorts_template_var.get(),
                SHORTS_TEMPLATE_OPTIONS["Retro shorts"],
            )
            return zones_path
        return JERSEY_CUT_TEMPLATE_OPTIONS.get(
            self.generator_jersey_cut_var.get(),
            MASTER_TEMPLATE_ZONES,
        )

    def _current_generator_template_image_path(self) -> Path:
        if self.generator_garment_var.get() == "Shorts":
            image_path, _zones_path = SHORTS_TEMPLATE_OPTIONS.get(
                self.generator_shorts_template_var.get(),
                SHORTS_TEMPLATE_OPTIONS["Retro shorts"],
            )
            return image_path
        return JERSEY_CUT_IMAGE_OPTIONS.get(
            self.generator_jersey_cut_var.get(),
            MASTER_TEMPLATE_IMAGE,
        )

    def _current_generator_uv_map_path(self) -> Path:
        if self.generator_garment_var.get() == "Shorts":
            image_path = self._current_generator_template_image_path()
            return image_path.with_name(f"{image_path.stem}.uv.png")
        return JERSEY_CUT_UV_OPTIONS.get(
            self.generator_jersey_cut_var.get(),
            JERSEY_UV_TEMPLATE_IMAGE,
        )

    def _current_generator_template(self) -> JerseyTemplate:
        return load_template(self._current_generator_template_path())

    def _on_generator_template_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_generator_template_controls(refresh_preview=True)

    def _on_generator_uv_overlay_opacity_changed(self, _value: str | None = None) -> None:
        try:
            value = int(float(self.generator_uv_overlay_opacity_var.get()))
        except tk.TclError:
            value = 45
        value = max(0, min(100, value))
        self.generator_uv_overlay_opacity_var.set(value)
        self.generator_uv_overlay_opacity_label_var.set(f"{value}%")
        self._schedule_generator_overlay_redraw()

    def _schedule_generator_overlay_redraw(self) -> None:
        if self.generator_overlay_refresh_after_id is not None:
            self.after_cancel(self.generator_overlay_refresh_after_id)
        self.generator_overlay_refresh_after_id = self.after(
            35,
            self._run_scheduled_generator_overlay_redraw,
        )

    def _run_scheduled_generator_overlay_redraw(self) -> None:
        self.generator_overlay_refresh_after_id = None
        self._redraw_generator_preview_overlays()

    def _sync_generator_template_controls(self, *, refresh_preview: bool) -> None:
        is_shorts = self.generator_garment_var.get() == "Shorts"
        if is_shorts:
            self.generator_jersey_cut_label.grid_remove()
            self.generator_jersey_cut_box.grid_remove()
            self.generator_shorts_template_label.grid()
            self.generator_shorts_template_box.grid()
        else:
            self.generator_shorts_template_label.grid_remove()
            self.generator_shorts_template_box.grid_remove()
            self.generator_jersey_cut_label.grid()
            self.generator_jersey_cut_box.grid()
        self.generator_base_colors_label.configure(
            text="Shorts colors" if is_shorts else "Base colors"
        )
        for widget in self.generator_jersey_only_widgets:
            if is_shorts:
                widget.grid_remove()
            else:
                widget.grid()
        labels = {
            "front_color": "Front",
            "back_color": "Back",
            "left_panel_color": "Left side panel",
            "right_panel_color": "Right side panel",
            "collar_background_color": "Collar background",
            "left_arm_hole_trim_color": "Left arm hole",
            "right_arm_hole_trim_color": "Right arm hole",
            "collar_trim_color": "Collar trim",
        }
        if is_shorts:
            labels.update(
                {
                    "left_panel_color": "Left shorts panel",
                    "right_panel_color": "Right shorts panel",
                    "collar_background_color": "Waistband",
                }
            )
        for key, text in labels.items():
            label = self.generator_color_labels.get(key)
            if label is not None:
                label.configure(text=text)
        self._refresh_generator_logo_targets()
        if refresh_preview:
            self._schedule_generator_preview_refresh()

    def _refresh_generator_logo_targets(self) -> None:
        if not hasattr(self, "generator_logo_location_box"):
            return
        labels = self._logo_target_labels()
        self.generator_logo_location_box.configure(values=labels)
        if labels and self.generator_logo_type_var.get() not in labels:
            self.generator_logo_type_var.set(labels[0])

    def _logo_target_labels(self, *, include_front_wordmark: bool = False) -> list[str]:
        template = self._current_generator_template()
        targets = logo_target_zones(template)
        labels_by_target = {_logo_type_label(zone.name): zone.name for zone in targets}
        if include_front_wordmark:
            labels_by_target["Front Wordmark"] = "front_wordmark"
        self.generator_logo_target_names.update(labels_by_target)
        if not include_front_wordmark:
            return list(labels_by_target)
        order_by_target = {
            target: index
            for index, target in enumerate(LOGO_CREATOR_TARGET_DISPLAY_ORDER)
        }
        return sorted(
            labels_by_target,
            key=lambda label: (
                order_by_target.get(labels_by_target[label], len(order_by_target)),
                label,
            ),
        )

    def _build_logo_controls(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        labels = self._logo_target_labels()
        if labels:
            self.generator_logo_type_var.set(labels[0])

        picker = ttk.Frame(frame)
        picker.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(picker, text="Type").pack(side=tk.LEFT)
        self.generator_logo_location_box = ttk.Combobox(
            picker,
            textvariable=self.generator_logo_type_var,
            values=labels,
            state="readonly",
            width=24,
        )
        self.generator_logo_location_box.pack(side=tk.LEFT, padx=(8, 8), fill=tk.X, expand=True)
        ttk.Button(
            picker,
            text="Upload Logo",
            command=self.upload_generator_logo,
        ).pack(side=tk.RIGHT)

        self.generator_logo_list = ttk.Treeview(
            frame,
            columns=("location", "file"),
            show="headings",
            height=5,
        )
        self.generator_logo_list.heading("location", text="Type")
        self.generator_logo_list.heading("file", text="File")
        self.generator_logo_list.column("location", width=150, minwidth=120)
        self.generator_logo_list.column("file", width=220, minwidth=160)
        self.generator_logo_list.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        ttk.Button(
            frame,
            text="Remove Selected Logo",
            command=self.remove_selected_generator_logo,
        ).grid(row=2, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)

    def _build_generator_number_preview_controls(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        self.generator_number_preview_frame = frame
        ttk.Checkbutton(
            frame,
            text="Show",
            variable=self.generator_number_preview_enabled_var,
            command=self._redraw_generator_preview_overlays,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(frame, text="Number").grid(
            row=0,
            column=1,
            sticky="w",
            padx=(10, 4),
            pady=(0, 6),
        )
        number_entry = ttk.Entry(
            frame,
            width=6,
            textvariable=self.generator_number_preview_text_var,
        )
        number_entry.grid(row=0, column=2, sticky="w", pady=(0, 6))
        number_entry.bind("<Return>", lambda _event: self._redraw_generator_preview_overlays())
        number_entry.bind("<FocusOut>", lambda _event: self._redraw_generator_preview_overlays())

        for column, (label, variable, width) in enumerate(
            (
                ("X", self.generator_number_preview_x_var, 7),
                ("Y", self.generator_number_preview_y_var, 7),
                ("Scale %", self.generator_number_preview_scale_var, 6),
            )
        ):
            ttk.Label(frame, text=label).grid(row=1, column=column * 2, sticky="w")
            spinbox = tk.Spinbox(
                frame,
                from_=0 if label != "Scale %" else 5,
                to=2048 if label != "Scale %" else 500,
                increment=1 if label != "Scale %" else 5,
                width=width,
                textvariable=variable,
                command=self._redraw_generator_preview_overlays,
            )
            spinbox.grid(row=1, column=column * 2 + 1, sticky="w", padx=(4, 10))
            spinbox.bind("<Return>", lambda _event: self._redraw_generator_preview_overlays())
            spinbox.bind("<FocusOut>", lambda _event: self._redraw_generator_preview_overlays())
        ttk.Button(
            frame,
            text="Reset",
            command=self.reset_generator_number_preview,
        ).grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        ttk.Label(
            frame,
            text="Preview only - shown in Blender, not exported",
            style="Muted.TLabel",
        ).grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 0))
        frame.columnconfigure(5, weight=1)

    def _build_fabric_overlay_controls(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))

        preset_frame = ttk.Frame(frame)
        preset_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(preset_frame, text="Preset").pack(side=tk.LEFT)
        ttk.Combobox(
            preset_frame,
            textvariable=self.fabric_overlay_var,
            values=list(FABRIC_OVERLAY_PRESETS) + ["Custom upload"],
            state="readonly",
            width=20,
        ).pack(side=tk.LEFT, padx=(8, 8), fill=tk.X, expand=True)
        ttk.Button(
            preset_frame,
            text="Upload",
            command=self.upload_fabric_overlay,
        ).pack(side=tk.RIGHT)

        opacity_frame = ttk.Frame(frame)
        opacity_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(opacity_frame, text="Opacity").pack(side=tk.LEFT)
        tk.Scale(
            opacity_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.fabric_overlay_opacity_var,
            showvalue=True,
            length=180,
        ).pack(side=tk.LEFT, padx=(8, 8), fill=tk.X, expand=True)

        blend_frame = ttk.Frame(frame)
        blend_frame.grid(row=2, column=0, sticky="ew")
        ttk.Label(blend_frame, text="Blend").pack(side=tk.LEFT)
        ttk.Combobox(
            blend_frame,
            textvariable=self.fabric_overlay_blend_var,
            values=("multiply", "overlay", "normal"),
            state="readonly",
            width=12,
        ).pack(side=tk.LEFT, padx=(8, 0))
        frame.columnconfigure(0, weight=1)

    def open_trim_creator_web_selector(self) -> None:
        if self.trim_creator_image_path is None:
            messagebox.showinfo("Trim Creator", "Upload a jersey mockup first.")
            return
        try:
            if self.web_editor_server is None:
                self.web_editor_server = WebEditorServer(self)
            url = self.web_editor_server.start().rstrip("/") + "/trim"
            webbrowser.open(url)
            self.trim_creator_status.configure(text=f"Trim web selector opened at {url}")
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Trim web selector failed", str(exc))

    def _trim_creator_web_project(self) -> dict:
        if (
            self.trim_creator_image_path is None
            or not self.trim_creator_image_path.exists()
        ):
            return {
                "hasImage": False,
                "width": 0,
                "height": 0,
                "imageUrl": "/api/trim/mockup",
                "message": "No trim mockup is loaded.",
                "line": None,
            }
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Trim selector requires Pillow.") from exc
        with Image.open(self.trim_creator_image_path) as image:
            width, height = image.size
        line = None
        if self.trim_creator_line is not None:
            start, end = self.trim_creator_line
            line = {
                "start": {"x": start[0], "y": start[1]},
                "end": {"x": end[0], "y": end[1]},
            }
        return {
            "hasImage": True,
            "width": width,
            "height": height,
            "imageUrl": "/api/trim/mockup",
            "message": f"Loaded {self.trim_creator_image_path.name}",
            "line": line,
        }

    def _trim_creator_mockup_image(self) -> tuple[bytes, str]:
        if (
            self.trim_creator_image_path is None
            or not self.trim_creator_image_path.exists()
        ):
            raise FileNotFoundError("No trim mockup image is loaded.")
        return (
            self.trim_creator_image_path.read_bytes(),
            image_content_type(self.trim_creator_image_path),
        )

    def _trim_creator_web_line(self, payload: dict) -> None:
        def clean_point(raw: object) -> tuple[int, int]:
            if not isinstance(raw, dict):
                raise ValueError("Line point is missing.")
            x = int(round(float(raw.get("x", 0))))
            y = int(round(float(raw.get("y", 0))))
            return self._trim_creator_clamp_point((x, y))

        try:
            start = clean_point(payload.get("start"))
            end = clean_point(payload.get("end"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid trim line: {exc}") from exc
        if start == end:
            raise ValueError("Trim line points must be different.")
        self.trim_creator_line = (start, end)
        self.trim_creator_pending_line_start = None
        self.trim_creator_line_drag_start = None
        self.trim_creator_line_drag_original = None
        self.trim_creator_nudge_target_var.set("Whole line")
        self.refresh_trim_creator_line_preview()
        self._show_trim_creator_preview()
        self.trim_creator_status.configure(
            text=(
                "Received web trim line: "
                f"({start[0]}, {start[1]}) to ({end[0]}, {end[1]})."
            )
        )

    def _trim_creator_web_clear(self) -> None:
        self.clear_trim_creator_line()
        self.trim_creator_status.configure(text="Trim web line cleared.")

    def load_trim_creator_mockup(self) -> None:
        selected = filedialog.askopenfilename(
            title="Upload Jersey Mockup",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        self.trim_creator_image_path = Path(selected)
        self.trim_creator_results = []
        self.trim_creator_line = None
        self.trim_creator_pending_line_start = None
        self.trim_creator_line_drag_start = None
        self.trim_creator_line_preview_path = None
        self.trim_creator_crop_top_var.set(0)
        self.trim_creator_crop_bottom_var.set(0)
        self._clear_trim_creator_strip_preview()
        self.trim_creator_zoom = 1.0
        self.trim_creator_zoom_label_var.set("100%")
        self.trim_creator_list.delete(*self.trim_creator_list.get_children())
        self._show_trim_creator_preview()
        self.trim_creator_status.configure(text=f"Loaded mockup: {Path(selected).name}")
        self.tabs.select(self.trim_creator_tab)

    def generate_trim_creator_line_strip(self) -> None:
        if self.trim_creator_image_path is None:
            messagebox.showinfo("Trim Creator", "Upload a jersey mockup first.")
            return
        if self.trim_creator_line is None:
            messagebox.showinfo("Trim Creator", "Draw a sample line on the mockup first.")
            return
        if (
            self.trim_creator_pending_line_start is not None
            or self.trim_creator_line[0] == self.trim_creator_line[1]
        ):
            messagebox.showinfo("Trim Creator", "Click the second point before generating.")
            return
        target_name = self.trim_creator_target_var.get()
        output_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "trim_creator"
            / self.trim_creator_image_path.stem
        )
        output_path = output_dir / f"{target_name}_line_sample.png"
        try:
            self._write_trim_creator_line_strip(output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Line strip failed", str(exc))
            return
        bbox = (
            min(self.trim_creator_line[0][0], self.trim_creator_line[1][0]),
            min(self.trim_creator_line[0][1], self.trim_creator_line[1][1]),
            max(self.trim_creator_line[0][0], self.trim_creator_line[1][0]) + 1,
            max(self.trim_creator_line[0][1], self.trim_creator_line[1][1]) + 1,
        )
        result = TrimStrip(name=target_name, bbox=bbox, output_path=output_path)
        self.trim_creator_results = [
            existing
            for existing in self.trim_creator_results
            if not (
                existing.name == target_name
                and existing.output_path.name.endswith("_line_sample.png")
            )
        ]
        self.trim_creator_results.append(result)
        self._populate_trim_creator_results()
        self.trim_creator_list.selection_set(f"trim:{len(self.trim_creator_results) - 1}")
        self._show_trim_creator_preview()
        self.trim_creator_status.configure(text=f"Staged {_human_label(target_name)} from line.")

    def _write_trim_creator_line_strip(self, output_path: Path) -> None:
        if self.trim_creator_image_path is None or self.trim_creator_line is None:
            raise RuntimeError("Draw a sample line first.")
        create_trim_strip_from_line(
            self.trim_creator_image_path,
            output_path,
            self.trim_creator_line[0],
            self.trim_creator_line[1],
            crop_top=self._trim_creator_crop_top(),
            crop_bottom=self._trim_creator_crop_bottom(),
        )

    def refresh_trim_creator_line_preview(self) -> None:
        if (
            self.trim_creator_image_path is None
            or self.trim_creator_line is None
            or self.trim_creator_pending_line_start is not None
            or self.trim_creator_line[0] == self.trim_creator_line[1]
        ):
            self._clear_trim_creator_strip_preview()
            return
        preview_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "trim_creator"
            / self.trim_creator_image_path.stem
            / "_line_preview.png"
        )
        try:
            self._write_trim_creator_line_strip(preview_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            self.trim_creator_status.configure(text=f"Preview failed: {exc}")
            return
        self.trim_creator_line_preview_path = preview_path
        self._show_trim_creator_strip_preview(preview_path)

    def update_trim_preview_background(self) -> None:
        if not hasattr(self, "trim_creator_strip_preview"):
            return
        self.trim_creator_strip_preview.configure(
            background=self._trim_preview_background_color()
        )
        if (
            self.trim_creator_current_strip_preview_path is not None
            and self.trim_creator_current_strip_preview_path.exists()
        ):
            self._show_trim_creator_strip_preview(
                self.trim_creator_current_strip_preview_path
            )

    def _trim_preview_background_color(self) -> str:
        return "#ffffff" if self.trim_creator_preview_bg_var.get() == "White" else "#000000"

    def _trim_creator_preview_background(self) -> str:
        return self._trim_preview_background_color()

    def _show_trim_creator_strip_preview(self, path: Path) -> None:
        self.trim_creator_current_strip_preview_path = path
        self.trim_creator_strip_preview.update_idletasks()
        self.trim_creator_strip_preview.configure(
            background=self._trim_preview_background_color()
        )
        width = max(1, self.trim_creator_strip_preview.winfo_width() - 12)
        height = max(1, self.trim_creator_strip_preview.winfo_height() - 12)
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
            scale = min(width / image.width, height / image.height)
            preview_size = (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            )
            preview = image.resize(preview_size, Image.Resampling.NEAREST)
        self.trim_creator_strip_preview_image = ImageTk.PhotoImage(preview)
        self.trim_creator_strip_preview.delete("all")
        x = (self.trim_creator_strip_preview.winfo_width() - preview_size[0]) // 2
        y = (self.trim_creator_strip_preview.winfo_height() - preview_size[1]) // 2
        self.trim_creator_strip_preview.create_image(
            max(0, x),
            max(0, y),
            image=self.trim_creator_strip_preview_image,
            anchor=tk.NW,
        )

    def _clear_trim_creator_strip_preview(self) -> None:
        if hasattr(self, "trim_creator_strip_preview"):
            self.trim_creator_strip_preview.delete("all")
        self.trim_creator_strip_preview_image = None
        self.trim_creator_current_strip_preview_path = None

    def _trim_creator_crop_top(self) -> int:
        try:
            return max(-32, min(63, self.trim_creator_crop_top_var.get()))
        except tk.TclError:
            return 0

    def _trim_creator_crop_bottom(self) -> int:
        try:
            return max(-32, min(63, self.trim_creator_crop_bottom_var.get()))
        except tk.TclError:
            return 0

    def _populate_trim_creator_results(self) -> None:
        self.trim_creator_list.delete(*self.trim_creator_list.get_children())
        for index, result in enumerate(self.trim_creator_results):
            self.trim_creator_list.insert(
                "",
                tk.END,
                iid=f"trim:{index}",
                text=_human_label(result.name),
                values=(
                    f"{result.bbox[0]}, {result.bbox[1]}, {result.bbox[2]}, {result.bbox[3]}",
                    result.output_path.name,
                ),
            )

    def _on_trim_creator_result_select(self, _event: tk.Event | None = None) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            return
        if result.output_path.exists():
            self._show_trim_creator_strip_preview(result.output_path)

    def _open_trim_creator_editor_from_click(self, event: tk.Event) -> str:
        row = self.trim_creator_list.identify_row(event.y)
        if row:
            self.trim_creator_list.selection_set(row)
            self.trim_creator_list.focus(row)
            self.open_selected_trim_crop_editor()
        return "break"

    def _selected_trim_creator_result(self) -> TrimStrip | None:
        selected = self.trim_creator_list.selection()
        if not selected:
            return None
        index = int(selected[0].split(":")[1])
        if 0 <= index < len(self.trim_creator_results):
            return self.trim_creator_results[index]
        return None

    def _selected_trim_creator_indexes(self) -> list[int]:
        indexes: list[int] = []
        for item_id in self.trim_creator_list.selection():
            try:
                index = int(item_id.split(":")[1])
            except (IndexError, ValueError):
                continue
            if 0 <= index < len(self.trim_creator_results):
                indexes.append(index)
        return sorted(set(indexes))

    def remove_selected_trim_strips(self) -> str:
        indexes = self._selected_trim_creator_indexes()
        if not indexes:
            messagebox.showinfo("Trim Creator", "Select one or more trim strips first.")
            return "break"

        removed_count = len(indexes)
        next_index = min(indexes[0], max(0, len(self.trim_creator_results) - removed_count - 1))
        for index in reversed(indexes):
            del self.trim_creator_results[index]

        self._populate_trim_creator_results()
        self._clear_trim_creator_strip_preview()
        self._show_trim_creator_preview()

        if self.trim_creator_results:
            new_iid = f"trim:{next_index}"
            self.trim_creator_list.selection_set(new_iid)
            self.trim_creator_list.focus(new_iid)
            self.trim_creator_list.see(new_iid)

        label = "trim strip" if removed_count == 1 else "trim strips"
        self.trim_creator_status.configure(text=f"Removed {removed_count} {label} from the list.")
        return "break"

    def save_selected_trim_strip_as(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Creator", "Select a staged trim first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Save Trim Strip",
            defaultextension=".png",
            initialfile=result.output_path.name,
            filetypes=(("PNG files", "*.png"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            Path(selected).write_bytes(result.output_path.read_bytes())
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.trim_creator_status.configure(text=f"Saved trim strip to {selected}.")

    def create_trim_ai_reference_pack(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Creator", "Select a trim strip first.")
            return
        if not result.output_path.exists():
            messagebox.showerror("Trim Creator", "That trim image file is missing.")
            return
        selected = filedialog.askdirectory(title="Choose folder for AI trim reference pack")
        if not selected:
            return
        folder = Path(selected)
        reference_path = folder / f"{safe_filename(result.name)}_trim_reference.png"
        prompt_path = folder / "ai_trim_prompt.txt"
        try:
            shutil.copyfile(result.output_path, reference_path)
            prompt_path.write_text(
                self._trim_ai_prompt_text(result),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror("Trim AI Assist", str(exc))
            return
        self.trim_creator_status.configure(
            text=f"AI trim pack saved: {reference_path.name} and {prompt_path.name}."
        )

    def import_ai_trim_strip(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import AI Trim PNG",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        source = Path(selected)
        base = self._selected_trim_creator_result()
        trim_name = base.name if base is not None else self.trim_creator_target_var.get()
        bbox = base.bbox if base is not None else (0, 0, 0, 0)
        output_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "trim_creator"
            / "ai_imports"
        )
        output_path = _next_available_path(
            output_dir / f"{safe_filename(trim_name)}_ai_trim.png"
        )
        try:
            from PIL import Image
        except ImportError:
            messagebox.showerror("Trim AI Assist", "Importing AI trim requires Pillow.")
            return
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as opened:
                opened.convert("RGBA").save(output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Trim AI Assist", str(exc))
            return
        imported = TrimStrip(name=trim_name, bbox=bbox, output_path=output_path)
        self.trim_creator_results.append(imported)
        self._populate_trim_creator_results()
        new_iid = f"trim:{len(self.trim_creator_results) - 1}"
        self.trim_creator_list.selection_set(new_iid)
        self.trim_creator_list.see(new_iid)
        self._show_trim_creator_strip_preview(output_path)
        self.refresh_trim_library()
        self.trim_creator_status.configure(text=f"Imported AI trim: {output_path.name}.")

    def _trim_ai_prompt_text(self, result: TrimStrip) -> str:
        return "\n".join(
            [
                "Create a cleaner, higher-quality basketball jersey trim strip from the attached reference.",
                f"Trim type: {_human_label(result.name)}.",
                "Keep it as a perfectly straight horizontal trim strip.",
                "Preserve the exact stripe order, stripe thickness relationships, colors, outlines, and any subtle fabric texture.",
                "Even out gaps, wavy edges, compression artifacts, and blurry pixels without changing the design.",
                "Return a PNG with a true transparent background and alpha channel.",
                "Do not put the trim on white, black, gray, checkerboard, or any solid-color background.",
                "Keep the strip tileable/repeatable left-to-right so it can wrap around a collar or armhole.",
                "Do not place it on a jersey mockup. Only output the trim strip image.",
            ]
        )

    def correct_selected_trim_strip(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Corrector", "Select a trim strip first.")
            return
        output_path = result.output_path.with_name(
            f"{result.output_path.stem}_corrected.png"
        )
        try:
            correct_trim_strip(result.output_path, output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Trim correction failed", str(exc))
            return
        corrected = TrimStrip(
            name=result.name,
            bbox=result.bbox,
            output_path=output_path,
        )
        self.trim_creator_results.append(corrected)
        self._populate_trim_creator_results()
        new_iid = f"trim:{len(self.trim_creator_results) - 1}"
        self.trim_creator_list.selection_set(new_iid)
        self.trim_creator_list.see(new_iid)
        self._show_trim_creator_strip_preview(output_path)
        self.trim_creator_status.configure(
            text=f"Corrected {_human_label(result.name)} gaps and line edges."
        )

    def upscale_selected_trim_strip(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Creator", "Select a trim strip first.")
            return
        if not result.output_path.exists():
            messagebox.showerror("Trim Creator", "That trim image file is missing.")
            return
        factor = self._trim_creator_upscale_factor()
        if factor == 1:
            messagebox.showinfo("Trim Creator", "Choose 2x or 4x before upscaling.")
            return
        try:
            from PIL import Image

            from .generator import upscale_logo_image
        except ImportError as exc:
            messagebox.showerror("Trim upscale failed", str(exc))
            return
        output_path = _next_available_path(
            result.output_path.with_name(
                f"{result.output_path.stem}_upscaled_{factor}x.png"
            )
        )
        try:
            with Image.open(result.output_path) as opened:
                upscaled = upscale_logo_image(
                    opened.convert("RGBA"),
                    scale_factor=factor,
                    sharpen=self.trim_creator_sharpen_var.get(),
                )
            upscaled.save(output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Trim upscale failed", str(exc))
            return
        upscaled_result = TrimStrip(
            name=result.name,
            bbox=result.bbox,
            output_path=output_path,
        )
        self.trim_creator_results.append(upscaled_result)
        self._populate_trim_creator_results()
        new_iid = f"trim:{len(self.trim_creator_results) - 1}"
        self.trim_creator_list.selection_set(new_iid)
        self.trim_creator_list.see(new_iid)
        self._show_trim_creator_strip_preview(output_path)
        self.trim_creator_status.configure(
            text=f"Upscaled {_human_label(result.name)} to {upscaled.width} x {upscaled.height}."
        )

    def _trim_creator_upscale_factor(self) -> int:
        value = self.trim_creator_upscale_var.get().lower().strip()
        if value.startswith("4"):
            return 4
        if value.startswith("2"):
            return 2
        return 1

    def open_selected_trim_color_corrector(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Creator", "Select a trim strip first.")
            return
        if not result.output_path.exists():
            messagebox.showerror("Trim Creator", "That trim image file is missing.")
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            messagebox.showerror("Trim Color Corrector", "Color correction requires Pillow.")
            return

        with Image.open(result.output_path) as opened:
            source_image = opened.convert("RGBA")
        initial_color = _dominant_visible_color(source_image) or (255, 255, 255)

        dialog = tk.Toplevel(self)
        dialog.title(f"Color Correct - {_human_label(result.name)}")
        dialog.geometry("920x380")
        dialog.minsize(680, 320)
        dialog.transient(self)
        dialog.preview_image = None

        source_color_var = tk.StringVar(value=_rgb_to_hex(initial_color))
        replacement_color_var = tk.StringVar(value=_rgb_to_hex(initial_color))
        tolerance_var = tk.IntVar(value=24)
        background_var = tk.StringVar(value=self.trim_creator_preview_bg_var.get())

        controls = ttk.Frame(dialog, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        source_swatch = tk.Label(
            controls,
            width=7,
            background=source_color_var.get(),
            relief=tk.SOLID,
            borderwidth=1,
        )
        replacement_swatch = tk.Label(
            controls,
            width=7,
            background=replacement_color_var.get(),
            relief=tk.SOLID,
            borderwidth=1,
        )

        ttk.Label(controls, text="Source").pack(side=tk.LEFT)
        source_swatch.pack(side=tk.LEFT, padx=(6, 6))
        ttk.Button(
            controls,
            text="Pick",
            command=lambda: choose_color(source_color_var, source_swatch),
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(controls, text="New").pack(side=tk.LEFT)
        replacement_swatch.pack(side=tk.LEFT, padx=(6, 6))
        ttk.Button(
            controls,
            text="Pick",
            command=lambda: choose_color(replacement_color_var, replacement_swatch),
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(controls, text="Tolerance").pack(side=tk.LEFT)
        tolerance_spin = tk.Spinbox(
            controls,
            from_=0,
            to=255,
            increment=1,
            width=5,
            textvariable=tolerance_var,
        )
        tolerance_spin.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(controls, text="Background").pack(side=tk.LEFT)
        bg_choice = ttk.Combobox(
            controls,
            textvariable=background_var,
            values=("Black", "White"),
            state="readonly",
            width=7,
        )
        bg_choice.pack(side=tk.LEFT, padx=(6, 0))

        canvas = tk.Canvas(dialog, background="#000000", highlightthickness=0)
        canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        def color_tuple(value: str) -> tuple[int, int, int]:
            normalized = self._normalize_hex_color(value)
            if not normalized:
                return (255, 255, 255)
            return _hex_to_rgb(normalized)

        def tolerance_value() -> int:
            try:
                return max(0, min(255, int(tolerance_var.get())))
            except tk.TclError:
                return 24

        def corrected_image():
            return _replace_trim_color(
                source_image,
                color_tuple(source_color_var.get()),
                color_tuple(replacement_color_var.get()),
                tolerance_value(),
            )

        def choose_color(variable: tk.StringVar, swatch: tk.Label) -> None:
            selected = colorchooser.askcolor(color=variable.get(), parent=dialog)[1]
            if not selected:
                return
            variable.set(selected)
            swatch.configure(background=selected)
            update_preview()

        def update_preview(_event: tk.Event | None = None) -> None:
            canvas.update_idletasks()
            canvas.configure(
                background="#ffffff" if background_var.get() == "White" else "#000000"
            )
            image = corrected_image()
            width = max(1, canvas.winfo_width() - 20)
            height = max(1, canvas.winfo_height() - 20)
            scale = min(width / image.width, height / image.height)
            preview_size = (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            )
            preview = image.resize(preview_size, Image.Resampling.NEAREST)
            dialog.preview_image = ImageTk.PhotoImage(preview)
            canvas.delete("all")
            x = (canvas.winfo_width() - preview_size[0]) // 2
            y = (canvas.winfo_height() - preview_size[1]) // 2
            canvas.create_image(max(0, x), max(0, y), image=dialog.preview_image, anchor=tk.NW)

        def save_corrected_copy() -> None:
            output_path = _next_available_path(
                result.output_path.with_name(f"{result.output_path.stem}_color_corrected.png")
            )
            try:
                image = corrected_image()
                image.save(output_path)
            except Exception as exc:  # noqa: BLE001 - GUI boundary.
                messagebox.showerror("Color correction failed", str(exc), parent=dialog)
                return
            corrected_result = TrimStrip(
                name=result.name,
                bbox=result.bbox,
                output_path=output_path,
            )
            self.trim_creator_results.append(corrected_result)
            self._populate_trim_creator_results()
            new_iid = f"trim:{len(self.trim_creator_results) - 1}"
            self.trim_creator_list.selection_set(new_iid)
            self.trim_creator_list.see(new_iid)
            self._show_trim_creator_strip_preview(output_path)
            self.trim_creator_status.configure(
                text=f"Saved color corrected trim: {output_path.name}."
            )

        action_bar = ttk.Frame(dialog, padding=(10, 0, 10, 10))
        action_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(action_bar, text="Save Corrected Copy", command=save_corrected_copy).pack(
            side=tk.LEFT
        )
        ttk.Button(action_bar, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

        tolerance_spin.configure(command=update_preview)
        tolerance_spin.bind("<KeyRelease>", update_preview)
        bg_choice.bind("<<ComboboxSelected>>", update_preview)
        canvas.bind("<Configure>", update_preview)
        update_preview()

    def open_selected_trim_crop_editor(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Creator", "Select a trim strip first.")
            return
        if not result.output_path.exists():
            messagebox.showerror("Trim Creator", "That trim image file is missing.")
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            messagebox.showerror("Trim Creator", "Trim preview requires Pillow.")
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Trim Preview / Crop - {_human_label(result.name)}")
        dialog.geometry("920x360")
        dialog.minsize(680, 300)
        dialog.transient(self)
        dialog.preview_image = None
        dialog.preview_rect = None
        dialog.box_crop_start = None
        dialog.box_crop_end = None

        controls = ttk.Frame(dialog, padding=10)
        controls.pack(side=tk.TOP, fill=tk.X)

        crop_top_var = tk.IntVar(value=0)
        crop_bottom_var = tk.IntVar(value=0)
        bg_var = tk.StringVar(value=self.trim_creator_preview_bg_var.get())

        ttk.Label(controls, text=result.output_path.name, style="Status.TLabel").pack(
            side=tk.LEFT,
            padx=(0, 16),
        )
        ttk.Label(controls, text="Crop top").pack(side=tk.LEFT)
        top_spin = tk.Spinbox(
            controls,
            from_=-64,
            to=512,
            increment=1,
            width=6,
            textvariable=crop_top_var,
        )
        top_spin.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(controls, text="bottom").pack(side=tk.LEFT)
        bottom_spin = tk.Spinbox(
            controls,
            from_=-64,
            to=512,
            increment=1,
            width=6,
            textvariable=crop_bottom_var,
        )
        bottom_spin.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Label(controls, text="Background").pack(side=tk.LEFT)
        bg_choice = ttk.Combobox(
            controls,
            textvariable=bg_var,
            values=("Black", "White"),
            state="readonly",
            width=7,
        )
        bg_choice.pack(side=tk.LEFT, padx=(6, 12))

        canvas = tk.Canvas(
            dialog,
            background="#000000",
            highlightthickness=0,
        )
        canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        def crop_value(variable: tk.IntVar) -> int:
            try:
                return int(variable.get())
            except tk.TclError:
                return 0

        def background_color() -> str:
            return "#ffffff" if bg_var.get() == "White" else "#000000"

        def preview_source_image():
            with Image.open(result.output_path) as opened:
                return _crop_trim_image(
                    opened.convert("RGBA"),
                    crop_value(crop_top_var),
                    crop_value(crop_bottom_var),
                )

        def update_preview(_event: tk.Event | None = None) -> None:
            canvas.update_idletasks()
            canvas.configure(background=background_color())
            width = max(1, canvas.winfo_width() - 20)
            height = max(1, canvas.winfo_height() - 20)
            image = preview_source_image()
            scale = min(width / image.width, height / image.height)
            preview_size = (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            )
            preview = image.resize(preview_size, Image.Resampling.NEAREST)
            dialog.preview_image = ImageTk.PhotoImage(preview)
            canvas.delete("all")
            x = (canvas.winfo_width() - preview_size[0]) // 2
            y = (canvas.winfo_height() - preview_size[1]) // 2
            x = max(0, x)
            y = max(0, y)
            dialog.preview_rect = (x, y, preview_size[0], preview_size[1], image.width, image.height)
            canvas.create_image(x, y, image=dialog.preview_image, anchor=tk.NW)
            draw_box_crop()

        def event_to_crop_image(event: tk.Event) -> tuple[int, int] | None:
            if dialog.preview_rect is None:
                return None
            left, top, shown_width, shown_height, image_width, image_height = dialog.preview_rect
            canvas_x = canvas.canvasx(event.x)
            canvas_y = canvas.canvasy(event.y)
            if not (
                left <= canvas_x <= left + shown_width
                and top <= canvas_y <= top + shown_height
            ):
                return None
            image_x = round((canvas_x - left) * image_width / shown_width)
            image_y = round((canvas_y - top) * image_height / shown_height)
            return (
                max(0, min(image_width - 1, image_x)),
                max(0, min(image_height - 1, image_y)),
            )

        def image_to_canvas(point: tuple[int, int]) -> tuple[float, float]:
            if dialog.preview_rect is None:
                return (0, 0)
            left, top, shown_width, shown_height, image_width, image_height = dialog.preview_rect
            return (
                left + point[0] * shown_width / image_width,
                top + point[1] * shown_height / image_height,
            )

        def draw_box_crop() -> None:
            canvas.delete("box-crop")
            if dialog.box_crop_start is None or dialog.box_crop_end is None:
                return
            x1, y1 = image_to_canvas(dialog.box_crop_start)
            x2, y2 = image_to_canvas(dialog.box_crop_end)
            canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline="#ffd24a",
                width=2,
                tags="box-crop",
            )

        def box_crop_press(event: tk.Event) -> None:
            point = event_to_crop_image(event)
            if point is None:
                return
            dialog.box_crop_start = point
            dialog.box_crop_end = point
            draw_box_crop()

        def box_crop_drag(event: tk.Event) -> None:
            point = event_to_crop_image(event)
            if point is None or dialog.box_crop_start is None:
                return
            dialog.box_crop_end = point
            draw_box_crop()

        def box_crop_release(event: tk.Event) -> None:
            point = event_to_crop_image(event)
            if point is not None and dialog.box_crop_start is not None:
                dialog.box_crop_end = point
            draw_box_crop()

        def clear_box_crop() -> None:
            dialog.box_crop_start = None
            dialog.box_crop_end = None
            draw_box_crop()

        def selected_box_crop_image():
            if dialog.box_crop_start is None or dialog.box_crop_end is None:
                raise ValueError("Drag a crop box on the preview first.")
            source = preview_source_image()
            x1, y1 = dialog.box_crop_start
            x2, y2 = dialog.box_crop_end
            left = max(0, min(x1, x2))
            top = max(0, min(y1, y2))
            right = min(source.width, max(x1, x2) + 1)
            bottom = min(source.height, max(y1, y2) + 1)
            if right - left < 2 or bottom - top < 2:
                raise ValueError("Crop box is too small.")
            return source.crop((left, top, right, bottom))

        def append_trim_result(output_path: Path, status_text: str) -> None:
            cropped_result = TrimStrip(
                name=result.name,
                bbox=result.bbox,
                output_path=output_path,
            )
            self.trim_creator_results.append(cropped_result)
            self._populate_trim_creator_results()
            new_iid = f"trim:{len(self.trim_creator_results) - 1}"
            self.trim_creator_list.selection_set(new_iid)
            self.trim_creator_list.see(new_iid)
            self._show_trim_creator_strip_preview(output_path)
            self.trim_creator_status.configure(text=status_text)

        def save_cropped_copy() -> None:
            output_path = _next_available_path(
                result.output_path.with_name(f"{result.output_path.stem}_cropped.png")
            )
            try:
                cropped = preview_source_image()
                cropped.save(output_path)
            except Exception as exc:  # noqa: BLE001 - GUI boundary.
                messagebox.showerror("Crop failed", str(exc), parent=dialog)
                return
            append_trim_result(output_path, f"Saved cropped trim: {output_path.name}.")

        def save_box_cropped_copy() -> None:
            output_path = _next_available_path(
                result.output_path.with_name(f"{result.output_path.stem}_box_cropped.png")
            )
            try:
                selected_box_crop_image().save(output_path)
            except Exception as exc:  # noqa: BLE001 - GUI boundary.
                messagebox.showerror("Box crop failed", str(exc), parent=dialog)
                return
            append_trim_result(output_path, f"Saved box-cropped trim: {output_path.name}.")

        def correct_preview_copy() -> None:
            output_path = _next_available_path(
                result.output_path.with_name(f"{result.output_path.stem}_corrected.png")
            )
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                    temp_path = Path(tmp_file.name)
                with Image.open(result.output_path) as opened:
                    cropped = _crop_trim_image(
                        opened.convert("RGBA"),
                        crop_value(crop_top_var),
                        crop_value(crop_bottom_var),
                    )
                cropped.save(temp_path)
                correct_trim_strip(temp_path, output_path)
            except Exception as exc:  # noqa: BLE001 - GUI boundary.
                messagebox.showerror("Correction failed", str(exc), parent=dialog)
                return
            finally:
                if "temp_path" in locals():
                    temp_path.unlink(missing_ok=True)
            corrected_result = TrimStrip(
                name=result.name,
                bbox=result.bbox,
                output_path=output_path,
            )
            self.trim_creator_results.append(corrected_result)
            self._populate_trim_creator_results()
            new_iid = f"trim:{len(self.trim_creator_results) - 1}"
            self.trim_creator_list.selection_set(new_iid)
            self.trim_creator_list.see(new_iid)
            self._show_trim_creator_strip_preview(output_path)
            self.trim_creator_status.configure(
                text=f"Saved corrected trim: {output_path.name}."
            )

        action_bar = ttk.Frame(dialog, padding=(10, 0, 10, 10))
        action_bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(action_bar, text="Save Cropped Copy", command=save_cropped_copy).pack(
            side=tk.LEFT
        )
        ttk.Button(action_bar, text="Save Box Crop", command=save_box_cropped_copy).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(action_bar, text="Clear Box", command=clear_box_crop).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(action_bar, text="Even Lines + Save", command=correct_preview_copy).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(action_bar, text="Use in Generator", command=self.use_selected_trim_strip_in_generator).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(action_bar, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)

        for widget in (top_spin, bottom_spin):
            widget.configure(command=update_preview)
            widget.bind("<KeyRelease>", update_preview)
        bg_choice.bind("<<ComboboxSelected>>", update_preview)
        canvas.bind("<ButtonPress-1>", box_crop_press)
        canvas.bind("<B1-Motion>", box_crop_drag)
        canvas.bind("<ButtonRelease-1>", box_crop_release)
        canvas.bind("<Configure>", update_preview)
        update_preview()

    def use_selected_trim_strip_in_generator(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Creator", "Select a staged trim first.")
            return
        key = TRIM_GENERATOR_KEYS.get(result.name)
        if key is None:
            messagebox.showinfo("Trim Creator", "This staged trim has no generator slot.")
            return
        self.generator_paths[key] = result.output_path
        self.generator_file_labels[key].configure(text=result.output_path.name)
        self.generator_trim_placements[result.name] = TrimPlacementSettings()
        self.trim_creator_status.configure(
            text=f"Sent {_human_label(result.name)} to the Generator."
        )
        self.tabs.select(self.generator_tab)

    def refresh_trim_library(self) -> None:
        if not hasattr(self, "trim_library_list"):
            return
        TRIM_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        self.trim_library_list.delete(*self.trim_library_list.get_children())
        for path in sorted(TRIM_LIBRARY_DIR.glob("*.png")):
            self.trim_library_list.insert(
                "",
                tk.END,
                iid=str(path),
                text=path.stem.replace("_", " "),
                values=(path.name,),
            )
        self._clear_trim_library_preview()
        self._set_trim_library_status("Trim library refreshed.")

    def _set_trim_library_status(self, text: str) -> None:
        if hasattr(self, "trim_library_status"):
            self.trim_library_status.configure(text=text)
        if hasattr(self, "trim_creator_status"):
            self.trim_creator_status.configure(text=text)

    def save_selected_trim_to_library(self) -> None:
        result = self._selected_trim_creator_result()
        if result is None:
            messagebox.showinfo("Trim Library", "Select a generated trim strip first.")
            return
        name = simpledialog.askstring(
            "Save Trim",
            "Trim name:",
            initialvalue=result.output_path.stem.replace("_", " "),
            parent=self,
        )
        if not name:
            return
        TRIM_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        destination = TRIM_LIBRARY_DIR / f"{safe_filename(name).replace(' ', '_')}.png"
        try:
            shutil.copyfile(result.output_path, destination)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.refresh_trim_library()
        self._set_trim_library_status(f"Saved trim to library: {destination.name}.")

    def apply_selected_trim_library_item(self) -> None:
        path = self._selected_trim_library_path()
        if path is None:
            messagebox.showinfo("Trim Library", "Select a saved trim first.")
            return
        target_name = self.trim_library_target_var.get()
        key = TRIM_GENERATOR_KEYS.get(target_name)
        if key is None:
            return
        self.generator_paths[key] = path
        self.generator_file_labels[key].configure(text=path.name)
        self.generator_trim_placements[target_name] = TrimPlacementSettings()
        self._set_trim_library_status(f"Applied {path.name} to {_human_label(target_name)}.")
        self.generate_jersey_preview(select_tab=False, update_status=False)

    def _selected_trim_library_path(self) -> Path | None:
        if not hasattr(self, "trim_library_list"):
            return None
        selected = self.trim_library_list.selection()
        if not selected:
            return None
        path = Path(selected[0])
        return path if path.exists() else None

    def _on_trim_library_select(self, _event: tk.Event | None = None) -> None:
        self._show_selected_trim_library_preview()

    def _show_selected_trim_library_preview(self) -> None:
        path = self._selected_trim_library_path()
        if path is None:
            self._clear_trim_library_preview()
            return
        self._show_trim_library_preview(path)
        self._set_trim_library_status(f"Previewing {path.name}.")

    def _show_trim_library_preview(self, path: Path) -> None:
        if not hasattr(self, "trim_library_preview"):
            return
        self.trim_library_preview.update_idletasks()
        self.trim_library_preview.configure(background=self._trim_creator_preview_background())
        width = max(1, self.trim_library_preview.winfo_width() - 12)
        height = max(1, self.trim_library_preview.winfo_height() - 12)
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.trim_library_preview_image = tk.PhotoImage(file=str(path))
            self.trim_library_preview.delete("all")
            self.trim_library_preview.create_image(
                self.trim_library_preview.winfo_width() // 2,
                self.trim_library_preview.winfo_height() // 2,
                image=self.trim_library_preview_image,
                anchor=tk.CENTER,
            )
            return
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        scale = min(width / max(1, image.width), height / max(1, image.height), 1)
        preview_size = (
            max(1, round(image.width * scale)),
            max(1, round(image.height * scale)),
        )
        preview = image.resize(preview_size, Image.Resampling.LANCZOS)
        background = Image.new(
            "RGBA",
            preview_size,
            self._trim_creator_preview_background(),
        )
        background.alpha_composite(preview)
        self.trim_library_preview_image = ImageTk.PhotoImage(background)
        self.trim_library_preview.delete("all")
        self.trim_library_preview.create_image(
            self.trim_library_preview.winfo_width() // 2,
            self.trim_library_preview.winfo_height() // 2,
            image=self.trim_library_preview_image,
            anchor=tk.CENTER,
        )

    def _clear_trim_library_preview(self) -> None:
        if hasattr(self, "trim_library_preview"):
            self.trim_library_preview.delete("all")
            self.trim_library_preview.configure(background=self._trim_creator_preview_background())
            self.trim_library_preview.create_text(
                self.trim_library_preview.winfo_width() // 2,
                self.trim_library_preview.winfo_height() // 2,
                text="Select a saved trim to preview it.",
                fill="#9aa4b5",
                anchor=tk.CENTER,
            )
        self.trim_library_preview_image = None

    def _show_trim_creator_preview(self) -> None:
        if self.trim_creator_image_path is None:
            return
        self.trim_creator_canvas.update_idletasks()
        canvas_width = max(1, self.trim_creator_canvas.winfo_width())
        canvas_height = max(1, self.trim_creator_canvas.winfo_height())
        target_width = max(1, canvas_width - 20)
        target_height = max(1, canvas_height - 20)
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.trim_creator_preview_image = load_scaled_photo_image(
                self.trim_creator_image_path,
                target_width,
                target_height,
            )
            shown_width = target_width
            shown_height = target_height
        else:
            with Image.open(self.trim_creator_image_path) as opened:
                image = opened.convert("RGBA")
                fit_scale = min(target_width / image.width, target_height / image.height)
                scale = fit_scale * self.trim_creator_zoom
                shown_width = max(1, round(image.width * scale))
                shown_height = max(1, round(image.height * scale))
                preview = image.resize((shown_width, shown_height), Image.Resampling.LANCZOS)
            self.trim_creator_preview_image = ImageTk.PhotoImage(preview)
        self.trim_creator_canvas.delete("all")
        left = max(10, (canvas_width - shown_width) // 2)
        top = max(10, (canvas_height - shown_height) // 2)
        self.trim_creator_image_rect = (left, top, shown_width, shown_height)
        self.trim_creator_canvas.create_image(
            left,
            top,
            image=self.trim_creator_preview_image,
            anchor=tk.NW,
        )
        scroll_right = max(canvas_width, left + shown_width + 10)
        scroll_bottom = max(canvas_height, top + shown_height + 10)
        self.trim_creator_canvas.configure(scrollregion=(0, 0, scroll_right, scroll_bottom))
        self._draw_trim_creator_boxes(left, top, shown_width, shown_height)
        self._draw_trim_creator_line()

    def zoom_trim_creator_preview(self, factor: float) -> None:
        self.trim_creator_zoom = max(0.35, min(16.0, self.trim_creator_zoom * factor))
        self.trim_creator_zoom_label_var.set(f"{round(self.trim_creator_zoom * 100)}%")
        self._show_trim_creator_preview()

    def _trim_creator_mousewheel_zoom(self, event: tk.Event) -> str:
        factor = 1.18 if event.delta > 0 else 1 / 1.18
        self.zoom_trim_creator_preview(factor)
        return "break"

    def nudge_trim_creator_line(self, dx: int, dy: int) -> str:
        if self.trim_creator_line is None:
            return "break"
        start, end = self.trim_creator_line
        target = self.trim_creator_nudge_target_var.get()
        if target == "Start point":
            start = self._trim_creator_clamp_point((start[0] + dx, start[1] + dy))
        elif target == "End point":
            end = self._trim_creator_clamp_point((end[0] + dx, end[1] + dy))
        else:
            start = self._trim_creator_clamp_point((start[0] + dx, start[1] + dy))
            end = self._trim_creator_clamp_point((end[0] + dx, end[1] + dy))
        self.trim_creator_line = (start, end)
        self._show_trim_creator_preview()
        self.refresh_trim_creator_line_preview()
        return "break"

    def clear_trim_creator_line(self) -> None:
        self.trim_creator_line = None
        self.trim_creator_pending_line_start = None
        self.trim_creator_line_drag_start = None
        self.trim_creator_line_drag_original = None
        self.trim_creator_line_preview_path = None
        self._clear_trim_creator_strip_preview()
        self._show_trim_creator_preview()

    def _draw_trim_creator_boxes(
        self,
        image_left: int,
        image_top: int,
        shown_width: int,
        shown_height: int,
    ) -> None:
        if self.trim_creator_image_path is None or not self.trim_creator_results:
            return
        try:
            from PIL import Image
        except ImportError:
            return
        with Image.open(self.trim_creator_image_path) as image:
            original_width, original_height = image.size
        scale_x = shown_width / original_width
        scale_y = shown_height / original_height
        colors = {
            "collar_trim": "#ffcc33",
            "left_arm_hole_trim": "#31d0ff",
            "right_arm_hole_trim": "#49e36d",
        }
        for result in self.trim_creator_results:
            left, top, right, bottom = result.bbox
            x1 = image_left + left * scale_x
            y1 = image_top + top * scale_y
            x2 = image_left + right * scale_x
            y2 = image_top + bottom * scale_y
            color = colors.get(result.name, "#ffcc33")
            self.trim_creator_canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline=color,
                width=2,
            )
            self.trim_creator_canvas.create_text(
                x1 + 4,
                y1 - 10,
                text=_human_label(result.name),
                fill=color,
                anchor=tk.W,
            )

    def _draw_trim_creator_line(self) -> None:
        if self.trim_creator_line is None or self.trim_creator_image_rect is None:
            return
        start, end = self.trim_creator_line
        x1, y1 = self._trim_creator_image_to_canvas(start[0], start[1])
        x2, y2 = self._trim_creator_image_to_canvas(end[0], end[1])
        self.trim_creator_canvas.create_line(
            x1,
            y1,
            x2,
            y2,
            fill="#ffcc33",
            width=3,
            tags=("trim_line",),
        )
        for x, y in ((x1, y1), (x2, y2)):
            self.trim_creator_canvas.create_oval(
                x - 5,
                y - 5,
                x + 5,
                y + 5,
                fill="#ffcc33",
                outline="#11141a",
                width=1,
                tags=("trim_line",),
            )

    def _trim_creator_line_click(self, event: tk.Event) -> None:
        self.trim_creator_canvas.focus_set()
        point = self._trim_creator_event_to_image(event)
        if point is None:
            return
        if self.trim_creator_pending_line_start is None:
            self.trim_creator_pending_line_start = point
            self.trim_creator_line = (point, point)
            self._clear_trim_creator_strip_preview()
            self.trim_creator_status.configure(text="First point set. Click the second point.")
        else:
            self.trim_creator_line = (self.trim_creator_pending_line_start, point)
            self.trim_creator_pending_line_start = None
            self.trim_creator_nudge_target_var.set("Whole line")
            self.refresh_trim_creator_line_preview()
            self.trim_creator_status.configure(text="Sample line set. Generate from line or nudge it.")
        self._show_trim_creator_preview()

    def _trim_creator_line_start(self, event: tk.Event) -> None:
        self.trim_creator_canvas.focus_set()
        point = self._trim_creator_event_to_image(event)
        if point is None:
            return
        self.trim_creator_line_drag_mode = self._trim_creator_hit_line_part(event)
        self.trim_creator_line_drag_start = point
        self.trim_creator_line_drag_original = self.trim_creator_line
        if self.trim_creator_line_drag_mode == "new" or self.trim_creator_line is None:
            self.trim_creator_line = (point, point)
        self._show_trim_creator_preview()

    def _trim_creator_line_drag(self, event: tk.Event) -> None:
        if self.trim_creator_line_drag_start is None:
            return
        point = self._trim_creator_event_to_image(event)
        if point is None:
            return
        original = self.trim_creator_line_drag_original
        mode = self.trim_creator_line_drag_mode
        if mode == "start" and original is not None:
            self.trim_creator_line = (point, original[1])
            self.trim_creator_nudge_target_var.set("Start point")
        elif mode == "end" and original is not None:
            self.trim_creator_line = (original[0], point)
            self.trim_creator_nudge_target_var.set("End point")
        elif mode == "line" and original is not None:
            dx = point[0] - self.trim_creator_line_drag_start[0]
            dy = point[1] - self.trim_creator_line_drag_start[1]
            self.trim_creator_line = (
                self._trim_creator_clamp_point((original[0][0] + dx, original[0][1] + dy)),
                self._trim_creator_clamp_point((original[1][0] + dx, original[1][1] + dy)),
            )
            self.trim_creator_nudge_target_var.set("Whole line")
        else:
            self.trim_creator_line = (self.trim_creator_line_drag_start, point)
        self._show_trim_creator_preview()

    def _trim_creator_line_end(self, event: tk.Event) -> None:
        if self.trim_creator_line_drag_start is None:
            return
        point = self._trim_creator_event_to_image(event)
        if point is not None:
            self._trim_creator_line_drag(event)
        self.trim_creator_line_drag_start = None
        self.trim_creator_line_drag_original = None
        self._show_trim_creator_preview()

    def _trim_creator_hit_line_part(self, event: tk.Event) -> str:
        if self.trim_creator_line is None:
            return "new"
        canvas_x = self.trim_creator_canvas.canvasx(event.x)
        canvas_y = self.trim_creator_canvas.canvasy(event.y)
        start, end = self.trim_creator_line
        start_x, start_y = self._trim_creator_image_to_canvas(start[0], start[1])
        end_x, end_y = self._trim_creator_image_to_canvas(end[0], end[1])
        if _distance(canvas_x, canvas_y, start_x, start_y) <= 12:
            return "start"
        if _distance(canvas_x, canvas_y, end_x, end_y) <= 12:
            return "end"
        if _point_to_segment_distance(canvas_x, canvas_y, start_x, start_y, end_x, end_y) <= 8:
            return "line"
        return "new"

    def _trim_creator_event_to_image(self, event: tk.Event) -> tuple[int, int] | None:
        if self.trim_creator_image_rect is None or self.trim_creator_image_path is None:
            return None
        try:
            from PIL import Image
        except ImportError:
            return None
        with Image.open(self.trim_creator_image_path) as image:
            original_width, original_height = image.size
        canvas_x = self.trim_creator_canvas.canvasx(event.x)
        canvas_y = self.trim_creator_canvas.canvasy(event.y)
        image_left, image_top, shown_width, shown_height = self.trim_creator_image_rect
        if shown_width <= 0 or shown_height <= 0:
            return None
        x = round((canvas_x - image_left) * original_width / shown_width)
        y = round((canvas_y - image_top) * original_height / shown_height)
        x = max(0, min(original_width - 1, x))
        y = max(0, min(original_height - 1, y))
        return x, y

    def _trim_creator_clamp_point(self, point: tuple[int, int]) -> tuple[int, int]:
        if self.trim_creator_image_path is None:
            return point
        try:
            from PIL import Image
        except ImportError:
            return point
        with Image.open(self.trim_creator_image_path) as image:
            width, height = image.size
        return (
            max(0, min(width - 1, point[0])),
            max(0, min(height - 1, point[1])),
        )

    def _trim_creator_image_to_canvas(self, x: int, y: int) -> tuple[float, float]:
        if self.trim_creator_image_rect is None or self.trim_creator_image_path is None:
            return 0.0, 0.0
        try:
            from PIL import Image
        except ImportError:
            return 0.0, 0.0
        with Image.open(self.trim_creator_image_path) as image:
            original_width, original_height = image.size
        image_left, image_top, shown_width, shown_height = self.trim_creator_image_rect
        canvas_x = image_left + x * shown_width / max(1, original_width)
        canvas_y = image_top + y * shown_height / max(1, original_height)
        return canvas_x, canvas_y

    def _build_rdat_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.rdat_tab = tab
        self.tabs.add(tab, text="RDAT")

        toolbar = ttk.Frame(tab)
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Button(toolbar, text="Open .rdat", command=self.open_rdat).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Save", command=self.save_rdat).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Save As", command=self.save_rdat_as).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.rdat_status = ttk.Label(
            toolbar,
            text="No RDAT loaded.",
            style="Muted.TLabel",
        )
        self.rdat_status.pack(side=tk.LEFT, padx=(16, 0), fill=tk.X, expand=True)

        left = ttk.Frame(tab)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(left, text="RDAT references", style="Status.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 6)
        )
        self.rdat_refs = ttk.Treeview(
            left,
            columns=("offset", "source", "file"),
            show="tree headings",
            height=8,
        )
        self.rdat_refs.heading("#0", text="Name")
        self.rdat_refs.heading("offset", text="Offset")
        self.rdat_refs.heading("source", text="Detected From")
        self.rdat_refs.heading("file", text="Local File")
        self.rdat_refs.column("#0", width=180, minwidth=140)
        self.rdat_refs.column("offset", width=95, anchor=tk.E)
        self.rdat_refs.column("source", width=120)
        self.rdat_refs.column("file", width=95)
        self.rdat_refs.bind("<Double-1>", self._open_selected_rdat_reference)

        rdat_ref_scroll = ttk.Scrollbar(
            left, orient=tk.VERTICAL, command=self.rdat_refs.yview
        )
        self.rdat_refs.configure(yscrollcommand=rdat_ref_scroll.set)
        self.rdat_refs.grid(row=1, column=0, sticky="nsew")
        rdat_ref_scroll.grid(row=1, column=1, sticky="ns")
        ttk.Button(
            left,
            text="Load Selected",
            command=self.load_selected_rdat_reference,
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        editor_frame = ttk.Frame(tab)
        editor_frame.grid(row=1, column=1, sticky="nsew")
        self.rdat_editor = tk.Text(
            editor_frame,
            wrap=tk.NONE,
            undo=True,
            font=("Consolas", 10),
        )
        self.rdat_editor.bind("<<Modified>>", self._on_rdat_modified)
        y_scroll = ttk.Scrollbar(
            editor_frame, orient=tk.VERTICAL, command=self.rdat_editor.yview
        )
        x_scroll = ttk.Scrollbar(
            editor_frame, orient=tk.HORIZONTAL, command=self.rdat_editor.xview
        )
        self.rdat_editor.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        self.rdat_editor.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        tab.columnconfigure(0, minsize=380)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

    def open_iff(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import NBA 2K Jersey .iff",
            filetypes=(("NBA 2K IFF files", "*.iff"), ("All files", "*.*")),
        )
        if not selected:
            return

        path = Path(selected)
        self._set_busy(True)
        self.summary.configure(text=f"Scanning {path.name}...")

        thread = threading.Thread(target=self._scan_file_worker, args=(path,), daemon=True)
        thread.start()

    def _scan_file_worker(self, path: Path) -> None:
        try:
            result = scan_iff(path)
        except Exception as exc:  # noqa: BLE001 - show GUI error for import failures.
            self.after(0, lambda: self._scan_failed(path, exc))
            return
        self.after(0, lambda: self._scan_finished(result))

    def _scan_failed(self, path: Path, exc: Exception) -> None:
        self._set_busy(False)
        self.summary.configure(text="Import failed.")
        messagebox.showerror("Import failed", f"Could not scan {path.name}:\n\n{exc}")

    def _scan_finished(self, result: IffScanResult) -> None:
        self.scan_result = result
        self.pending_replacements.clear()
        self.texture_file_overrides.clear()
        self._set_busy(False)
        self.file_label.configure(text=str(result.path))
        self.summary.configure(
            text=(
                f"{result.path.name} | {format_bytes(result.size)} | "
                f"{len(result.resources)} resources | "
                f"{len(result.texture_pairs)} texture pair candidates"
            )
        )
        self._populate_textures(result)
        self._populate_rdat(result)

    def _set_busy(self, busy: bool) -> None:
        self.configure(cursor="watch" if busy else "")
        self.update_idletasks()

    def _populate_textures(self, result: IffScanResult) -> None:
        self.textures.delete(*self.textures.get_children())
        self._pair_index.clear()
        self._texture_row_index.clear()

        row_index = 0
        for pair in result.texture_pairs:
            rows = texture_rows_for_pair(pair)
            for dds_hit, txtr_hit in rows:
                item_id = f"texture-row:{row_index}"
                self._texture_row_index[item_id] = (dds_hit, txtr_hit)
                self.textures.insert(
                    "",
                    tk.END,
                    iid=item_id,
                    values=(
                        dds_hit.name if dds_hit else "",
                        txtr_hit.name if txtr_hit else "",
                        texture_row_status(dds_hit, txtr_hit),
                        hex_offset(dds_hit.offset) if dds_hit else "",
                        hex_offset(txtr_hit.offset) if txtr_hit else "",
                        texture_row_source(dds_hit, txtr_hit),
                    ),
                )
                row_index += 1

        if row_index == 0:
            self.textures.insert(
                "",
                tk.END,
                values=(
                    "",
                    "",
                    "No textures found",
                    "",
                    "",
                    "",
                ),
            )

    def _populate_rdat(self, result: IffScanResult) -> None:
        self.rdat_refs.delete(*self.rdat_refs.get_children())
        self._rdat_resource_index.clear()

        rdat_hits = [resource for resource in result.resources if resource.kind == "RDAT"]
        for index, resource in enumerate(rdat_hits):
            item_id = f"rdat:{index}:{resource.offset}"
            self._rdat_resource_index[item_id] = resource
            local_path = self._resolve_rdat_reference(resource)
            self.rdat_refs.insert(
                "",
                tk.END,
                iid=item_id,
                text=resource.name,
                values=(
                    hex_offset(resource.offset),
                    resource.source,
                    "found" if local_path else "not found",
                ),
            )

        if rdat_hits:
            self.rdat_status.configure(
                text=(
                    f"{len(rdat_hits)} RDAT reference"
                    f"{'' if len(rdat_hits) == 1 else 's'} found in the imported .iff."
                )
            )
        elif self.rdat_path is None:
            self.rdat_status.configure(text="No RDAT references found in this .iff.")

    def choose_generator_color(self, key: str, swatch: tk.Label) -> None:
        current = self.generator_color_vars[key].get() or "#ffffff"
        color = colorchooser.askcolor(color=current)[1]
        if not color:
            return
        self.generator_color_vars[key].set(color)
        swatch.configure(text="", background=color)
        self._schedule_generator_preview_refresh()

    def clear_generator_color(self, key: str, swatch: tk.Label) -> None:
        self.generator_color_vars[key].set("")
        swatch.configure(text="None", background="#f0f0f0")
        self._schedule_generator_preview_refresh()

    def normalize_generator_color_entry(self, key: str, swatch: tk.Label) -> None:
        color = self._normalize_hex_color(self.generator_color_vars[key].get())
        if color is None:
            swatch.configure(text="Bad", background="#f0f0f0")
            return
        self.generator_color_vars[key].set(color)
        if color:
            swatch.configure(text="", background=color)
        else:
            swatch.configure(text="None", background="#f0f0f0")
        self._schedule_generator_preview_refresh()

    def upload_generator_image(self, key: str) -> None:
        selected = filedialog.askopenfilename(
            title="Select image",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        path = Path(selected)
        self.generator_paths[key] = path
        self.generator_file_labels[key].configure(text=path.name)
        trim_name = _trim_name_for_generator_key(key)
        if trim_name is not None:
            self.generator_trim_placements[trim_name] = TrimPlacementSettings()
        self._schedule_generator_preview_refresh()

    def clear_generator_image(self, key: str) -> None:
        self.generator_paths[key] = None
        self.generator_file_labels[key].configure(text="none")
        trim_name = _trim_name_for_generator_key(key)
        if trim_name is not None:
            self.generator_trim_placements.pop(trim_name, None)
        self._schedule_generator_preview_refresh()

    def upload_generator_logo(self) -> None:
        type_label = self.generator_logo_type_var.get()
        target_name = self.generator_logo_target_names.get(type_label)
        if not target_name:
            messagebox.showinfo("Upload Logo", "Choose a logo type first.")
            return
        selected = filedialog.askopenfilename(
            title="Select logo image",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        placement = LogoPlacement(
            Path(selected),
            target_name,
            stretch_x=target_name == "wrap_across_front_back_logo",
        )
        self.generator_logo_placements.append(placement)
        self.generator_logo_list.insert(
            "",
            tk.END,
            iid=f"logo:{len(self.generator_logo_placements) - 1}",
            values=(type_label, placement.path.name),
        )
        self._schedule_generator_preview_refresh()

    def load_logo_creator_reference(self) -> None:
        selected = filedialog.askopenfilename(
            title="Upload Logo Reference",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        self.logo_creator_image_path = Path(selected)
        self.logo_creator_web_reference_path = None
        self.logo_creator_lasso_points = []
        self.logo_creator_drag_start = None
        self.logo_creator_output_path = None
        self.logo_creator_preview_visible_var.set(False)
        self._sync_logo_creator_preview_visibility()
        self._show_logo_creator_reference()
        self.logo_creator_status.configure(
            text=f"Loaded reference: {Path(selected).name}. Select an area or use Preview to create a logo."
        )
        self.tabs.select(self.logo_creator_tab)

    def _write_logo_creator_web_reference_copy(self, source: Path) -> Path:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Logo web selector requires Pillow.") from exc
        output_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "logo_creator"
            / "web_reference.png"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as opened:
            opened.convert("RGBA").save(output_path)
        return output_path

    def _show_logo_creator_reference(self) -> None:
        if not hasattr(self, "logo_creator_canvas"):
            return
        self.logo_creator_canvas.delete("all")
        if self.logo_creator_image_path is None:
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        self.logo_creator_canvas.update_idletasks()
        canvas_width = max(1, self.logo_creator_canvas.winfo_width())
        canvas_height = max(1, self.logo_creator_canvas.winfo_height())
        with Image.open(self.logo_creator_image_path) as opened:
            source_width, source_height = opened.size
            scale = min(canvas_width / source_width, canvas_height / source_height, 1.0)
            shown_width = max(1, round(source_width * scale))
            shown_height = max(1, round(source_height * scale))
            opened.thumbnail((shown_width, shown_height), Image.Resampling.LANCZOS)
            shown = opened.convert("RGBA")
            if shown.size != (shown_width, shown_height):
                shown = shown.resize((shown_width, shown_height), Image.Resampling.LANCZOS)
        left = max(10, (canvas_width - shown_width) // 2)
        top = max(10, (canvas_height - shown_height) // 2)
        self.logo_creator_image_rect = (left, top, shown_width, shown_height)
        self.logo_creator_preview_image = ImageTk.PhotoImage(shown)
        self.logo_creator_canvas.create_image(
            left,
            top,
            image=self.logo_creator_preview_image,
            anchor=tk.NW,
        )
        self.logo_creator_canvas.configure(
            scrollregion=(0, 0, max(canvas_width, left + shown_width + 10), max(canvas_height, top + shown_height + 10))
        )
        self._draw_logo_creator_lasso()

    def _draw_logo_creator_lasso(self) -> None:
        if not self.logo_creator_lasso_points or self.logo_creator_image_rect is None:
            return
        canvas_points: list[float] = []
        for x, y in self.logo_creator_lasso_points:
            canvas_x, canvas_y = self._logo_creator_image_to_canvas(x, y)
            canvas_points.extend((canvas_x, canvas_y))
        if len(canvas_points) >= 4:
            self.logo_creator_canvas.create_line(
                *canvas_points,
                fill="#ffcc33",
                width=2,
                smooth=True,
                tags=("logo_lasso",),
            )
        if len(canvas_points) >= 6:
            closed = canvas_points + canvas_points[:2]
            self.logo_creator_canvas.create_line(
                *closed,
                fill="#ffcc33",
                width=2,
                dash=(8, 5),
                tags=("logo_lasso",),
            )

    def _logo_creator_lasso_start(self, event: tk.Event) -> None:
        point = self._logo_creator_event_to_image(event)
        if point is None:
            return
        if self.logo_creator_pick_color_mode:
            self.sample_logo_creator_color(point)
            return
        self.logo_creator_lasso_points = [point]
        self.logo_creator_drag_start = point
        self._show_logo_creator_reference()

    def _logo_creator_lasso_move(self, event: tk.Event) -> None:
        if self.logo_creator_pick_color_mode:
            return
        point = self._logo_creator_event_to_image(event)
        if point is None:
            return
        if not self.logo_creator_lasso_points:
            self.logo_creator_lasso_points = [point]
        last_x, last_y = self.logo_creator_lasso_points[-1]
        if abs(point[0] - last_x) + abs(point[1] - last_y) >= 2:
            self.logo_creator_lasso_points.append(point)
            self._show_logo_creator_reference()

    def _logo_creator_lasso_end(self, event: tk.Event) -> None:
        if self.logo_creator_pick_color_mode:
            return
        point = self._logo_creator_event_to_image(event)
        if point is not None and self.logo_creator_lasso_points:
            self.logo_creator_lasso_points.append(point)
        self.logo_creator_drag_start = None
        if len(self.logo_creator_lasso_points) < 3:
            self.logo_creator_lasso_points = []
            self.logo_creator_status.configure(text="Lasso needs a larger selected area.")
            self._show_logo_creator_reference()
            return
        self._show_logo_creator_reference()
        self.update_logo_creator_preview()

    def _logo_creator_event_to_image(self, event: tk.Event) -> tuple[int, int] | None:
        if self.logo_creator_image_path is None or self.logo_creator_image_rect is None:
            return None
        try:
            from PIL import Image
        except ImportError:
            return None
        left, top, shown_width, shown_height = self.logo_creator_image_rect
        canvas_x = self.logo_creator_canvas.canvasx(event.x)
        canvas_y = self.logo_creator_canvas.canvasy(event.y)
        if not (left <= canvas_x <= left + shown_width and top <= canvas_y <= top + shown_height):
            return None
        with Image.open(self.logo_creator_image_path) as image:
            width, height = image.size
        image_x = round((canvas_x - left) * width / shown_width)
        image_y = round((canvas_y - top) * height / shown_height)
        return (
            max(0, min(width - 1, image_x)),
            max(0, min(height - 1, image_y)),
        )

    def _logo_creator_image_to_canvas(self, image_x: int, image_y: int) -> tuple[float, float]:
        if self.logo_creator_image_path is None or self.logo_creator_image_rect is None:
            return (0, 0)
        from PIL import Image

        left, top, shown_width, shown_height = self.logo_creator_image_rect
        with Image.open(self.logo_creator_image_path) as image:
            width, height = image.size
        return (
            left + image_x * shown_width / width,
            top + image_y * shown_height / height,
        )

    def enable_logo_creator_color_dropper(self) -> None:
        if self.logo_creator_image_path is None:
            messagebox.showinfo("Logo Creator", "Upload a reference image first.")
            return
        self.logo_creator_pick_color_mode = True
        if hasattr(self, "logo_creator_canvas"):
            self.logo_creator_canvas.configure(cursor="tcross")
        self.logo_creator_status.configure(text="Eyedropper active: click a color on the reference image.")

    def sample_logo_creator_color(self, point: tuple[int, int]) -> None:
        if self.logo_creator_image_path is None:
            return
        try:
            from PIL import Image
        except ImportError:
            return
        with Image.open(self.logo_creator_image_path) as opened:
            image = opened.convert("RGBA")
            red, green, blue, _alpha = image.getpixel(point)
        color = _rgb_to_hex((red, green, blue))
        self.logo_creator_sampled_color_var.set(color)
        if hasattr(self, "logo_creator_sampled_color_swatch"):
            self.logo_creator_sampled_color_swatch.configure(background=color)
        self.logo_creator_remove_sampled_color_var.set(True)
        self.logo_creator_pick_color_mode = False
        self.logo_creator_canvas.configure(cursor="")
        self.logo_creator_status.configure(text=f"Sampled cleanup color {color}.")
        self.update_logo_creator_preview()

    def normalize_logo_creator_sampled_hex(self) -> None:
        color = self._normalize_hex_color(self.logo_creator_sampled_color_var.get())
        if not color:
            self.logo_creator_status.configure(text="Sampled color hex is not valid.")
            return
        self.logo_creator_sampled_color_var.set(color)
        if hasattr(self, "logo_creator_sampled_color_swatch"):
            self.logo_creator_sampled_color_swatch.configure(background=color)
        self.update_logo_creator_preview()

    def copy_logo_creator_sampled_hex(self) -> None:
        color = self._normalize_hex_color(self.logo_creator_sampled_color_var.get())
        if not color:
            self.logo_creator_status.configure(text="Sampled color hex is not valid.")
            return
        self.logo_creator_sampled_color_var.set(color)
        self.clipboard_clear()
        self.clipboard_append(color)
        self.logo_creator_status.configure(text=f"Copied sampled color {color}.")

    def update_logo_creator_preview(self) -> None:
        if self.logo_creator_image_path is None:
            messagebox.showinfo("Logo Creator", "Upload a reference image first.")
            return
        try:
            from .generator import (
                remove_detected_background,
                remove_image_background,
                upscale_logo_image,
            )
            from PIL import Image, ImageDraw
        except ImportError as exc:
            messagebox.showerror("Logo Creator", f"Logo creation requires Pillow.\n\n{exc}")
            return
        with Image.open(self.logo_creator_image_path) as opened:
            image = opened.convert("RGBA")
            if len(self.logo_creator_lasso_points) >= 3:
                xs = [point[0] for point in self.logo_creator_lasso_points]
                ys = [point[1] for point in self.logo_creator_lasso_points]
                left = max(0, min(xs))
                top = max(0, min(ys))
                right = min(image.width, max(xs) + 1)
                bottom = min(image.height, max(ys) + 1)
                logo = image.crop((left, top, right, bottom))
                mask = Image.new("L", logo.size, 0)
                relative_points = [
                    (x - left, y - top)
                    for x, y in self.logo_creator_lasso_points
                ]
                ImageDraw.Draw(mask).polygon(relative_points, fill=255)
                alpha = logo.getchannel("A")
                logo.putalpha(Image.composite(alpha, Image.new("L", logo.size, 0), mask))
            else:
                logo = image
            if self.logo_creator_auto_bg_var.get():
                logo = remove_detected_background(
                    logo,
                    tolerance=self._logo_creator_tolerance(),
                )
            cleaned = remove_image_background(
                logo,
                remove_white=self.logo_creator_remove_white_var.get(),
                remove_black=self.logo_creator_remove_black_var.get(),
                outside_only=self.logo_creator_outside_only_var.get(),
                tolerance=self._logo_creator_tolerance(),
            )
            if self.logo_creator_remove_sampled_color_var.get():
                sampled_color = self._normalize_hex_color(
                    self.logo_creator_sampled_color_var.get()
                )
                if sampled_color:
                    cleaned = _remove_sampled_color_background(
                        cleaned,
                        _hex_to_rgb(sampled_color),
                        outside_only=self.logo_creator_outside_only_var.get(),
                        tolerance=self._logo_creator_tolerance(),
                    )
            cleaned = upscale_logo_image(
                cleaned,
                scale_factor=self._logo_creator_upscale_factor(),
                sharpen=self.logo_creator_sharpen_var.get(),
            )
            cleaned = _fit_transparent_image_to_square(
                cleaned,
                self._logo_creator_canvas_size(),
                padding_ratio=0.08,
            )
        output_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "logo_creator"
            / self.logo_creator_image_path.stem
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        self.logo_creator_output_path = output_dir / "created_logo.png"
        cleaned.save(self.logo_creator_output_path)
        self.logo_creator_preview_visible_var.set(True)
        self._sync_logo_creator_preview_visibility()
        self._show_logo_creator_logo_preview()
        self.logo_creator_status.configure(text=f"Logo preview ready: {cleaned.width} x {cleaned.height}.")

    def _logo_creator_canvas_size(self) -> int:
        value = self.logo_creator_canvas_size_var.get().lower().strip()
        if value.startswith("2048"):
            return 2048
        if value.startswith("512"):
            return 512
        return 1024

    def _logo_creator_upscale_factor(self) -> int:
        value = self.logo_creator_upscale_var.get().lower().strip()
        if value.startswith("4"):
            return 4
        if value.startswith("2"):
            return 2
        return 1

    def _logo_creator_tolerance(self) -> int:
        try:
            return max(0, min(255, int(self.logo_creator_tolerance_var.get())))
        except tk.TclError:
            return 32

    def toggle_logo_creator_preview(self) -> None:
        self.logo_creator_preview_visible_var.set(
            not self.logo_creator_preview_visible_var.get()
        )
        self._sync_logo_creator_preview_visibility()

    def _sync_logo_creator_preview_visibility(self) -> None:
        if not hasattr(self, "logo_creator_logo_preview_frame"):
            return
        visible = self.logo_creator_preview_visible_var.get()
        if visible:
            self.logo_creator_logo_preview_frame.grid()
            self.logo_creator_logo_preview_frame.master.rowconfigure(2, weight=1)
        else:
            self.logo_creator_logo_preview_frame.grid_remove()
            self.logo_creator_logo_preview_frame.master.rowconfigure(2, weight=0)
        if hasattr(self, "logo_creator_preview_toggle_button"):
            self.logo_creator_preview_toggle_button.configure(
                text="Hide Preview" if visible else "Show Preview"
            )
        if visible:
            self._show_logo_creator_logo_preview()

    def _show_logo_creator_logo_preview(self) -> None:
        if not hasattr(self, "logo_creator_logo_preview"):
            return
        self.logo_creator_logo_preview.delete("all")
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            return
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            return
        self.logo_creator_logo_preview.update_idletasks()
        width = max(1, self.logo_creator_logo_preview.winfo_width() - 12)
        height = max(1, self.logo_creator_logo_preview.winfo_height() - 12)
        with Image.open(self.logo_creator_output_path) as opened:
            logo = opened.convert("RGBA")
            scale = min(width / logo.width, height / logo.height)
            preview_size = (
                max(1, round(logo.width * scale)),
                max(1, round(logo.height * scale)),
            )
            logo = logo.resize(preview_size, Image.Resampling.LANCZOS)
        background = self._logo_creator_preview_background(preview_size)
        background.alpha_composite(logo)
        self.logo_creator_logo_preview_image = ImageTk.PhotoImage(background)
        x = (self.logo_creator_logo_preview.winfo_width() - preview_size[0]) // 2
        y = (self.logo_creator_logo_preview.winfo_height() - preview_size[1]) // 2
        self.logo_creator_logo_preview.create_image(
            max(0, x),
            max(0, y),
            image=self.logo_creator_logo_preview_image,
            anchor=tk.NW,
        )

    def _logo_creator_preview_background(self, size: tuple[int, int]):
        from PIL import Image, ImageDraw

        mode = self.logo_creator_bg_var.get()
        if mode == "White":
            return Image.new("RGBA", size, (255, 255, 255, 255))
        if mode == "Checker":
            background = Image.new("RGBA", size, (238, 238, 238, 255))
            draw = ImageDraw.Draw(background)
            square = 16
            for y in range(0, size[1], square):
                for x in range(0, size[0], square):
                    if (x // square + y // square) % 2:
                        draw.rectangle((x, y, x + square - 1, y + square - 1), fill=(205, 205, 205, 255))
            return background
        return Image.new("RGBA", size, (0, 0, 0, 255))

    def save_logo_creator_png_as(self) -> None:
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            self.update_logo_creator_preview()
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            return
        selected = filedialog.asksaveasfilename(
            title="Save Created Logo",
            defaultextension=".png",
            initialfile=self.logo_creator_output_path.name,
            filetypes=(("PNG files", "*.png"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            Path(selected).write_bytes(self.logo_creator_output_path.read_bytes())
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.logo_creator_status.configure(text=f"Saved logo to {selected}.")

    def stage_current_logo_for_ai_pack(self) -> None:
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            self.update_logo_creator_preview()
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            return
        logo_type = self.logo_creator_type_var.get() or "Logo"
        output_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "logo_creator"
            / "ai_stage"
        )
        output_path = _next_available_path(
            output_dir
            / f"{safe_filename(logo_type).replace(' ', '_').lower()}_staged.png"
        )
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.logo_creator_output_path, output_path)
        except OSError as exc:
            messagebox.showerror("Logo AI Assist", str(exc))
            return
        self.logo_ai_staged_paths.append((logo_type, output_path))
        self._refresh_logo_ai_stage_list()
        self.logo_creator_status.configure(
            text=f"Staged {logo_type} for AI pack: {output_path.name}."
        )

    def remove_selected_logo_ai_stage(self) -> None:
        if not hasattr(self, "logo_ai_stage_list"):
            return
        selected = self.logo_ai_stage_list.selection()
        if not selected:
            return
        indexes = sorted(
            (int(item_id.split(":")[1]) for item_id in selected),
            reverse=True,
        )
        for index in indexes:
            if 0 <= index < len(self.logo_ai_staged_paths):
                del self.logo_ai_staged_paths[index]
        self._refresh_logo_ai_stage_list()
        self.logo_creator_status.configure(text="Removed staged logo.")

    def clear_logo_ai_stage(self) -> None:
        self.logo_ai_staged_paths = []
        self._refresh_logo_ai_stage_list()
        self.logo_creator_status.configure(text="Cleared staged logos.")

    def _refresh_logo_ai_stage_list(self) -> None:
        if not hasattr(self, "logo_ai_stage_list"):
            return
        self.logo_ai_stage_list.delete(*self.logo_ai_stage_list.get_children())
        for index, (logo_type, path) in enumerate(self.logo_ai_staged_paths):
            self.logo_ai_stage_list.insert(
                "",
                tk.END,
                iid=f"stage:{index}",
                values=(logo_type, path.name),
            )

    def create_logo_ai_reference_pack(self) -> None:
        staged = [
            (logo_type, path)
            for logo_type, path in self.logo_ai_staged_paths
            if path.exists()
        ]
        if not staged:
            if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
                self.update_logo_creator_preview()
            if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
                return
            staged = [(self.logo_creator_type_var.get() or "Logo", self.logo_creator_output_path)]
        selected = filedialog.askdirectory(title="Choose folder for AI logo reference pack")
        if not selected:
            return
        folder = Path(selected)
        prompt_path = folder / "ai_logo_prompt.txt"
        try:
            copied_names = []
            for index, (logo_type, path) in enumerate(staged, start=1):
                reference_path = folder / (
                    f"{index:02d}_"
                    f"{safe_filename(logo_type).replace(' ', '_').lower()}"
                    "_logo_reference.png"
                )
                shutil.copyfile(path, reference_path)
                copied_names.append(reference_path.name)
            prompt_path.write_text(
                self._logo_ai_prompt_text([logo_type for logo_type, _path in staged]),
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror("Logo AI Assist", str(exc))
            return
        self.logo_creator_status.configure(
            text=f"AI logo pack saved with {len(copied_names)} logo reference(s)."
        )

    def import_ai_logo_creator_png(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import AI Logo PNG",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            from PIL import Image
        except ImportError:
            messagebox.showerror("Logo AI Assist", "Importing AI logo requires Pillow.")
            return
        output_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "logo_creator"
            / "ai_imports"
        )
        logo_type = self.logo_creator_type_var.get() or "logo"
        output_path = _next_available_path(
            output_dir / f"{safe_filename(logo_type).replace(' ', '_').lower()}_ai_logo.png"
        )
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(selected) as opened:
                image = opened.convert("RGBA")
                image = _fit_transparent_image_to_square(
                    image,
                    self._logo_creator_canvas_size(),
                    padding_ratio=0.08,
                )
                image.save(output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Logo AI Assist", str(exc))
            return
        self.logo_creator_output_path = output_path
        self.logo_creator_preview_visible_var.set(True)
        self._sync_logo_creator_preview_visibility()
        self._show_logo_creator_logo_preview()
        self.logo_creator_status.configure(text=f"Imported AI logo: {output_path.name}.")

    def _logo_ai_prompt_text(self, logo_types: str | list[str]) -> str:
        if isinstance(logo_types, str):
            logo_type_text = logo_types
        else:
            logo_type_text = ", ".join(logo_types)
        return "\n".join(
            [
                "Clean up and redraw these basketball jersey logos as transparent PNGs.",
                f"Logo type(s): {logo_type_text}.",
                "Keep the same design, colors, proportions, outline thickness, and visual style.",
                "Remove background noise, jagged edges, compression artifacts, and blur.",
                "Use a true transparent background with an alpha channel.",
                "Do not put the logo on white, black, gray, checkerboard, or any solid-color background.",
                "Do not redesign it, change the wording, add extra effects, or place it on a jersey mockup.",
                f"Output size should be {self._logo_creator_canvas_size()} x {self._logo_creator_canvas_size()} pixels.",
                "Keep it centered with a small transparent padding area.",
                "Return one finished PNG per uploaded reference, keeping the same order as the file names.",
            ]
        )

    def send_logo_creator_to_generator(self) -> None:
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            self.update_logo_creator_preview()
        if self.logo_creator_output_path is None or not self.logo_creator_output_path.exists():
            return
        type_label = self.logo_creator_type_var.get()
        try:
            saved_path, target_name = self._send_logo_path_to_generator(
                type_label,
                self.logo_creator_output_path,
            )
        except ValueError as exc:
            messagebox.showinfo("Logo Creator", str(exc))
            return
        except OSError as exc:
            messagebox.showerror("Logo Creator", str(exc))
            return
        self._refresh_generator_logo_list()
        self.tabs.select(self.generator_tab)
        self._schedule_generator_preview_refresh()
        if target_name == "front_wordmark":
            self.logo_creator_status.configure(
                text=f"Sent front wordmark to Generator: {saved_path.name}."
            )
            return
        self.logo_creator_status.configure(text=f"Sent logo to Generator: {saved_path.name}.")

    def send_staged_logos_to_generator(self) -> None:
        staged = [
            (logo_type, path)
            for logo_type, path in self.logo_ai_staged_paths
            if path.exists()
        ]
        if not staged:
            messagebox.showinfo("Logo Creator", "Stage one or more logos first.")
            return
        sent_count = 0
        failures = []
        for logo_type, path in staged:
            try:
                self._send_logo_path_to_generator(logo_type, path)
                sent_count += 1
            except (OSError, ValueError) as exc:
                failures.append(f"{logo_type}: {exc}")
        if sent_count:
            self._refresh_generator_logo_list()
            self.tabs.select(self.generator_tab)
            self._schedule_generator_preview_refresh()
            self.logo_creator_status.configure(
                text=f"Sent {sent_count} staged logo(s) to Generator."
            )
        if failures:
            messagebox.showwarning(
                "Logo Creator",
                "Some staged logos could not be sent:\n\n" + "\n".join(failures[:6]),
            )
        elif sent_count == 0:
            messagebox.showinfo("Logo Creator", "No staged logos were sent.")

    def _send_logo_path_to_generator(self, type_label: str, source_path: Path) -> tuple[Path, str]:
        target_name = self.generator_logo_target_names.get(type_label)
        if not target_name:
            raise ValueError("Choose a logo type first.")
        if not source_path.exists():
            raise ValueError(f"Logo file is missing: {source_path.name}")
        saved_path = _next_available_path(
            source_path.with_name(
                f"{safe_filename(type_label).replace(' ', '_').lower()}_logo.png"
            )
        )
        shutil.copyfile(source_path, saved_path)
        if target_name == "front_wordmark":
            self.generator_paths["front_wordmark_image"] = saved_path
            if "front_wordmark_image" in self.generator_file_labels:
                self.generator_file_labels["front_wordmark_image"].configure(
                    text=saved_path.name
                )
            return saved_path, target_name
        placement = LogoPlacement(
            saved_path,
            target_name,
            stretch_x=target_name == "wrap_across_front_back_logo",
        )
        self.generator_logo_placements.append(placement)
        return saved_path, target_name

    def open_logo_creator_web_selector(self) -> None:
        if self.logo_creator_image_path is None:
            messagebox.showinfo("Logo Creator", "Upload a reference image first.")
            return
        try:
            if self.web_editor_server is None:
                self.web_editor_server = WebEditorServer(self)
            url = self.web_editor_server.start().rstrip("/") + "/logo"
            webbrowser.open(url)
            self.logo_creator_status.configure(text=f"Logo web selector opened at {url}")
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Logo web selector failed", str(exc))

    def _logo_creator_web_project(self) -> dict:
        reference_path = self._logo_creator_web_reference_source()
        if reference_path is None:
            return {
                "hasImage": False,
                "width": 0,
                "height": 0,
                "imageUrl": "/api/logo/reference",
                "message": (
                    "No logo reference is loaded."
                    if self.logo_creator_image_path is None
                    else (
                        f"Logo reference is not available for the web selector. "
                        f"Original: {self.logo_creator_image_path}"
                    )
                ),
                "points": [],
            }
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Logo selector requires Pillow.") from exc
        with Image.open(reference_path) as image:
            width, height = image.size
        return {
            "hasImage": True,
            "width": width,
            "height": height,
            "imageUrl": "/api/logo/reference",
            "message": f"Loaded {reference_path.name}",
            "points": [
                {"x": x, "y": y}
                for x, y in self.logo_creator_lasso_points
            ],
        }

    def _logo_creator_reference_image(self) -> tuple[bytes, str]:
        reference_path = self._logo_creator_web_reference_source()
        if reference_path is None:
            raise FileNotFoundError("No logo reference image is loaded.")
        return reference_path.read_bytes(), image_content_type(reference_path)

    def _logo_creator_web_reference_source(self) -> Path | None:
        if (
            self.logo_creator_web_reference_path is not None
            and self.logo_creator_web_reference_path.exists()
        ):
            return self.logo_creator_web_reference_path
        if (
            self.logo_creator_image_path is not None
            and self.logo_creator_image_path.exists()
        ):
            try:
                self.logo_creator_web_reference_path = self._write_logo_creator_web_reference_copy(
                    self.logo_creator_image_path
                )
                return self.logo_creator_web_reference_path
            except Exception:  # noqa: BLE001 - fallback handled by caller.
                return self.logo_creator_image_path
        return None

    def _logo_creator_web_lasso(self, payload: dict) -> None:
        points = payload.get("points", [])
        clean_points: list[tuple[int, int]] = []
        for point in points:
            try:
                x = int(round(float(point.get("x", 0))))
                y = int(round(float(point.get("y", 0))))
            except (AttributeError, TypeError, ValueError):
                continue
            clean_points.append((x, y))
        self.logo_creator_lasso_points = clean_points
        self._show_logo_creator_reference()
        self.update_logo_creator_preview()
        self.logo_creator_status.configure(
            text=f"Received web lasso with {len(clean_points)} points."
        )

    def _logo_creator_web_clear(self) -> None:
        self.logo_creator_lasso_points = []
        self.logo_creator_output_path = None
        self.logo_creator_preview_visible_var.set(False)
        self._sync_logo_creator_preview_visibility()
        self._show_logo_creator_reference()
        self._show_logo_creator_logo_preview()
        self.logo_creator_status.configure(text="Logo lasso cleared.")

    def upload_number_creator_digit(self) -> None:
        selected = filedialog.askopenfilename(
            title=f"Select digit {self.number_creator_digit_var.get()} image",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        digit = self.number_creator_digit_var.get()
        output_path = self._number_creator_digit_output_path(digit)
        try:
            self._write_clean_number_digit(Path(selected), output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        self.number_creator_digit_paths[digit] = output_path
        self._refresh_number_creator_digit_list()
        self.refresh_number_creator_sheet_preview()
        self._advance_number_creator_digit_after_save(digit)
        self.number_creator_status.configure(text=f"Loaded digit {digit}.")

    def import_number_font_iff(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import Font IFF",
            filetypes=(("Font IFF files", "*font*.iff"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            info = inspect_font_number_texture(selected)
            sheet = extract_number_sheet_from_font_iff(selected)
            digits = split_number_sheet_digits(sheet)
            self.number_creator_digit_paths = {}
            self.number_creator_original_digit_paths = {}
            self.number_creator_font_digit_centers = {}
            self.number_creator_font_digit_bounds = {}
            for index, digit_image in enumerate(digits):
                bbox = _visible_image_bounds(digit_image)
                if bbox is not None:
                    self.number_creator_font_digit_bounds[str(index)] = bbox
                center = _visible_image_center(digit_image)
                if center is not None:
                    self.number_creator_font_digit_centers[str(index)] = center
                output_path = self._number_creator_digit_output_path(
                    str(index),
                    prefix="font_original_digit",
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                digit_image.save(output_path)
                self.number_creator_digit_paths[str(index)] = output_path
                self.number_creator_original_digit_paths[str(index)] = output_path
            self.number_creator_font_info = info
            self.number_creator_font_status_var.set(
                f"Font IFF: {Path(selected).name} | {info.width} x {info.height} | "
                f"{info.cell_width} px cells | {info.format_label}"
            )
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Import Font IFF", str(exc))
            return
        self._refresh_number_creator_digit_list()
        self.refresh_number_creator_sheet_preview()
        self.number_creator_status.configure(
            text=f"Imported font colors from {Path(selected).name}."
        )

    def choose_number_recolor_color(self, target: str) -> None:
        variable = (
            self.number_recolor_light_var
            if target == "light"
            else self.number_recolor_dark_var
        )
        current = self._normalize_hex_color(variable.get()) or "#ffffff"
        color = colorchooser.askcolor(color=current, parent=self)[1]
        if color is None:
            return
        normalized = self._normalize_hex_color(color)
        if normalized is None:
            return
        variable.set(normalized)
        if target == "light":
            self.number_recolor_no_light_var.set(False)
        else:
            self.number_recolor_no_dark_var.set(False)
        self._refresh_number_recolor_swatches()

    def apply_number_font_recolor(self) -> None:
        if self.number_creator_font_info is None or not self.number_creator_original_digit_paths:
            messagebox.showinfo("Font Recolor", "Import a font IFF first.")
            return
        try:
            light = self._number_recolor_rgb("light")
            dark = self._number_recolor_rgb("dark")
            edge_protection = self._number_recolor_edge_protection()
            outline_thickness = self._number_recolor_outline_thickness()
            recolored_paths: dict[str, Path] = {}
            from PIL import Image

            for digit, source in self.number_creator_original_digit_paths.items():
                if not source.exists():
                    continue
                with Image.open(source) as opened:
                    recolored = _recolor_font_image(
                        opened.convert("RGBA"),
                        dark,
                        light,
                        edge_protection=edge_protection,
                        outline_thickness=outline_thickness,
                    )
                output_path = self._number_creator_digit_output_path(
                    digit,
                    prefix="font_recolor_digit",
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                recolored.save(output_path)
                recolored_paths[digit] = output_path
            if not recolored_paths:
                raise ValueError("No original font digits were available to recolor.")
            self.number_creator_digit_paths = recolored_paths
            self.refresh_number_creator_sheet_preview()
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Font Recolor", str(exc))
            return
        self.number_creator_status.configure(text="Applied font recolor preview.")

    def _on_number_recolor_edge_protection_changed(self, _value: str | None = None) -> None:
        self.number_recolor_edge_protection_label_var.set(
            f"{self.number_recolor_edge_protection_var.get()}%"
        )

    def _on_number_recolor_outline_thickness_changed(self, _value: str | None = None) -> None:
        self.number_recolor_outline_thickness_label_var.set(
            f"{self._number_recolor_outline_thickness()} px"
        )

    def _number_recolor_edge_protection(self) -> float:
        value = self.number_recolor_edge_protection_var.get()
        value = min(100, max(0, value))
        self.number_recolor_edge_protection_var.set(value)
        self._on_number_recolor_edge_protection_changed()
        return value / 100

    def _number_recolor_outline_thickness(self) -> int:
        value = int(round(self.number_recolor_outline_thickness_var.get()))
        value = min(3, max(0, value))
        self.number_recolor_outline_thickness_var.set(value)
        self.number_recolor_outline_thickness_label_var.set(f"{value} px")
        return value

    def restore_number_font_original_colors(self) -> None:
        if self.number_creator_font_info is None or not self.number_creator_original_digit_paths:
            messagebox.showinfo("Font Recolor", "Import a font IFF first.")
            return
        self.number_creator_digit_paths = {
            digit: path
            for digit, path in self.number_creator_original_digit_paths.items()
            if path.exists()
        }
        self.refresh_number_creator_sheet_preview()
        self.number_creator_status.configure(text="Restored original font colors.")

    def _number_recolor_rgb(self, target: str) -> tuple[int, int, int] | None:
        if target == "light" and self.number_recolor_no_light_var.get():
            return None
        if target == "dark" and self.number_recolor_no_dark_var.get():
            return None
        variable = (
            self.number_recolor_light_var
            if target == "light"
            else self.number_recolor_dark_var
        )
        normalized = self._normalize_hex_color(variable.get())
        if normalized is None or not normalized:
            raise ValueError("Enter valid light and dark hex colors.")
        variable.set(normalized)
        self._refresh_number_recolor_swatches()
        return _hex_to_rgb(normalized)

    def _on_number_recolor_hex_changed(self, target: str) -> None:
        variable = (
            self.number_recolor_light_var
            if target == "light"
            else self.number_recolor_dark_var
        )
        if not self._normalize_hex_color(variable.get()):
            self._refresh_number_recolor_swatches()
            return
        if target == "light" and self.number_recolor_no_light_var.get():
            self.number_recolor_no_light_var.set(False)
        elif target == "dark" and self.number_recolor_no_dark_var.get():
            self.number_recolor_no_dark_var.set(False)
        self._refresh_number_recolor_swatches()

    def _refresh_number_recolor_swatches(self) -> None:
        if hasattr(self, "number_recolor_light_swatch"):
            light = self._normalize_hex_color(self.number_recolor_light_var.get())
            if self.number_recolor_no_light_var.get():
                self.number_recolor_light_swatch.configure(background="#d8dbe2")
            elif light:
                self.number_recolor_light_swatch.configure(background=light)
        if hasattr(self, "number_recolor_dark_swatch"):
            dark = self._normalize_hex_color(self.number_recolor_dark_var.get())
            if self.number_recolor_no_dark_var.get():
                self.number_recolor_dark_swatch.configure(background="#d8dbe2")
            elif dark:
                self.number_recolor_dark_swatch.configure(background=dark)

    def save_number_creator_back_to_font_iff(self) -> None:
        if not self.number_creator_digit_paths:
            messagebox.showinfo("Font Recolor", "Import and recolor a font IFF first.")
            return
        if self.number_creator_font_info is None:
            selected_template = filedialog.askopenfilename(
                title="Choose source font IFF",
                filetypes=(("Font IFF files", "*font*.iff"), ("All files", "*.*")),
            )
            if not selected_template:
                return
            try:
                self.number_creator_font_info = inspect_font_number_texture(selected_template)
                template_sheet = extract_number_sheet_from_font_iff(selected_template)
                template_digits = split_number_sheet_digits(template_sheet)
                self.number_creator_font_digit_centers = {}
                self.number_creator_font_digit_bounds = {}
                for index, digit_image in enumerate(template_digits):
                    bbox = _visible_image_bounds(digit_image)
                    if bbox is not None:
                        self.number_creator_font_digit_bounds[str(index)] = bbox
                    center = _visible_image_center(digit_image)
                    if center is not None:
                        self.number_creator_font_digit_centers[str(index)] = center
                info = self.number_creator_font_info
                self.number_creator_font_status_var.set(
                    f"Font IFF: {Path(selected_template).name} | {info.width} x {info.height} | "
                    f"{info.cell_width} px cells | {info.format_label}"
                )
            except Exception as exc:  # noqa: BLE001 - GUI boundary.
                messagebox.showerror("Font IFF", str(exc))
                return
        info = self.number_creator_font_info
        selected = filedialog.asksaveasfilename(
            title="Save Modded Font IFF",
            defaultextension=".iff",
            initialfile=f"{info.source_path.stem}_modded.iff",
            filetypes=(("Font IFF files", "*font*.iff"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            sheet = self._build_number_creator_font_sheet()
            write_number_sheet_to_font_iff(info.source_path, selected, sheet)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Save Font IFF", str(exc))
            return
        self.number_creator_status.configure(text=f"Saved modded font IFF to {selected}.")

    def load_tweak_iff(self) -> None:
        selected = filedialog.askopenfilename(
            title="Load Tweak IFF",
            filetypes=(("Tweak IFF files", "*tweak*.iff"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            info = inspect_front_number_tweak(selected)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Tweak Editor", str(exc))
            return
        self.tweak_file_path = Path(selected)
        self.tweak_info = info
        self.tweak_original_values = {
            "x": info.x.value,
            "y": info.y.value,
            "width": info.width.value,
            "height": info.height.value,
        }
        self._set_tweak_values(self.tweak_original_values)
        self._capture_tweak_size_ratio()
        self._refresh_tweak_field_table()
        entry_label = info.entry_name or "raw file"
        self.tweak_status_var.set(
            f"Loaded {self.tweak_file_path.name} | {entry_label} | "
            f"{info.data_size:,} bytes of tweak data."
        )

    def save_tweak_iff_as(self) -> None:
        if self.tweak_file_path is None or self.tweak_info is None:
            messagebox.showinfo("Tweak Editor", "Load a tweak IFF first.")
            return
        try:
            values = self._current_tweak_values(validate=True)
        except ValueError as exc:
            messagebox.showerror("Tweak Editor", str(exc))
            return
        selected = filedialog.asksaveasfilename(
            title="Save Edited Tweak IFF",
            defaultextension=".iff",
            initialfile=f"{self.tweak_file_path.stem}_front_number_edit.iff",
            filetypes=(("Tweak IFF files", "*tweak*.iff"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            write_front_number_tweak(
                self.tweak_file_path,
                selected,
                x=values["x"],
                y=values["y"],
                width=values["width"],
                height=values["height"],
            )
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Tweak Editor", str(exc))
            return
        self.tweak_status_var.set(f"Saved edited tweak IFF to {selected}.")

    def reset_tweak_values(self) -> None:
        if not self.tweak_original_values:
            messagebox.showinfo("Tweak Editor", "Load a tweak IFF first.")
            return
        self._set_tweak_values(self.tweak_original_values)
        self.tweak_status_var.set("Restored the front number values from the loaded file.")

    def apply_tweak_entry(self, key: str) -> None:
        try:
            display_value = float(self.tweak_value_vars[key].get())
            value = self._tweak_display_to_raw(key, display_value)
            self._validate_tweak_value(key, value)
        except ValueError as exc:
            messagebox.showerror("Tweak Editor", str(exc))
            self._sync_tweak_value_label(key)
            return
        self._tweak_variable(key).set(value)
        self._sync_locked_tweak_size(key)
        self._sync_tweak_value_label(key)

    def _set_tweak_values(self, values: dict[str, float]) -> None:
        previous_syncing = self.tweak_lock_syncing
        self.tweak_lock_syncing = True
        try:
            for key, value in values.items():
                self._tweak_variable(key).set(value)
                self._sync_tweak_value_label(key)
        finally:
            self.tweak_lock_syncing = previous_syncing
        if self.tweak_lock_size_var.get():
            self._capture_tweak_size_ratio()

    def _on_tweak_slider_changed(self, key: str) -> None:
        if self.tweak_lock_syncing:
            return
        value = self._tweak_display_to_raw(key, self.tweak_slider_vars[key].get())
        value = self._clamp_tweak_value(key, value)
        self._tweak_variable(key).set(value)
        self._sync_locked_tweak_size(key)
        self._sync_tweak_value_label(key)

    def toggle_tweak_size_lock(self) -> None:
        if self.tweak_lock_size_var.get():
            self._capture_tweak_size_ratio()

    def _capture_tweak_size_ratio(self) -> None:
        width = self.tweak_width_var.get()
        height = self.tweak_height_var.get()
        if abs(width) > 0.000001:
            self.tweak_locked_size_ratio = height / width

    def _sync_locked_tweak_size(self, changed_key: str) -> None:
        if (
            self.tweak_lock_syncing
            or not self.tweak_lock_size_var.get()
            or changed_key not in {"width", "height"}
        ):
            return
        self.tweak_lock_syncing = True
        try:
            if changed_key == "width":
                paired_key = "height"
                paired_value = self.tweak_width_var.get() * self.tweak_locked_size_ratio
            else:
                paired_key = "width"
                if abs(self.tweak_locked_size_ratio) <= 0.000001:
                    return
                paired_value = self.tweak_height_var.get() / self.tweak_locked_size_ratio
            paired_value = self._clamp_tweak_value(paired_key, paired_value)
            self._tweak_variable(paired_key).set(paired_value)
            self._sync_tweak_value_label(paired_key)
        finally:
            self.tweak_lock_syncing = False

    def _sync_tweak_value_label(self, key: str) -> None:
        display_value = self._tweak_raw_to_display(key, self._tweak_variable(key).get())
        self.tweak_slider_vars[key].set(display_value)
        self.tweak_value_vars[key].set(f"{display_value:.6f}")

    def _tweak_variable(self, key: str) -> tk.DoubleVar:
        return {
            "x": self.tweak_x_var,
            "y": self.tweak_y_var,
            "width": self.tweak_width_var,
            "height": self.tweak_height_var,
        }[key]

    def _tweak_raw_to_display(self, key: str, value: float) -> float:
        if key == "x":
            return -value
        if key in {"width", "height"}:
            minimum, maximum = self.tweak_slider_ranges[key]
            return minimum + maximum - value
        return value

    def _tweak_display_to_raw(self, key: str, value: float) -> float:
        if key == "x":
            return -value
        if key in {"width", "height"}:
            minimum, maximum = self.tweak_slider_ranges[key]
            return minimum + maximum - value
        return value

    def _current_tweak_values(self, *, validate: bool = False) -> dict[str, float]:
        values = {
            "x": self.tweak_x_var.get(),
            "y": self.tweak_y_var.get(),
            "width": self.tweak_width_var.get(),
            "height": self.tweak_height_var.get(),
        }
        if validate:
            for key, value in values.items():
                self._validate_tweak_value(key, value)
        return values

    def _validate_tweak_value(self, key: str, value: float) -> None:
        if self.tweak_info is None:
            return
        scalar = getattr(self.tweak_info, key)
        if value < scalar.minimum or value > scalar.maximum:
            raise ValueError(
                f"{_human_label(key)} must be between "
                f"{scalar.minimum:g} and {scalar.maximum:g}."
            )

    def _clamp_tweak_value(self, key: str, value: float) -> float:
        if self.tweak_info is None:
            return value
        scalar = getattr(self.tweak_info, key)
        return min(max(value, scalar.minimum), scalar.maximum)

    def _refresh_tweak_field_table(self) -> None:
        if not hasattr(self, "tweak_fields"):
            return
        for item in self.tweak_fields.get_children():
            self.tweak_fields.delete(item)
        if self.tweak_info is None:
            return
        for key, label in (
            ("x", "X position"),
            ("y", "Y position"),
            ("width", "Width / size"),
            ("height", "Height / size"),
        ):
            scalar = getattr(self.tweak_info, key)
            self.tweak_fields.insert(
                "",
                tk.END,
                text=label,
                values=(
                    scalar.hash_id,
                    f"0x{scalar.value_offset:04x}",
                    f"{scalar.minimum:g} to {scalar.maximum:g}",
                ),
            )

    def clear_number_creator_digit(self) -> None:
        digit = self.number_creator_digit_var.get()
        self.number_creator_digit_paths.pop(digit, None)
        self._refresh_number_creator_digit_list()
        self.refresh_number_creator_sheet_preview()
        self.number_creator_status.configure(text=f"Cleared digit {digit}.")

    def load_number_creator_reference(self) -> None:
        selected = filedialog.askopenfilename(
            title="Upload Number Reference",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        self.number_creator_reference_path = Path(selected)
        self.number_creator_box_start = None
        self.number_creator_box_end = None
        self.number_creator_lasso_points = []
        self.number_creator_dragging = False
        self.number_creator_reference_zoom = 1.0
        self.number_creator_reference_zoom_label_var.set("100%")
        self._show_number_creator_reference()
        self.number_creator_status.configure(text=f"Loaded number reference: {Path(selected).name}")
        self.tabs.select(self.number_creator_tab)

    def open_number_creator_web_selector(self) -> None:
        if self.number_creator_reference_path is None:
            messagebox.showinfo("Number Set Creator", "Upload a number reference image first.")
            return
        try:
            if self.web_editor_server is None:
                self.web_editor_server = WebEditorServer(self)
            url = self.web_editor_server.start().rstrip("/") + "/number"
            webbrowser.open(url)
            self.number_creator_status.configure(text=f"Number web selector opened at {url}")
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number web selector failed", str(exc))

    def adjust_number_reference_zoom(self, factor: float) -> None:
        self.number_creator_reference_zoom = max(
            0.25,
            min(8.0, self.number_creator_reference_zoom * factor),
        )
        self.number_creator_reference_zoom_label_var.set(
            f"{round(self.number_creator_reference_zoom * 100)}%"
        )
        self._show_number_creator_reference()

    def fit_number_reference_zoom(self) -> None:
        self.number_creator_reference_zoom = 1.0
        self.number_creator_reference_zoom_label_var.set("100%")
        self._show_number_creator_reference()

    def _number_reference_mousewheel_zoom(self, event: tk.Event) -> str:
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self.adjust_number_reference_zoom(factor)
        return "break"

    def clear_number_reference_selection(self) -> None:
        self.number_creator_box_start = None
        self.number_creator_box_end = None
        self.number_creator_lasso_points = []
        self.number_creator_dragging = False
        self._show_number_creator_reference()
        self.number_creator_status.configure(text="Number reference selection cleared.")

    def use_number_reference_selection_as_digit(self) -> None:
        if self.number_creator_reference_path is None:
            messagebox.showinfo("Number Set Creator", "Upload a number reference image first.")
            return
        try:
            saved_digit, _saved_path = self._save_number_reference_selection_as_digit()
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        self.number_creator_status.configure(
            text=f"Picked reference selection as digit {saved_digit}."
        )

    def _save_number_reference_selection_as_digit(self) -> tuple[str, Path]:
        digit_image = self._number_reference_selected_image()
        digit = self.number_creator_digit_var.get()
        digit_image = self._prepare_number_digit_image_for_save(digit, digit_image)
        output_path = self._number_creator_digit_output_path(digit, prefix="picked_digit")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        digit_image.save(output_path)
        self.number_creator_digit_paths[digit] = output_path
        self._refresh_number_creator_digit_list()
        self.refresh_number_creator_sheet_preview()
        self._advance_number_creator_digit_after_save(digit)
        return digit, output_path

    def _show_number_creator_reference(self) -> None:
        if not hasattr(self, "number_creator_reference_canvas"):
            return
        canvas = self.number_creator_reference_canvas
        canvas.delete("all")
        self.number_creator_reference_rect = None
        if self.number_creator_reference_path is None or not self.number_creator_reference_path.exists():
            canvas.create_text(
                max(1, canvas.winfo_width() // 2),
                max(1, canvas.winfo_height() // 2),
                text="Upload a jersey/reference photo, then select a number.",
                fill="#c9ced8",
            )
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        canvas.update_idletasks()
        available_width = max(1, canvas.winfo_width() - 20)
        available_height = max(1, canvas.winfo_height() - 20)
        with Image.open(self.number_creator_reference_path) as opened:
            image = opened.convert("RGBA")
            fit_scale = min(available_width / image.width, available_height / image.height, 1.0)
            scale = fit_scale * self.number_creator_reference_zoom
            shown_size = (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            )
            preview = image.resize(shown_size, Image.Resampling.LANCZOS)
        self.number_creator_reference_preview_image = ImageTk.PhotoImage(preview)
        left = max(10, (canvas.winfo_width() - shown_size[0]) // 2)
        top = max(10, (canvas.winfo_height() - shown_size[1]) // 2)
        self.number_creator_reference_rect = (left, top, shown_size[0], shown_size[1])
        canvas.create_image(left, top, image=self.number_creator_reference_preview_image, anchor=tk.NW)
        canvas.configure(scrollregion=(0, 0, left + shown_size[0] + 10, top + shown_size[1] + 10))
        self._draw_number_reference_selection()

    def _draw_number_reference_selection(self) -> None:
        if not hasattr(self, "number_creator_reference_canvas"):
            return
        canvas = self.number_creator_reference_canvas
        canvas.delete("number-selection")
        if self.number_creator_pick_mode_var.get() == "Lasso":
            if len(self.number_creator_lasso_points) < 2:
                return
            points = []
            for x, y in self.number_creator_lasso_points:
                points.extend(self._number_reference_image_to_canvas(x, y))
            canvas.create_line(
                *points,
                fill="#ffd24a",
                width=2,
                tags="number-selection",
                smooth=True,
            )
            if len(self.number_creator_lasso_points) >= 3 and not self.number_creator_dragging:
                first_x, first_y = self._number_reference_image_to_canvas(*self.number_creator_lasso_points[0])
                last_x, last_y = self._number_reference_image_to_canvas(*self.number_creator_lasso_points[-1])
                canvas.create_line(
                    last_x,
                    last_y,
                    first_x,
                    first_y,
                    fill="#ffd24a",
                    width=2,
                    tags="number-selection",
                )
            return
        if self.number_creator_box_start is None or self.number_creator_box_end is None:
            return
        x1, y1 = self._number_reference_image_to_canvas(*self.number_creator_box_start)
        x2, y2 = self._number_reference_image_to_canvas(*self.number_creator_box_end)
        canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline="#ffd24a",
            width=2,
            tags="number-selection",
        )

    def _number_reference_press(self, event: tk.Event) -> None:
        point = self._number_reference_event_to_image(event)
        if point is None:
            return
        self.number_creator_dragging = True
        if self.number_creator_pick_mode_var.get() == "Lasso":
            self.number_creator_lasso_points = [point]
            self.number_creator_box_start = None
            self.number_creator_box_end = None
        else:
            self.number_creator_box_start = point
            self.number_creator_box_end = point
            self.number_creator_lasso_points = []
        self._show_number_creator_reference()

    def _number_reference_drag(self, event: tk.Event) -> None:
        point = self._number_reference_event_to_image(event)
        if point is None or not self.number_creator_dragging:
            return
        if self.number_creator_pick_mode_var.get() == "Lasso":
            if not self.number_creator_lasso_points or _distance(
                point[0],
                point[1],
                self.number_creator_lasso_points[-1][0],
                self.number_creator_lasso_points[-1][1],
            ) >= 2:
                self.number_creator_lasso_points.append(point)
        else:
            self.number_creator_box_end = point
        self._show_number_creator_reference()

    def _number_reference_release(self, event: tk.Event) -> None:
        point = self._number_reference_event_to_image(event)
        if point is not None:
            if self.number_creator_pick_mode_var.get() == "Lasso":
                self.number_creator_lasso_points.append(point)
            else:
                self.number_creator_box_end = point
        self.number_creator_dragging = False
        if self.number_creator_pick_mode_var.get() == "Lasso" and len(self.number_creator_lasso_points) < 3:
            self.number_creator_lasso_points = []
            self.number_creator_status.configure(text="Lasso needs a larger selected area.")
        self._show_number_creator_reference()

    def _number_reference_event_to_image(self, event: tk.Event) -> tuple[int, int] | None:
        if self.number_creator_reference_path is None or self.number_creator_reference_rect is None:
            return None
        try:
            from PIL import Image
        except ImportError:
            return None
        left, top, shown_width, shown_height = self.number_creator_reference_rect
        canvas = self.number_creator_reference_canvas
        canvas_x = canvas.canvasx(event.x)
        canvas_y = canvas.canvasy(event.y)
        if not (left <= canvas_x <= left + shown_width and top <= canvas_y <= top + shown_height):
            return None
        with Image.open(self.number_creator_reference_path) as image:
            width, height = image.size
        image_x = round((canvas_x - left) * width / shown_width)
        image_y = round((canvas_y - top) * height / shown_height)
        return (
            max(0, min(width - 1, image_x)),
            max(0, min(height - 1, image_y)),
        )

    def _number_reference_image_to_canvas(self, image_x: int, image_y: int) -> tuple[float, float]:
        if self.number_creator_reference_path is None or self.number_creator_reference_rect is None:
            return (0, 0)
        from PIL import Image

        left, top, shown_width, shown_height = self.number_creator_reference_rect
        with Image.open(self.number_creator_reference_path) as image:
            width, height = image.size
        return (
            left + image_x * shown_width / width,
            top + image_y * shown_height / height,
        )

    def _number_reference_selected_image(self):
        if self.number_creator_reference_path is None:
            raise ValueError("Upload a number reference image first.")
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise RuntimeError("Number reference picker requires Pillow.") from exc
        with Image.open(self.number_creator_reference_path) as opened:
            image = opened.convert("RGBA")
        if self.number_creator_pick_mode_var.get() == "Lasso":
            if len(self.number_creator_lasso_points) < 3:
                raise ValueError("Draw a lasso around a number first.")
            xs = [point[0] for point in self.number_creator_lasso_points]
            ys = [point[1] for point in self.number_creator_lasso_points]
            left = max(0, min(xs))
            top = max(0, min(ys))
            right = min(image.width, max(xs) + 1)
            bottom = min(image.height, max(ys) + 1)
            if right - left < 2 or bottom - top < 2:
                raise ValueError("Selection is too small.")
            cropped = image.crop((left, top, right, bottom))
            mask = Image.new("L", cropped.size, 0)
            points = [(x - left, y - top) for x, y in self.number_creator_lasso_points]
            ImageDraw.Draw(mask).polygon(points, fill=255)
            alpha = cropped.getchannel("A")
            cropped.putalpha(Image.composite(alpha, Image.new("L", cropped.size, 0), mask))
            return cropped
        if self.number_creator_box_start is None or self.number_creator_box_end is None:
            raise ValueError("Draw a box around a number first.")
        x1, y1 = self.number_creator_box_start
        x2, y2 = self.number_creator_box_end
        left = max(0, min(x1, x2))
        top = max(0, min(y1, y2))
        right = min(image.width, max(x1, x2) + 1)
        bottom = min(image.height, max(y1, y2) + 1)
        if right - left < 2 or bottom - top < 2:
            raise ValueError("Selection is too small.")
        return image.crop((left, top, right, bottom))

    def _number_creator_web_project(self) -> dict:
        if (
            self.number_creator_reference_path is None
            or not self.number_creator_reference_path.exists()
        ):
            return {
                "hasImage": False,
                "width": 0,
                "height": 0,
                "imageUrl": "/api/number/reference",
                "mode": self.number_creator_pick_mode_var.get(),
                "digit": self.number_creator_digit_var.get(),
                "points": [],
                "box": None,
            }
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Number selector requires Pillow.") from exc
        with Image.open(self.number_creator_reference_path) as image:
            width, height = image.size
        box = None
        if self.number_creator_box_start is not None and self.number_creator_box_end is not None:
            box = {
                "x1": self.number_creator_box_start[0],
                "y1": self.number_creator_box_start[1],
                "x2": self.number_creator_box_end[0],
                "y2": self.number_creator_box_end[1],
            }
        return {
            "hasImage": True,
            "width": width,
            "height": height,
            "imageUrl": "/api/number/reference",
            "mode": self.number_creator_pick_mode_var.get(),
            "digit": self.number_creator_digit_var.get(),
            "points": [
                {"x": x, "y": y}
                for x, y in self.number_creator_lasso_points
            ],
            "box": box,
        }

    def _number_creator_reference_image(self) -> tuple[bytes, str]:
        if (
            self.number_creator_reference_path is None
            or not self.number_creator_reference_path.exists()
        ):
            raise FileNotFoundError("No number reference image is loaded.")
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Number selector requires Pillow.") from exc
        output_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "number_creator"
            / "reference.png"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(self.number_creator_reference_path) as opened:
            opened.convert("RGBA").save(output_path)
        return output_path.read_bytes(), "image/png"

    def _number_creator_web_selection(self, payload: dict) -> dict:
        mode = str(payload.get("mode", "Box"))
        if mode not in {"Box", "Lasso"}:
            mode = "Box"
        self.number_creator_pick_mode_var.set(mode)
        self.number_creator_box_start = None
        self.number_creator_box_end = None
        self.number_creator_lasso_points = []
        if mode == "Lasso":
            points = payload.get("points", [])
            clean_points: list[tuple[int, int]] = []
            for point in points:
                try:
                    x = int(round(float(point.get("x", 0))))
                    y = int(round(float(point.get("y", 0))))
                except (AttributeError, TypeError, ValueError):
                    continue
                clean_points.append((x, y))
            self.number_creator_lasso_points = clean_points
        else:
            box = payload.get("box") or {}
            try:
                self.number_creator_box_start = (
                    int(round(float(box.get("x1", 0)))),
                    int(round(float(box.get("y1", 0)))),
                )
                self.number_creator_box_end = (
                    int(round(float(box.get("x2", 0)))),
                    int(round(float(box.get("y2", 0)))),
                )
            except (AttributeError, TypeError, ValueError):
                self.number_creator_box_start = None
                self.number_creator_box_end = None
        self._show_number_creator_reference()
        saved_digit, saved_path = self._save_number_reference_selection_as_digit()
        self.number_creator_status.configure(
            text=f"Received web {mode.lower()} and saved digit {saved_digit}."
        )
        return {"saved": saved_path.name, "digit": saved_digit}

    def _number_creator_web_clear(self) -> None:
        self.number_creator_box_start = None
        self.number_creator_box_end = None
        self.number_creator_lasso_points = []
        self._show_number_creator_reference()
        self.number_creator_status.configure(text="Number web selection cleared.")

    def refresh_number_creator_sheet_preview(self) -> None:
        if not self.number_creator_digit_paths:
            if hasattr(self, "number_creator_preview"):
                self.number_creator_preview.delete("all")
            self.number_creator_sheet_path = None
            self._redraw_generator_preview_overlays()
            self.number_creator_status.configure(text="Upload at least one digit first.")
            return
        output_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "number_creator"
            / "number_sheet_preview.png"
        )
        try:
            if self.number_creator_font_info is not None:
                sheet = self._build_number_creator_font_sheet()
                output_path.parent.mkdir(parents=True, exist_ok=True)
                sheet.save(output_path)
            else:
                self._build_number_creator_sheet(output_path, label_digits=True)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        self.number_creator_sheet_path = output_path
        self._show_number_creator_sheet_preview(output_path)
        self._redraw_generator_preview_overlays()
        self.number_creator_status.configure(text=f"Preview built with {len(self.number_creator_digit_paths)} digit(s).")

    def save_number_creator_sheet_as(self) -> None:
        if not self.number_creator_digit_paths:
            messagebox.showinfo("Number Set Creator", "Upload at least one digit first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Save Number Sheet",
            defaultextension=".png",
            initialfile="jersey_numbers_0-9.png",
            filetypes=(("PNG files", "*.png"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            self._build_number_creator_sheet(Path(selected), label_digits=False)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        self.number_creator_status.configure(text=f"Saved number sheet to {selected}.")

    def create_number_ai_reference_pack(self) -> None:
        if not self.number_creator_digit_paths:
            messagebox.showinfo("Number Set Creator", "Upload at least one example digit first.")
            return
        selected = filedialog.askdirectory(title="Choose folder for AI reference pack")
        if not selected:
            return
        folder = Path(selected)
        sheet_path = folder / "number_reference_sheet.png"
        prompt_path = folder / "ai_number_prompt.txt"
        font_sheet_path = folder / "font_game_layout_template.png"
        font_pixel_guide_path = folder / "font_pixel_guide.txt"
        try:
            self._build_number_creator_sheet(
                sheet_path,
                label_digits=True,
                reference_background=True,
            )
            if self.number_creator_font_info is not None:
                self._build_number_creator_font_sheet().save(font_sheet_path)
                font_pixel_guide_path.write_text(
                    self._number_font_pixel_guide_text(),
                    encoding="utf-8",
                )
            prompt_path.write_text(self._number_ai_prompt_text(), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        pack_files = f"{sheet_path.name} and {prompt_path.name}"
        if self.number_creator_font_info is not None:
            pack_files = (
                f"{sheet_path.name}, {font_sheet_path.name}, "
                f"{font_pixel_guide_path.name}, and {prompt_path.name}"
            )
        self.number_creator_status.configure(text=f"AI reference pack saved: {pack_files}.")

    def import_number_ai_sheet(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import AI 0-9 number sheet",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            from PIL import Image
        except ImportError as exc:
            messagebox.showerror("Number Set Creator", f"Number import requires Pillow.\n\n{exc}")
            return
        try:
            with Image.open(selected) as opened:
                sheet = opened.convert("RGBA")
            if self.number_creator_font_info is not None:
                target_size = (
                    self.number_creator_font_info.width,
                    self.number_creator_font_info.height,
                )
                if sheet.size != target_size:
                    sheet = sheet.resize(target_size, Image.Resampling.LANCZOS)
            cell_width = sheet.width // 10
            if cell_width <= 0:
                raise ValueError("The imported sheet is too narrow to split into digits.")
            preserve_font_cells = (
                self.number_creator_font_info is not None
                and sheet.size
                == (self.number_creator_font_info.width, self.number_creator_font_info.height)
            )
            for index in range(10):
                left = index * cell_width
                right = sheet.width if index == 9 else (index + 1) * cell_width
                digit = sheet.crop((left, 0, right, sheet.height))
                if not preserve_font_cells:
                    digit = self._clean_number_digit_image(digit)
                elif str(index) in self.number_creator_font_digit_centers:
                    digit = _align_image_to_visible_center(
                        digit,
                        self.number_creator_font_digit_centers[str(index)],
                    )
                output_path = self._number_creator_digit_output_path(str(index), prefix="ai_digit")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                digit.save(output_path)
                self.number_creator_digit_paths[str(index)] = output_path
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        self._refresh_number_creator_digit_list()
        self.refresh_number_creator_sheet_preview()
        status = "Imported AI sheet into digits 0-9."
        if self.number_creator_font_info is not None:
            status = "Imported AI sheet into font-sized digits 0-9."
        self.number_creator_status.configure(text=status)

    def apply_number_creator_font_nudge(self) -> None:
        if self.number_creator_font_info is None:
            messagebox.showinfo("Number Set Creator", "Import a font IFF first.")
            return
        try:
            offset_x = int(self.number_creator_nudge_x_var.get())
            offset_y = int(self.number_creator_nudge_y_var.get())
        except tk.TclError:
            messagebox.showinfo("Number Set Creator", "Enter valid nudge values.")
            return
        if offset_x == 0 and offset_y == 0:
            self.number_creator_status.configure(text="Nudge is 0, so nothing changed.")
            return
        try:
            from PIL import Image
        except ImportError as exc:
            messagebox.showerror("Number Set Creator", f"Number nudge requires Pillow.\n\n{exc}")
            return
        changed = 0
        try:
            for digit, path in list(self.number_creator_digit_paths.items()):
                if digit not in {str(index) for index in range(10)} or not path.exists():
                    continue
                with Image.open(path) as opened:
                    image = opened.convert("RGBA")
                nudged = _nudge_image(image, offset_x, offset_y)
                output_path = self._number_creator_digit_output_path(
                    digit,
                    prefix="nudged_digit",
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                nudged.save(output_path)
                self.number_creator_digit_paths[digit] = output_path
                changed += 1
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Number Set Creator", str(exc))
            return
        self.number_creator_nudge_x_var.set(0)
        self.number_creator_nudge_y_var.set(0)
        self._refresh_number_creator_digit_list()
        self.refresh_number_creator_sheet_preview()
        self.number_creator_status.configure(
            text=f"Nudged {changed} font digit(s) by X {offset_x}, Y {offset_y}."
        )

    def _select_number_creator_digit_from_list(self, _event: tk.Event) -> None:
        selected = self.number_creator_digit_list.selection()
        if not selected:
            return
        item_id = selected[0]
        if item_id.startswith("digit:"):
            self.number_creator_digit_var.set(item_id.split(":", 1)[1])

    def _selected_number_creator_digit(self) -> str:
        if hasattr(self, "number_creator_digit_list"):
            selected = self.number_creator_digit_list.selection()
            if selected and selected[0].startswith("digit:"):
                return selected[0].split(":", 1)[1]
        return self.number_creator_digit_var.get()

    def use_selected_number_creator_digit(self) -> None:
        digit = self._selected_number_creator_digit()
        self.number_creator_digit_var.set(digit)
        self.number_creator_status.configure(text=f"Selected digit {digit}.")

    def upload_selected_number_creator_digit(self) -> None:
        self.number_creator_digit_var.set(self._selected_number_creator_digit())
        self.upload_number_creator_digit()

    def clear_selected_number_creator_digit(self) -> None:
        self.number_creator_digit_var.set(self._selected_number_creator_digit())
        self.clear_number_creator_digit()

    def clear_all_number_creator_digits(self) -> None:
        self.number_creator_digit_paths.clear()
        self._refresh_number_creator_digit_list()
        if hasattr(self, "number_creator_preview"):
            self.number_creator_preview.delete("all")
        self.number_creator_sheet_path = None
        self.number_creator_status.configure(
            text="Cleared all digits. Font IFF layout and pixel guide are still loaded."
        )

    def _refresh_number_creator_digit_list(self) -> None:
        if not hasattr(self, "number_creator_digit_list"):
            return
        loaded_digits = _loaded_number_digit_keys(self.number_creator_digit_paths)
        self.number_creator_digit_list.delete(*self.number_creator_digit_list.get_children())
        for index in range(10):
            digit = str(index)
            path = self.number_creator_digit_paths.get(digit)
            self.number_creator_digit_list.insert(
                "",
                tk.END,
                iid=f"digit:{digit}",
                text=digit,
                values=(
                    "Loaded" if digit in loaded_digits else "Missing",
                    path.name if path and path.exists() else "",
                ),
            )
        current = self.number_creator_digit_var.get()
        item_id = f"digit:{current}"
        if self.number_creator_digit_list.exists(item_id):
            self.number_creator_digit_list.selection_set(item_id)
            self.number_creator_digit_list.see(item_id)

    def _advance_number_creator_digit_after_save(self, saved_digit: str) -> None:
        loaded = _loaded_number_digit_keys(self.number_creator_digit_paths)
        for index in range(int(saved_digit) + 1, 10):
            if str(index) not in loaded:
                self.number_creator_digit_var.set(str(index))
                return
        for index in range(10):
            if str(index) not in loaded:
                self.number_creator_digit_var.set(str(index))
                return
        self.number_creator_digit_var.set(saved_digit)

    def _write_clean_number_digit(self, source: Path, output_path: Path) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Number cleanup requires Pillow.") from exc
        with Image.open(source) as opened:
            image = opened.convert("RGBA")
        image = self._prepare_number_digit_image_for_save(self.number_creator_digit_var.get(), image)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)

    def _prepare_number_digit_image_for_save(self, digit: str, image):
        image = self._clean_number_digit_image(image)
        return self._align_number_digit_to_font_cell(digit, image)

    def _align_number_digit_to_font_cell(self, digit: str, image):
        if self.number_creator_font_info is None:
            return image
        target_center = self.number_creator_font_digit_centers.get(digit)
        if target_center is None:
            return image
        return _place_image_visible_center(
            image,
            (self.number_creator_font_info.cell_width, self.number_creator_font_info.height),
            target_center,
        )

    def _clean_number_digit_image(self, image):
        try:
            from .generator import (
                remove_detected_background,
                remove_image_background,
                upscale_logo_image,
            )
        except ImportError as exc:
            raise RuntimeError("Number cleanup requires Pillow.") from exc
        if self.number_creator_auto_bg_var.get():
            image = remove_detected_background(
                image,
                tolerance=self._number_creator_tolerance(),
            )
        image = remove_image_background(
            image,
            remove_white=self.number_creator_remove_white_var.get(),
            remove_black=self.number_creator_remove_black_var.get(),
            outside_only=self.number_creator_outside_only_var.get(),
            tolerance=self._number_creator_tolerance(),
        )
        image = _trim_transparent_padding(image, padding=12)
        image = upscale_logo_image(
            image,
            scale_factor=self._number_creator_upscale_factor(),
            sharpen=self.number_creator_sharpen_var.get(),
        )
        return image

    def _build_number_creator_sheet(
        self,
        output_path: Path,
        *,
        label_digits: bool,
        reference_background: bool = False,
    ) -> Path:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError as exc:
            raise RuntimeError("Number sheet export requires Pillow.") from exc
        loaded = []
        for digit, path in sorted(self.number_creator_digit_paths.items()):
            if path.exists():
                with Image.open(path) as opened:
                    loaded.append((digit, opened.convert("RGBA").copy()))
        if not loaded:
            raise ValueError("No loaded digit images were found.")
        max_width = max(image.width for _digit, image in loaded)
        max_height = max(image.height for _digit, image in loaded)
        label_height = 36 if label_digits else 0
        padding = 28
        cell_width = max(96, max_width + padding * 2)
        cell_height = max(128, max_height + padding * 2 + label_height)
        background = (255, 255, 255, 255) if reference_background else (0, 0, 0, 0)
        sheet = Image.new("RGBA", (cell_width * 10, cell_height), background)
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()
        by_digit = {digit: image for digit, image in loaded}
        for index in range(10):
            digit = str(index)
            cell_left = index * cell_width
            if label_digits:
                draw.text((cell_left + 8, 8), digit, fill=(20, 20, 20, 255), font=font)
                draw.rectangle(
                    (
                        cell_left + 1,
                        label_height - 1,
                        cell_left + cell_width - 2,
                        cell_height - 2,
                    ),
                    outline=(180, 180, 180, 255),
                )
            image = by_digit.get(digit)
            if image is None:
                if label_digits:
                    draw.text(
                        (cell_left + 8, label_height + 8),
                        "missing",
                        fill=(150, 40, 40, 255),
                        font=font,
                    )
                continue
            x = cell_left + (cell_width - image.width) // 2
            y = label_height + (cell_height - label_height - image.height) // 2
            sheet.alpha_composite(image, (x, y))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(output_path)
        return output_path

    def _build_number_creator_font_sheet(self):
        if self.number_creator_font_info is None:
            raise ValueError("Import a font IFF first so the app knows the exact game layout.")
        return build_font_number_sheet(
            self.number_creator_digit_paths,
            (self.number_creator_font_info.width, self.number_creator_font_info.height),
        )

    def _show_number_creator_sheet_preview(self, path: Path) -> None:
        if not hasattr(self, "number_creator_preview"):
            return
        self.number_creator_preview.delete("all")
        try:
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            return
        self.number_creator_preview.update_idletasks()
        width = max(1, self.number_creator_preview.winfo_width() - 20)
        height = max(1, self.number_creator_preview.winfo_height() - 20)
        with Image.open(path) as opened:
            sheet = opened.convert("RGBA")
        scale = min(width / sheet.width, height / sheet.height, 1.0)
        preview_size = (
            max(1, round(sheet.width * scale)),
            max(1, round(sheet.height * scale)),
        )
        sheet = sheet.resize(preview_size, Image.Resampling.LANCZOS)
        background = Image.new("RGBA", preview_size, (238, 238, 238, 255))
        draw = ImageDraw.Draw(background)
        square = 18
        for y in range(0, preview_size[1], square):
            for x in range(0, preview_size[0], square):
                if (x // square + y // square) % 2:
                    draw.rectangle((x, y, x + square - 1, y + square - 1), fill=(205, 205, 205, 255))
        background.alpha_composite(sheet)
        self.number_creator_preview_image = ImageTk.PhotoImage(background)
        canvas_width = self.number_creator_preview.winfo_width()
        canvas_height = self.number_creator_preview.winfo_height()
        self.number_creator_preview.create_image(
            max(10, (canvas_width - preview_size[0]) // 2),
            max(10, (canvas_height - preview_size[1]) // 2),
            image=self.number_creator_preview_image,
            anchor=tk.NW,
        )

    def _number_creator_digit_output_path(self, digit: str, *, prefix: str = "digit") -> Path:
        return (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "number_creator"
            / "digits"
            / f"{prefix}_{digit}.png"
        )

    def _number_creator_upscale_factor(self) -> int:
        value = self.number_creator_upscale_var.get().lower().strip()
        if value.startswith("4"):
            return 4
        if value.startswith("2"):
            return 2
        return 1

    def _number_creator_tolerance(self) -> int:
        try:
            return max(0, min(255, int(self.number_creator_tolerance_var.get())))
        except tk.TclError:
            return 32

    def _number_ai_prompt_text(self) -> str:
        loaded_digits = _loaded_number_digit_keys(self.number_creator_digit_paths)
        loaded = ", ".join(
            str(index)
            for index in range(10)
            if str(index) in loaded_digits
        )
        missing = ", ".join(
            str(index)
            for index in range(10)
            if str(index) not in loaded_digits
        )
        lines = [
            "Create a complete basketball jersey number set from 0 through 9.",
            "Match the uploaded examples exactly: font shape, outline, bevel, trim, color, and texture.",
            "Keep the result as one horizontal sheet with ten equal-width cells in this order: 0 1 2 3 4 5 6 7 8 9.",
            "Use a transparent background when possible. If transparency is not possible, use one solid high-contrast background color.",
            "Keep each digit centered in its cell and leave a little transparent padding around each digit.",
            "",
            f"Provided digits: {loaded or 'none'}",
            f"Missing digits to infer: {missing or 'none'}",
        ]
        if self.number_creator_font_info is not None:
            info = self.number_creator_font_info
            lines.extend(
                [
                    "",
                    "This will be imported back into an NBA 2K font IFF.",
                    f"Final PNG must be exactly {info.width} x {info.height} pixels.",
                    f"Use ten equal cells. Each cell is exactly {info.cell_width} x {info.height} pixels.",
                    "The digit 0 goes in the first cell, digit 9 goes in the last cell.",
                    "Use font_game_layout_template.png as the exact layout guide.",
                    "Use font_pixel_guide.txt for exact per-digit pixel targets.",
                    "Each digit's visible artwork center must land on its listed target absolute center.",
                    "Do not change the canvas size.",
                    "",
                    "Exact pixel targets:",
                    *self._number_font_pixel_guide_lines(),
                ]
            )
        return "\n".join(lines)

    def _number_font_pixel_guide_text(self) -> str:
        return "\n".join(
            [
                "NBA 2K font number pixel guide",
                "Use these exact pixel targets for the generated 0-9 sheet.",
                "Coordinates are measured from the top-left corner of the final PNG.",
                "",
                *self._number_font_pixel_guide_lines(),
                "",
                "Important:",
                "Do not change canvas size.",
                "Do not move digits to visual center of the cell unless that matches the target center.",
                "The visible artwork center of each generated digit should match the target absolute center.",
            ]
        )

    def _number_font_pixel_guide_lines(self) -> list[str]:
        if self.number_creator_font_info is None:
            return []
        info = self.number_creator_font_info
        lines = [
            f"Canvas: {info.width} x {info.height} px",
            f"Cell size: {info.cell_width} x {info.height} px",
        ]
        for index in range(10):
            digit = str(index)
            cell_left = index * info.cell_width
            cell_right = cell_left + info.cell_width - 1
            center = self.number_creator_font_digit_centers.get(digit)
            bbox = self.number_creator_font_digit_bounds.get(digit)
            if center is None:
                lines.append(
                    f"Digit {digit}: cell x={cell_left}-{cell_right}, y=0-{info.height - 1}; "
                    "no visible template center detected."
                )
                continue
            absolute_x = cell_left + center[0]
            absolute_y = center[1]
            detail = (
                f"Digit {digit}: cell x={cell_left}-{cell_right}, y=0-{info.height - 1}; "
                f"target visible center absolute=({absolute_x:.1f}, {absolute_y:.1f}); "
                f"target visible center inside cell=({center[0]:.1f}, {center[1]:.1f})"
            )
            if bbox is not None:
                left, top, right, bottom = bbox
                detail += f"; original visible bbox inside cell=({left}, {top}, {right - 1}, {bottom - 1})"
            lines.append(detail)
        return lines

    def upload_fabric_overlay(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select fabric or wrinkle overlay",
            filetypes=(
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        self.custom_fabric_overlay_path = Path(selected)
        self.fabric_overlay_var.set("Custom upload")
        if self.fabric_overlay_opacity_var.get() == 0:
            self.fabric_overlay_opacity_var.set(25)
        self._schedule_generator_preview_refresh()

    def remove_selected_generator_logo(self) -> None:
        selected = self.generator_logo_list.selection()
        if not selected:
            return
        indexes = sorted(
            (int(item_id.split(":")[1]) for item_id in selected),
            reverse=True,
        )
        for index in indexes:
            if 0 <= index < len(self.generator_logo_placements):
                del self.generator_logo_placements[index]
        self._reindex_logo_web_editor_state(indexes)
        self._refresh_generator_logo_list()
        self._schedule_generator_preview_refresh()

    def _reindex_logo_web_editor_state(self, removed_indexes: list[int]) -> None:
        removed = set(removed_indexes)

        def reindex_key(key: str) -> str | None:
            if not key.startswith("logo:"):
                return key
            index = int(key.split(":")[1])
            if index in removed:
                return None
            shift = sum(1 for removed_index in removed if removed_index < index)
            return f"logo:{index - shift}"

        self.web_editor_layer_order = [
            new_key
            for key in self.web_editor_layer_order
            if (new_key := reindex_key(key)) is not None
        ]
        self.web_editor_layer_cleanup = {
            new_key: cleanup
            for key, cleanup in self.web_editor_layer_cleanup.items()
            if (new_key := reindex_key(key)) is not None
        }

    def _refresh_generator_logo_list(self) -> None:
        self.generator_logo_list.delete(*self.generator_logo_list.get_children())
        labels_by_target = {
            target: label for label, target in self.generator_logo_target_names.items()
        }
        for index, placement in enumerate(self.generator_logo_placements):
            self.generator_logo_list.insert(
                "",
                tk.END,
                iid=f"logo:{index}",
                values=(
                    labels_by_target.get(
                        placement.target_name,
                        _logo_type_label(placement.target_name),
                    ),
                    placement.path.name,
                ),
            )

    def reset_front_wordmark_position(self) -> None:
        self.front_wordmark_offset_x_var.set(0)
        self.front_wordmark_offset_y_var.set(0)
        self.front_wordmark_scale_var.set(100)

    def open_web_editor(self) -> None:
        try:
            if self.web_editor_server is None:
                self.web_editor_server = WebEditorServer(self)
            url = self.web_editor_server.start()
            webbrowser.open(url)
            self.generator_status.configure(text=f"Web editor opened at {url}")
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Web editor failed", str(exc))

    def _run_on_ui_thread(self, callback):
        if threading.current_thread() is self.ui_thread:
            return callback()
        done = threading.Event()
        result: dict = {}

        def run_callback() -> None:
            try:
                result["value"] = callback()
            except Exception as exc:  # noqa: BLE001 - crosses thread boundary.
                result["error"] = exc
            finally:
                done.set()

        self.after(0, run_callback)
        if not done.wait(10):
            raise TimeoutError("The desktop app did not respond to the web editor.")
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def _web_editor_project(self) -> dict:
        template = self._current_generator_template()
        inputs = self._generator_inputs()
        overlays = []
        for placement in image_placement_rects(template, inputs):
            is_trim = placement.key in TRIM_GENERATOR_KEYS
            is_side_panel = placement.key in SIDE_PANEL_GENERATOR_KEYS
            logo_index = (
                int(placement.key.split(":")[1])
                if placement.key.startswith("logo:")
                else None
            )
            overlays.append(
                {
                    "key": placement.key,
                    "label": placement.label,
                    "x": placement.x,
                    "y": placement.y,
                    "width": placement.width,
                    "height": placement.height,
                    "imageUrl": f"/api/image/{placement.key}?",
                    "blendMode": "normal",
                    "lockX": self._web_editor_overlay_locks_x(placement.key),
                    "lockAspect": not is_side_panel,
                    "canTransform": True,
                    "canRotate": is_side_panel,
                    "rotation": placement.rotation_degrees,
                    "canFlip": is_trim,
                    "flipX": self.generator_trim_placements.get(
                        placement.key,
                        TrimPlacementSettings(),
                    ).flip_x if is_trim else False,
                    "clipBox": (
                        {
                            "x": placement.clip_x,
                            "y": placement.clip_y,
                            "width": placement.clip_width,
                            "height": placement.clip_height,
                        }
                        if placement.clip_x is not None and not is_side_panel
                        else None
                    ),
                    "guideBox": (
                        {
                            "x": placement.clip_x,
                            "y": placement.clip_y,
                            "width": placement.clip_width,
                            "height": placement.clip_height,
                        }
                        if placement.clip_x is not None and is_side_panel
                        else None
                    ),
                    "canCleanup": True,
                    "cleanup": self._web_editor_cleanup_payload(placement.key),
                    "canReorder": placement.key.startswith("logo:"),
                    "layerLabel": (
                        "Top layer"
                        if placement.key == "front_wordmark"
                        else "Side panel layer"
                        if is_side_panel
                        else "Trim layer"
                        if is_trim
                        else f"Logo layer {logo_index + 1}"
                        if logo_index is not None
                        else "Layer"
                    ),
                }
            )
        fabric_layer = fabric_overlay_layer(template, inputs, (2048, 2048))
        if fabric_layer is not None:
            overlays.append(
                {
                    "key": "fabric_overlay",
                    "label": "Fabric / Wrinkle Overlay",
                    "x": 0,
                    "y": 0,
                    "width": 2048,
                    "height": 2048,
                    "imageUrl": "/api/image/fabric_overlay?",
                    "blendMode": fabric_layer.blend_mode,
                    "lockX": True,
                    "canTransform": False,
                    "canCleanup": False,
                    "cleanup": self._web_editor_cleanup_payload("fabric_overlay"),
                    "canReorder": True,
                    "layerLabel": f"{fabric_layer.blend_mode.title()} layer",
                }
            )
        overlays = self._web_editor_order_layers(overlays)
        preview_number = self._web_editor_preview_number_overlay()
        if preview_number is not None:
            overlays.append(preview_number)
        return {
            "textureSize": 2048,
            "baseUrl": "/api/base.png",
            "uvOverlay": self._web_editor_uv_overlay_payload(),
            "overlays": overlays,
        }

    def _web_editor_uv_overlay_payload(self) -> dict:
        uv_path = self._current_generator_uv_map_path()
        return {
            "available": uv_path.exists(),
            "imageUrl": "/api/uv.png",
            "enabled": self.generator_uv_overlay_var.get(),
            "opacity": self.generator_uv_overlay_opacity_var.get(),
        }

    def _web_editor_order_layers(self, overlays: list[dict]) -> list[dict]:
        preview_layers = [item for item in overlays if item["key"] == "preview_number"]
        top_layers = [item for item in overlays if item["key"] == "front_wordmark"]
        reorderable = [
            item
            for item in overlays
            if item["key"] not in {"front_wordmark", "preview_number"} and item.get("canReorder")
        ]
        fixed = [
            item
            for item in overlays
            if item["key"] not in {"front_wordmark", "preview_number"} and not item.get("canReorder")
        ]
        ordered_keys = self._active_dynamic_layer_order(
            [item["key"] for item in reorderable]
        )
        by_key = {item["key"]: item for item in reorderable}
        ordered = fixed + [by_key[key] for key in ordered_keys if key in by_key]
        ordered.extend(
            item for item in reorderable if item["key"] not in {entry["key"] for entry in ordered}
        )
        for index, item in enumerate(ordered, start=1):
            if item["key"].startswith("logo:") or item["key"] == "fabric_overlay":
                item["layerLabel"] = f"Layer {index}"
        ordered.extend(top_layers)
        ordered.extend(preview_layers)
        return ordered

    def _web_editor_preview_number_overlay(self) -> dict | None:
        if not self._generator_number_preview_available():
            return None
        image = self._build_generator_number_preview_image()
        if image is None:
            return None
        scale = self._generator_number_preview_scale()
        try:
            x = max(0, min(2048, int(self.generator_number_preview_x_var.get())))
            y = max(0, min(2048, int(self.generator_number_preview_y_var.get())))
        except tk.TclError:
            x, y = 1160, 780
        self.generator_number_preview_x_var.set(x)
        self.generator_number_preview_y_var.set(y)
        return {
            "key": "preview_number",
            "label": "Preview Number",
            "x": x,
            "y": y,
            "width": max(1, round(image.width * scale / 100)),
            "height": max(1, round(image.height * scale / 100)),
            "imageUrl": "/api/image/preview_number?",
            "blendMode": "normal",
            "lockX": False,
            "canTransform": True,
            "canFlip": False,
            "flipX": False,
            "clipBox": None,
            "canCleanup": False,
            "cleanup": self._web_editor_cleanup_payload("preview_number"),
            "canReorder": False,
            "layerLabel": "Preview only - not exported",
        }

    def _active_dynamic_layer_order(self, current_keys: list[str] | None = None) -> tuple[str, ...]:
        if current_keys is None:
            current_keys = [f"logo:{index}" for index in range(len(self.generator_logo_placements))]
            if self._fabric_overlay_path() is not None and self._fabric_overlay_opacity() > 0:
                current_keys.append("fabric_overlay")

        seen: set[str] = set()
        cleaned = []
        for key in self.web_editor_layer_order:
            if key in current_keys and key not in seen:
                cleaned.append(key)
                seen.add(key)
        cleaned.extend(key for key in current_keys if key not in seen)
        self.web_editor_layer_order = cleaned
        return tuple(cleaned)

    def _web_editor_cleanup_payload(self, key: str) -> dict:
        cleanup = self._web_editor_cleanup_for_key(key)
        return {
            "autoBackground": cleanup.auto_background,
            "removeWhite": cleanup.remove_white,
            "removeBlack": cleanup.remove_black,
            "outsideOnly": cleanup.outside_only,
            "tolerance": cleanup.tolerance,
            "isOverride": key in self.web_editor_layer_cleanup,
        }

    def _web_editor_cleanup_for_key(self, key: str) -> BackgroundCleanupSettings:
        if key in self.web_editor_layer_cleanup:
            return self.web_editor_layer_cleanup[key]
        return BackgroundCleanupSettings(
            remove_white=self.generator_remove_white_var.get(),
            remove_black=self.generator_remove_black_var.get(),
            outside_only=self.generator_outside_only_var.get(),
            tolerance=self._generator_background_tolerance(),
        )

    def _web_editor_overlay_locks_x(self, key: str) -> bool:
        if not key.startswith("logo:"):
            return False
        index = int(key.split(":")[1])
        return (
            0 <= index < len(self.generator_logo_placements)
            and self.generator_logo_placements[index].stretch_x
        )

    def _web_editor_base_png(self) -> bytes:
        template = self._current_generator_template()
        inputs = self._generator_inputs()
        base_inputs = replace(
            inputs,
            left_panel_image=None,
            right_panel_image=None,
            front_wordmark_image=None,
            left_arm_hole_trim_image=None,
            right_arm_hole_trim_image=None,
            collar_trim_image=None,
            logo_placements=(),
            fabric_overlay_image=None,
            fabric_overlay_opacity=0,
        )
        output_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "web_editor"
            / "base.png"
        )
        generate_jersey_texture(template, base_inputs, output_path)
        return output_path.read_bytes()

    def _web_editor_region_png(self) -> bytes:
        template = load_template(MASTER_TEMPLATE_ZONES)
        output_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "web_editor"
            / "jersey_region_preview.png"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = render_jersey_region_map(
            template,
            self._generator_inputs(),
            JERSEY_REGION_TEMPLATE_IMAGE,
            size=(2048, 2048),
        )
        image.save(output_path)
        return output_path.read_bytes()

    def _web_editor_uv_png(self) -> bytes:
        uv_path = self._current_generator_uv_map_path()
        if not uv_path.exists():
            raise FileNotFoundError("No UV overlay is available for this template.")
        return uv_path.read_bytes()

    def _web_editor_image(self, key: str) -> tuple[bytes, str]:
        if key == "front_wordmark":
            path = self.generator_paths["front_wordmark_image"]
        elif key == "preview_number":
            image = self._build_generator_number_preview_image()
            if image is None:
                raise FileNotFoundError("No preview number is available.")
            output_path = (
                Path(tempfile.gettempdir())
                / "nba2k_jersey_modder"
                / "web_editor"
                / "preview_number.png"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path)
            return output_path.read_bytes(), "image/png"
        elif key in TRIM_GENERATOR_KEYS:
            path = self.generator_paths[TRIM_GENERATOR_KEYS[key]]
        elif key in SIDE_PANEL_GENERATOR_KEYS:
            path = self.generator_paths[SIDE_PANEL_GENERATOR_KEYS[key]]
        elif key == "fabric_overlay":
            template = self._current_generator_template()
            layer = fabric_overlay_layer(template, self._generator_inputs(), (2048, 2048))
            if layer is None:
                raise FileNotFoundError("No fabric overlay is active.")
            output_path = (
                Path(tempfile.gettempdir())
                / "nba2k_jersey_modder"
                / "web_editor"
                / "fabric_overlay.png"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            layer.image.save(output_path)
            return output_path.read_bytes(), "image/png"
        elif key.startswith("logo:"):
            index = int(key.split(":")[1])
            path = (
                self.generator_logo_placements[index].path
                if 0 <= index < len(self.generator_logo_placements)
                else None
            )
        else:
            path = None
        if path is None or not path.exists():
            raise FileNotFoundError(f"No image found for {key}.")
        output_path = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / "web_editor"
            / f"{self._safe_web_editor_key(key)}.png"
        )
        self._write_cleaned_web_editor_image(key, path, output_path)
        return output_path.read_bytes(), "image/png"

    def _write_cleaned_web_editor_image(self, key: str, source: Path, output_path: Path) -> None:
        from PIL import Image

        from .generator import remove_detected_background, remove_image_background

        cleanup = self._web_editor_cleanup_for_key(key)
        image = Image.open(source).convert("RGBA")
        if cleanup.auto_background:
            image = remove_detected_background(
                image,
                tolerance=cleanup.tolerance,
            )
        image = remove_image_background(
            image,
            remove_white=cleanup.remove_white,
            remove_black=cleanup.remove_black,
            outside_only=cleanup.outside_only,
            tolerance=cleanup.tolerance,
        )
        if key in TRIM_GENERATOR_KEYS and self.generator_trim_placements.get(
            key,
            TrimPlacementSettings(),
        ).flip_x:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)

    def _safe_web_editor_key(self, key: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", key)

    def _web_editor_update(self, payload: dict) -> None:
        key = str(payload.get("key", ""))
        if key == "fabric_overlay":
            return
        x = float(payload.get("x", 0))
        y = float(payload.get("y", 0))
        width = max(1.0, float(payload.get("width", 1)))
        height = max(1.0, float(payload.get("height", 1)))
        rotation = float(payload.get("rotation", 0))
        if key == "preview_number":
            image = self._build_generator_number_preview_image()
            if image is None:
                return
            self.generator_number_preview_x_var.set(max(0, min(2048, round(x))))
            self.generator_number_preview_y_var.set(max(0, min(2048, round(y))))
            scale = round(100 * width / max(1, image.width))
            self.generator_number_preview_scale_var.set(max(5, min(500, scale)))
            self._redraw_generator_preview_overlays()
            return
        template = self._current_generator_template()
        inputs = self._generator_inputs()
        placements = {placement.key: placement for placement in image_placement_rects(template, inputs)}
        current = placements.get(key)
        if current is None:
            return
        if key in TRIM_GENERATOR_KEYS and current.clip_x is not None:
            x, y, width, height = _clamp_overlay_to_clip(
                x,
                y,
                width,
                height,
                current.clip_x,
                current.clip_y or 0,
                current.clip_width or 1,
                current.clip_height or 1,
            )
        delta_x = round(x - current.x)
        delta_y = round(y - current.y)

        if key == "front_wordmark":
            scale = round(
                self._front_wordmark_scale_percent() * width / max(1, current.width)
            )
            self.front_wordmark_offset_x_var.set(self._front_wordmark_offset_x() + delta_x)
            self.front_wordmark_offset_y_var.set(self._front_wordmark_offset_y() + delta_y)
            self.front_wordmark_scale_var.set(max(1, min(500, scale)))
        elif key.startswith("logo:"):
            index = int(key.split(":")[1])
            if not (0 <= index < len(self.generator_logo_placements)):
                return
            logo = self.generator_logo_placements[index]
            if logo.stretch_x:
                scale = round(logo.scale_percent * height / max(1, current.height))
                updated = replace(
                    logo,
                    offset_x=0,
                    offset_y=logo.offset_y + delta_y,
                    scale_percent=max(1, min(500, scale)),
                )
            else:
                scale = round(logo.scale_percent * width / max(1, current.width))
                updated = replace(
                    logo,
                    offset_x=logo.offset_x + delta_x,
                    offset_y=logo.offset_y + delta_y,
                    scale_percent=max(1, min(500, scale)),
                )
            self.generator_logo_placements[index] = updated
            self._refresh_generator_logo_list()
        elif key in TRIM_GENERATOR_KEYS:
            trim = self.generator_trim_placements.get(key, TrimPlacementSettings())
            scale = round(trim.scale_percent * width / max(1, current.width))
            self.generator_trim_placements[key] = replace(
                trim,
                offset_x=trim.offset_x + delta_x,
                offset_y=trim.offset_y + delta_y,
                scale_percent=max(1, min(500, scale)),
            )
        elif key in SIDE_PANEL_GENERATOR_KEYS:
            panel = self.generator_trim_placements.get(key, TrimPlacementSettings())
            width_scale = _scale_dimension_percent(
                panel.scale_width_percent,
                panel.scale_percent,
                width,
                current.width,
            )
            height_scale = _scale_dimension_percent(
                panel.scale_height_percent,
                panel.scale_percent,
                height,
                current.height,
            )
            self.generator_trim_placements[key] = replace(
                panel,
                offset_x=panel.offset_x + delta_x,
                offset_y=panel.offset_y + delta_y,
                scale_percent=width_scale,
                scale_width_percent=width_scale,
                scale_height_percent=height_scale,
                rotation_degrees=rotation,
            )
        self._schedule_generator_preview_refresh()

    def _web_editor_flip(self, payload: dict) -> None:
        key = str(payload.get("key", ""))
        if key not in TRIM_GENERATOR_KEYS:
            return
        trim = self.generator_trim_placements.get(key, TrimPlacementSettings())
        self.generator_trim_placements[key] = replace(trim, flip_x=not trim.flip_x)
        self._schedule_generator_preview_refresh()

    def _web_editor_transparency(self, payload: dict) -> None:
        key = str(payload.get("key", ""))
        if not key or key == "fabric_overlay":
            return
        if payload.get("clearOverride"):
            self.web_editor_layer_cleanup.pop(key, None)
            self._schedule_generator_preview_refresh()
            return
        cleanup = BackgroundCleanupSettings(
            auto_background=bool(payload.get("autoBackground", False)),
            remove_white=bool(payload.get("removeWhite", False)),
            remove_black=bool(payload.get("removeBlack", False)),
            outside_only=bool(payload.get("outsideOnly", True)),
            tolerance=max(0, min(255, int(payload.get("tolerance", 32)))),
        )
        self.web_editor_layer_cleanup[key] = cleanup
        self._schedule_generator_preview_refresh()

    def _web_editor_reorder(self, payload: dict) -> None:
        key = str(payload.get("key", ""))
        direction = str(payload.get("direction", ""))
        current = list(self._active_dynamic_layer_order())
        if key not in current:
            return
        index = current.index(key)
        if direction == "up":
            target = index + 1
        elif direction == "down":
            target = index - 1
        else:
            return
        if not (0 <= target < len(current)):
            return
        current[index], current[target] = current[target], current[index]
        self.web_editor_layer_order = current
        self._schedule_generator_preview_refresh()

    def _web_editor_reset(self) -> None:
        self.front_wordmark_offset_x_var.set(0)
        self.front_wordmark_offset_y_var.set(0)
        self.front_wordmark_scale_var.set(100)
        self.generator_logo_placements = [
            replace(
                placement,
                offset_x=0,
                offset_y=0,
                scale_percent=100,
            )
            for placement in self.generator_logo_placements
        ]
        self.generator_trim_placements.clear()
        self.reset_generator_number_preview()
        self.web_editor_layer_order.clear()
        self.web_editor_layer_cleanup.clear()
        self._refresh_generator_logo_list()
        self._schedule_generator_preview_refresh()
        self.generator_status.configure(text="Web editor edits reset.")

    def create_texture_from_generator(self) -> None:
        self._render_texture_creator_from_generator(
            select_tab=True,
            update_status=True,
            show_errors=True,
        )

    def _render_texture_creator_from_generator(
        self,
        *,
        select_tab: bool,
        update_status: bool,
        show_errors: bool,
    ) -> bool:
        output_dir = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "texture_creator"
        output_dir.mkdir(parents=True, exist_ok=True)
        garment = self.texture_creator_garment_var.get()
        texture_type = self.texture_creator_texture_type_var.get()
        try:
            if texture_type == "Region Texture":
                if garment != "Jersey":
                    if show_errors:
                        messagebox.showinfo(
                            "Texture Creator",
                            "Region texture creation is currently built for jersey textures. Shorts region creation can be added next.",
                        )
                    return False
                image = render_jersey_region_map(
                    self._texture_creator_template(),
                    self._generator_inputs(),
                    JERSEY_REGION_TEMPLATE_IMAGE,
                )
                output_path = output_dir / "texture_creator_jersey_region.png"
                image.save(output_path)
            elif texture_type == "Normal Map":
                if garment != "Jersey":
                    if show_errors:
                        messagebox.showinfo(
                            "Texture Creator",
                            "Normal map creation is currently built for jersey textures. Shorts normal maps can be added next.",
                        )
                    return False
                image = render_jersey_normal_map(
                    self._texture_creator_template(),
                    self._generator_inputs(),
                    JERSEY_NORMAL_TEMPLATE_IMAGE,
                    normal_strength=self._texture_creator_normal_strength(),
                )
                output_path = output_dir / "texture_creator_jersey_normal.png"
                image.save(output_path)
            else:
                output_name = (
                    "texture_creator_shorts_color.png"
                    if garment == "Shorts"
                    else "texture_creator_jersey_color.png"
                )
                output_path = output_dir / output_name
                image = render_jersey_texture(
                    self._texture_creator_template(),
                    self._generator_inputs(),
                )
                image.save(output_path)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            if show_errors:
                messagebox.showerror("Texture creation failed", str(exc))
            return False

        self.texture_creator_source_var.set("Current generator design")
        self.texture_creator_source_path = None
        self.texture_creator_preview_path = output_path
        self._show_texture_creator_preview()
        if update_status:
            self.texture_creator_status.configure(
                text=f"Created {garment.lower()} {texture_type.lower()} from the generator."
            )
        if select_tab:
            self.tabs.select(self.texture_creator_tab)
        return True

    def open_blender_preview(self) -> None:
        if self.texture_creator_garment_var.get() != "Jersey":
            messagebox.showinfo(
                "Blender Preview",
                "The current Blender preview is built for the retro jersey model. Shorts preview can be added once a shorts model is available.",
            )
            return
        if not BLENDER_PREVIEW_BLEND.exists():
            messagebox.showerror(
                "Blender Preview",
                f"Could not find the preview model:\n{BLENDER_PREVIEW_BLEND}",
            )
            return
        if not BLENDER_PREVIEW_SCRIPT.exists():
            messagebox.showerror(
                "Blender Preview",
                f"Could not find the Blender preview helper:\n{BLENDER_PREVIEW_SCRIPT}",
            )
            return
        blender_path = self._find_blender_executable()
        if blender_path is None:
            messagebox.showinfo("Blender Preview", "Choose your blender.exe to open the preview.")
            selected = filedialog.askopenfilename(
                title="Choose blender.exe",
                filetypes=(("Blender", "blender.exe"), ("All files", "*.*")),
            )
            if not selected:
                return
            blender_path = Path(selected)

        try:
            color_path, normal_path, settings_path = self._write_blender_preview_files()
            subprocess.Popen(
                [
                    str(blender_path),
                    str(BLENDER_PREVIEW_BLEND),
                    "--python",
                    str(BLENDER_PREVIEW_SCRIPT),
                    "--",
                    str(color_path),
                    str(normal_path),
                    str(self._blender_preview_normal_node_strength()),
                    str(settings_path),
                ],
                cwd=str(PROJECT_ROOT),
            )
            self.blender_preview_live_refresh = True
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Blender Preview failed", str(exc))
            return

        self.texture_creator_source_var.set("Current generator design")
        self.texture_creator_preview_path = color_path
        self.texture_creator_source_path = None
        self._show_texture_creator_preview()
        preview_mode = (
            "with the normal map"
            if self.texture_creator_blender_normal_var.get()
            else "color only"
        )
        self.texture_creator_status.configure(
            text=f"Opened Blender preview {preview_mode}."
        )
        self.tabs.select(self.texture_creator_tab)

    def _blender_preview_output_paths(self) -> tuple[Path, Path, Path]:
        output_dir = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "blender_preview"
        output_dir.mkdir(parents=True, exist_ok=True)
        return (
            output_dir / "jersey_preview_color.png",
            output_dir / "jersey_preview_normal.png",
            output_dir / "preview_settings.json",
        )

    def _write_blender_preview_files(self) -> tuple[Path, Path, Path]:
        color_path, normal_path, settings_path = self._blender_preview_output_paths()
        template = self._texture_creator_template()
        inputs = self._generator_inputs()
        color_image = render_jersey_texture(template, inputs)
        color_image = self._apply_blender_number_preview(color_image)
        normal_image = render_jersey_normal_map(
            template,
            inputs,
            JERSEY_NORMAL_TEMPLATE_IMAGE,
            normal_strength=self._texture_creator_normal_strength(),
        )
        color_image.save(color_path)
        normal_image.save(normal_path)
        settings_path.write_text(
            json.dumps(
                {
                    "color_path": str(color_path),
                    "normal_path": str(normal_path),
                    "normal_strength": self._blender_preview_normal_node_strength(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return color_path, normal_path, settings_path

    def _apply_blender_number_preview(self, color_image):
        if not self._generator_number_preview_available():
            return color_image
        try:
            from PIL import Image
        except ImportError:
            return color_image
        number = self._build_generator_number_preview_image()
        if number is None:
            return color_image
        scale_percent = self._generator_number_preview_scale()
        number = number.resize(
            (
                max(1, round(number.width * scale_percent / 100)),
                max(1, round(number.height * scale_percent / 100)),
            ),
            Image.Resampling.LANCZOS,
        )
        try:
            x = max(0, min(2048, int(self.generator_number_preview_x_var.get())))
            y = max(0, min(2048, int(self.generator_number_preview_y_var.get())))
        except tk.TclError:
            x, y = 1160, 780
        self.generator_number_preview_x_var.set(x)
        self.generator_number_preview_y_var.set(y)
        return _paste_image_on_canvas(number, color_image.copy(), x, y)

    def _refresh_blender_preview_files_if_active(self) -> None:
        if not self.blender_preview_live_refresh:
            return
        if self.texture_creator_garment_var.get() != "Jersey":
            return
        if self.blender_preview_refresh_after_id is not None:
            self.after_cancel(self.blender_preview_refresh_after_id)
        self.blender_preview_refresh_after_id = self.after(
            250,
            self._run_scheduled_blender_preview_refresh,
        )

    def _run_scheduled_blender_preview_refresh(self) -> None:
        self.blender_preview_refresh_after_id = None
        if self.blender_preview_refresh_running:
            self._refresh_blender_preview_files_if_active()
            return
        self.blender_preview_refresh_running = True
        try:
            self._write_blender_preview_files()
        except Exception:
            pass
        finally:
            self.blender_preview_refresh_running = False

    def _blender_preview_normal_node_strength(self) -> float:
        return 0.35 if self.texture_creator_blender_normal_var.get() else 0.0

    def _find_blender_executable(self) -> Path | None:
        from_path = shutil.which("blender")
        if from_path:
            return Path(from_path)
        for candidate in BLENDER_EXECUTABLE_CANDIDATES:
            if candidate.exists():
                return candidate
        return None

    def _texture_creator_normal_strength(self) -> int:
        try:
            value = self.texture_creator_normal_strength_var.get()
        except tk.TclError:
            return 15
        return max(0, min(100, int(value)))

    def _on_texture_creator_normal_strength_changed(self, _value: str | None = None) -> None:
        self.texture_creator_normal_strength_label_var.set(
            f"{self._texture_creator_normal_strength()}%"
        )
        self._schedule_texture_creator_auto_refresh()
        self._refresh_blender_preview_files_if_active()

    def _on_texture_creator_blender_normal_changed(self) -> None:
        self._refresh_blender_preview_files_if_active()

    def _texture_creator_template(self) -> JerseyTemplate:
        if self.texture_creator_garment_var.get() == "Shorts":
            _image_path, zones_path = SHORTS_TEMPLATE_OPTIONS.get(
                self.texture_creator_shorts_template_var.get(),
                SHORTS_TEMPLATE_OPTIONS["Retro shorts"],
            )
            return load_template(zones_path)
        zones_path = JERSEY_CUT_TEMPLATE_OPTIONS.get(
            self.texture_creator_jersey_cut_var.get(),
            MASTER_TEMPLATE_ZONES,
        )
        return load_template(zones_path)

    def _on_texture_creator_template_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_texture_creator_template_controls()
        self._schedule_texture_creator_auto_refresh()

    def _on_texture_creator_options_changed(self, _event: tk.Event | None = None) -> None:
        self._schedule_texture_creator_auto_refresh()

    def _schedule_texture_creator_auto_refresh(self) -> None:
        if self.texture_creator_source_var.get() != "Current generator design":
            return
        if self.texture_creator_refresh_after_id is not None:
            self.after_cancel(self.texture_creator_refresh_after_id)
        self.texture_creator_refresh_after_id = self.after(
            180,
            self._run_scheduled_texture_creator_auto_refresh,
        )

    def _run_scheduled_texture_creator_auto_refresh(self) -> None:
        self.texture_creator_refresh_after_id = None
        if self.texture_creator_refresh_running:
            self._schedule_texture_creator_auto_refresh()
            return
        self.texture_creator_refresh_running = True
        try:
            updated = self._render_texture_creator_from_generator(
                select_tab=False,
                update_status=False,
                show_errors=False,
            )
            if updated and hasattr(self, "texture_creator_status"):
                self.texture_creator_status.configure(
                    text="Texture Creator preview updated from the generator."
                )
        finally:
            self.texture_creator_refresh_running = False

    def _sync_texture_creator_template_controls(self) -> None:
        is_shorts = self.texture_creator_garment_var.get() == "Shorts"
        self.texture_creator_cut_label.configure(text="Shorts" if is_shorts else "Jersey")
        if is_shorts:
            self.texture_creator_jersey_cut_box.grid_remove()
            self.texture_creator_shorts_template_box.grid()
        else:
            self.texture_creator_shorts_template_box.grid_remove()
            self.texture_creator_jersey_cut_box.grid()

    def upload_texture_creator_source(self) -> None:
        selected = filedialog.askopenfilename(
            title="Upload Texture",
            filetypes=(
                ("Texture files", "*.png *.dds *.psd *.pds"),
                ("PNG files", "*.png"),
                ("DDS files", "*.dds"),
                ("Photoshop files", "*.psd *.pds"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        source = Path(selected)
        try:
            normalized = self._normalize_texture_creator_source(source)
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror(
                "Upload failed",
                f"Could not read this texture. Try exporting a flat PNG from Photoshop first.\n\n{exc}",
            )
            return
        self.texture_creator_source_var.set("Uploaded file")
        self.texture_creator_source_path = source
        self.texture_creator_preview_path = normalized
        self._show_texture_creator_preview()
        self.texture_creator_status.configure(text=f"Loaded {source.name}.")
        self.tabs.select(self.texture_creator_tab)

    def _normalize_texture_creator_source(self, source: Path) -> Path:
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Texture Creator uploads require Pillow.") from exc

        output_dir = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "texture_creator"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "uploaded_texture_preview.png"
        with Image.open(source) as opened:
            image = opened.convert("RGBA")
            image.save(output_path)
        return output_path

    def save_texture_creator_png_as(self) -> None:
        if self.texture_creator_preview_path is None or not self.texture_creator_preview_path.exists():
            messagebox.showinfo("Save PNG", "Create or upload a texture first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Save Texture as PNG",
            defaultextension=".png",
            filetypes=(("PNG files", "*.png"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            Path(selected).write_bytes(self.texture_creator_preview_path.read_bytes())
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.texture_creator_status.configure(text=f"Saved PNG texture to {selected}.")

    def save_texture_creator_dds_as(self) -> None:
        if self.texture_creator_preview_path is None or not self.texture_creator_preview_path.exists():
            messagebox.showinfo("Save DDS BC1", "Create or upload a texture first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Save Texture as DDS BC1",
            defaultextension=".dds",
            filetypes=(("DDS files", "*.dds"), ("All files", "*.*")),
        )
        if not selected:
            return
        source = self.texture_creator_preview_path
        target = Path(selected)
        self.texture_creator_status.configure(text=f"Saving BC1 DDS texture to {selected}...")
        thread = threading.Thread(
            target=self._save_texture_creator_dds_worker,
            args=(source, target),
            daemon=True,
        )
        thread.start()

    def _save_texture_creator_dds_worker(self, source: Path, target: Path) -> None:
        try:
            save_bc1_dds(source, target)
        except Exception as exc:  # noqa: BLE001 - background GUI boundary.
            self.after(0, lambda: self._finish_texture_creator_dds_save(target, exc))
            return
        self.after(0, lambda: self._finish_texture_creator_dds_save(target, None))

    def _finish_texture_creator_dds_save(self, target: Path, error: Exception | None) -> None:
        if error is not None:
            messagebox.showerror("DDS save failed", str(error))
            self.texture_creator_status.configure(text="DDS save failed.")
            return
        self.texture_creator_status.configure(text=f"Saved BC1 DDS texture to {target}.")

    def _show_texture_creator_preview(self) -> None:
        if not hasattr(self, "texture_creator_preview"):
            return
        self.texture_creator_preview.delete("all")
        path = self.texture_creator_preview_path
        canvas_width = max(1, self.texture_creator_preview.winfo_width())
        canvas_height = max(1, self.texture_creator_preview.winfo_height())
        if path is None or not path.exists():
            self.texture_creator_preview_info_var.set("No output generated.")
            self.texture_creator_preview.create_text(
                canvas_width // 2,
                canvas_height // 2,
                text="Create or upload a texture to preview it here.",
                fill="#9aa4b5",
                anchor=tk.CENTER,
            )
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.texture_creator_preview_image = tk.PhotoImage(file=str(path))
            self.texture_creator_preview.create_image(
                canvas_width // 2,
                canvas_height // 2,
                image=self.texture_creator_preview_image,
                anchor=tk.CENTER,
            )
            return

        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        original_width, original_height = image.size
        max_width = max(1, canvas_width - 20)
        max_height = max(1, canvas_height - 20)
        scale = min(
            max_width / max(1, original_width),
            max_height / max(1, original_height),
            1,
        )
        display_size = (
            max(1, round(original_width * scale)),
            max(1, round(original_height * scale)),
        )
        if image.size != display_size:
            image = image.resize(display_size, Image.Resampling.LANCZOS)
        self.texture_creator_preview_image = ImageTk.PhotoImage(image)
        self.texture_creator_preview_info_var.set(
            f"{path.name} - {original_width} x {original_height}"
        )
        self.texture_creator_preview.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.texture_creator_preview_image,
            anchor=tk.CENTER,
        )

    def generate_jersey_preview(
        self,
        *,
        select_tab: bool = True,
        update_status: bool = True,
    ) -> None:
        try:
            template = self._current_generator_template()
            output_name = (
                "generated_shorts_color.png"
                if self.generator_garment_var.get() == "Shorts"
                else "generated_jersey_color.png"
            )
            output_path = (
                Path(tempfile.gettempdir())
                / "nba2k_jersey_modder"
                / "generated"
                / output_name
            )
            generate_jersey_texture(
                template,
                self._generator_inputs(),
                output_path,
            )
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("Generate failed", str(exc))
            return

        self.generated_texture_path = output_path
        self._show_generated_preview(output_path)
        self._schedule_texture_creator_auto_refresh()
        self._refresh_blender_preview_files_if_active()
        if update_status:
            self.generator_status.configure(text=f"Generated {output_path}.")
        if select_tab:
            self.tabs.select(self.generator_tab)

    def _schedule_generator_preview_refresh(self) -> None:
        if self.generator_preview_refresh_after_id is not None:
            return
        self.generator_preview_refresh_after_id = self.after(
            80,
            self._run_scheduled_generator_preview_refresh,
        )

    def _run_scheduled_generator_preview_refresh(self) -> None:
        self.generator_preview_refresh_after_id = None
        if self.generator_preview_refresh_running:
            self._schedule_generator_preview_refresh()
            return
        self.generator_preview_refresh_running = True
        try:
            self.generate_jersey_preview(select_tab=False, update_status=False)
        finally:
            self.generator_preview_refresh_running = False

    def _cancel_generator_preview_refresh(self) -> None:
        if self.generator_preview_refresh_after_id is None:
            return
        self.after_cancel(self.generator_preview_refresh_after_id)
        self.generator_preview_refresh_after_id = None

    def save_generated_texture_as(self) -> None:
        if self.generated_texture_path is None or not self.generated_texture_path.exists():
            messagebox.showinfo("Save Generated PNG", "Generate a preview first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Save Generated Jersey Texture",
            defaultextension=".png",
            filetypes=(("PNG files", "*.png"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            Path(selected).write_bytes(self.generated_texture_path.read_bytes())
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        self.generator_status.configure(text=f"Saved generated texture to {selected}.")

    def save_generated_dds_as(self) -> None:
        if self.generated_texture_path is None or not self.generated_texture_path.exists():
            messagebox.showinfo("Save DDS BC1", "Generate a preview first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Save Generated Jersey Texture as DDS BC1",
            defaultextension=".dds",
            filetypes=(("DDS files", "*.dds"), ("All files", "*.*")),
        )
        if not selected:
            return
        source = self.generated_texture_path
        target = Path(selected)
        self.generator_status.configure(text=f"Saving BC1 DDS texture to {selected}...")
        thread = threading.Thread(
            target=self._save_generated_dds_worker,
            args=(source, target),
            daemon=True,
        )
        thread.start()

    def _save_generated_dds_worker(self, source: Path, target: Path) -> None:
        try:
            save_bc1_dds(source, target)
        except Exception as exc:  # noqa: BLE001 - background GUI boundary.
            self.after(0, lambda: self._finish_generated_dds_save(target, exc))
            return
        self.after(0, lambda: self._finish_generated_dds_save(target, None))

    def _finish_generated_dds_save(self, target: Path, error: Exception | None) -> None:
        if error is not None:
            messagebox.showerror("DDS save failed", str(error))
            self.generator_status.configure(text="DDS save failed.")
            return
        self.generator_status.configure(text=f"Saved BC1 DDS texture to {target}.")

    def save_layered_psd_as(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save Layered Photoshop File",
            defaultextension=".psd",
            filetypes=(("Photoshop files", "*.psd"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            template = self._current_generator_template()
            generate_layered_jersey_psd(
                template,
                self._generator_inputs(),
                Path(selected),
            )
        except Exception as exc:  # noqa: BLE001 - GUI boundary.
            messagebox.showerror("PSD save failed", str(exc))
            return
        self.generator_status.configure(text=f"Saved layered PSD to {selected}.")

    def _generator_inputs(self) -> GeneratorInputs:
        return GeneratorInputs(
            front_color=self._generator_color_value("front_color"),
            back_color=self._generator_color_value("back_color"),
            left_panel_color=self._generator_color_value("left_panel_color"),
            right_panel_color=self._generator_color_value("right_panel_color"),
            collar_background_color=self._generator_color_value(
                "collar_background_color"
            ),
            left_arm_hole_trim_color=self._generator_color_value(
                "left_arm_hole_trim_color"
            ),
            right_arm_hole_trim_color=self._generator_color_value(
                "right_arm_hole_trim_color"
            ),
            collar_trim_color=self._generator_color_value("collar_trim_color"),
            left_panel_image=self.generator_paths["left_panel_image"],
            right_panel_image=self.generator_paths["right_panel_image"],
            front_wordmark_image=self.generator_paths["front_wordmark_image"],
            left_arm_hole_trim_image=self.generator_paths["left_arm_hole_trim_image"],
            right_arm_hole_trim_image=self.generator_paths["right_arm_hole_trim_image"],
            collar_trim_image=self.generator_paths["collar_trim_image"],
            front_wordmark_offset_x=self._front_wordmark_offset_x(),
            front_wordmark_offset_y=self._front_wordmark_offset_y(),
            front_wordmark_scale_percent=self._front_wordmark_scale_percent(),
            logo_placements=tuple(self.generator_logo_placements),
            fabric_overlay_image=self._fabric_overlay_path(),
            fabric_overlay_opacity=self._fabric_overlay_opacity(),
            fabric_overlay_blend_mode=self.fabric_overlay_blend_var.get(),
            dynamic_layer_order=self._active_dynamic_layer_order(),
            layer_background_cleanup=dict(self.web_editor_layer_cleanup),
            trim_placements=dict(self.generator_trim_placements),
            remove_white_background=self.generator_remove_white_var.get(),
            remove_black_background=self.generator_remove_black_var.get(),
            remove_outside_background_only=self.generator_outside_only_var.get(),
            background_tolerance=self._generator_background_tolerance(),
        )

    def _front_wordmark_offset_x(self) -> int:
        try:
            return self.front_wordmark_offset_x_var.get()
        except tk.TclError:
            return 0

    def _front_wordmark_offset_y(self) -> int:
        try:
            return self.front_wordmark_offset_y_var.get()
        except tk.TclError:
            return 0

    def _front_wordmark_scale_percent(self) -> int:
        try:
            value = self.front_wordmark_scale_var.get()
        except tk.TclError:
            return 100
        return max(1, min(500, value))

    def _fabric_overlay_path(self) -> Path | None:
        selected = self.fabric_overlay_var.get()
        if selected == "Custom upload":
            return self.custom_fabric_overlay_path
        return FABRIC_OVERLAY_PRESETS.get(selected)

    def _fabric_overlay_opacity(self) -> int:
        try:
            value = self.fabric_overlay_opacity_var.get()
        except tk.TclError:
            return 0
        return max(0, min(100, value))

    def _generator_color_value(self, key: str) -> str:
        color = self._normalize_hex_color(self.generator_color_vars[key].get())
        if color is None:
            raise ValueError(f"Enter a valid hex color for {key.replace('_', ' ')}.")
        self.generator_color_vars[key].set(color)
        return color

    def _normalize_hex_color(self, value: str) -> str | None:
        value = value.strip()
        if not value:
            return ""
        match = HEX_COLOR_RE.match(value)
        if match is None:
            return None
        hex_value = match.group(1).lower()
        if len(hex_value) == 3:
            hex_value = "".join(character * 2 for character in hex_value)
        return f"#{hex_value}"

    def _generator_background_tolerance(self) -> int:
        try:
            value = self.generator_tolerance_var.get()
        except tk.TclError:
            return 32
        return max(0, min(128, value))

    def _show_generated_preview(self, path: Path) -> None:
        try:
            from PIL import Image, ImageTk
        except ImportError as exc:
            messagebox.showerror("Preview failed", "Preview rendering requires Pillow.")
            raise RuntimeError("Preview rendering requires Pillow.") from exc

        self.generator_preview.update_idletasks()
        canvas_width = max(1, self.generator_preview.winfo_width())
        canvas_height = max(1, self.generator_preview.winfo_height())
        size = min(max(1, canvas_width - 20), max(1, canvas_height - 20))
        left = (canvas_width - size) // 2
        top = (canvas_height - size) // 2
        self.generator_preview_rect = (left, top, size, size)
        self.generator_preview_scale = size / 2048
        with Image.open(path) as opened:
            self.generated_preview_base_image = opened.convert("RGB").resize(
                (size, size),
                Image.Resampling.LANCZOS,
            )
        self.generated_preview_image = ImageTk.PhotoImage(self.generated_preview_base_image)
        self.generator_preview.delete("all")
        self.generator_preview_image_item = self.generator_preview.create_image(
            left + size // 2,
            top + size // 2,
            image=self.generated_preview_image,
            anchor=tk.CENTER,
        )
        self._draw_generator_uv_overlay()
        self._draw_generator_image_boxes()

    def _redraw_generator_preview_overlays(self) -> None:
        if hasattr(self, "generator_preview"):
            self._draw_generator_uv_overlay()
            self._draw_generator_image_boxes()
        self._refresh_blender_preview_files_if_active()

    def _draw_generator_uv_overlay(self) -> None:
        self.generator_preview.delete("generator_uv_overlay")
        if (
            self.generator_preview_rect is None
            or self.generated_preview_base_image is None
            or self.generator_preview_image_item is None
        ):
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return
        display = self.generated_preview_base_image.copy()
        self.generator_uv_overlay_image = None
        if not self.generator_uv_overlay_var.get():
            self.generated_preview_image = ImageTk.PhotoImage(display)
            self.generator_preview.itemconfigure(
                self.generator_preview_image_item,
                image=self.generated_preview_image,
            )
            return
        try:
            opacity = int(float(self.generator_uv_overlay_opacity_var.get()))
        except tk.TclError:
            opacity = 45
        opacity = max(0, min(100, opacity))
        if opacity <= 0:
            self.generated_preview_image = ImageTk.PhotoImage(display)
            self.generator_preview.itemconfigure(
                self.generator_preview_image_item,
                image=self.generated_preview_image,
            )
            return
        uv_path = self._current_generator_uv_map_path()
        if not uv_path.exists():
            self.generated_preview_image = ImageTk.PhotoImage(display)
            self.generator_preview.itemconfigure(
                self.generator_preview_image_item,
                image=self.generated_preview_image,
            )
            return
        try:
            left, top, width, height = self.generator_preview_rect
            cache_key = (str(uv_path), uv_path.stat().st_mtime_ns, width, height)
            if (
                self.generator_uv_overlay_cache is None
                or self.generator_uv_overlay_cache.get("key") != cache_key
            ):
                with Image.open(uv_path) as opened:
                    source = opened.convert("RGBA")
                if source.size == (width, height):
                    scaled = source
                else:
                    scaled = source.resize((width, height), Image.Resampling.LANCZOS)
                self.generator_uv_overlay_cache = {
                    "key": cache_key,
                    "alpha": scaled.getchannel("A"),
                }
            base_alpha = self.generator_uv_overlay_cache["alpha"]
        except Exception:
            return
        alpha = base_alpha.point(lambda value: round(value * opacity / 100))
        display = Image.composite(
            Image.new("RGB", display.size, (0, 0, 0)),
            display,
            alpha,
        )
        self.generated_preview_image = ImageTk.PhotoImage(display)
        self.generator_preview.itemconfigure(
            self.generator_preview_image_item,
            image=self.generated_preview_image,
        )

    def _draw_generator_image_boxes(self) -> None:
        self.generator_preview.delete("generator_overlay")
        self.generator_image_rects.clear()
        if self.generator_preview_rect is None:
            return
        left, top, _width, _height = self.generator_preview_rect
        try:
            template = self._current_generator_template()
            placements = image_placement_rects(template, self._generator_inputs())
        except Exception:
            return
        active_keys = {placement.key for placement in placements}
        if self._generator_number_preview_available():
            active_keys.add("preview_number")
        if self.generator_selected_image_key not in active_keys:
            self.generator_selected_image_key = None

        for placement in placements:
            self.generator_image_rects[placement.key] = (
                placement.x,
                placement.y,
                placement.width,
                placement.height,
            )
            if placement.key != self.generator_selected_image_key:
                continue
            x1 = left + placement.x * self.generator_preview_scale
            y1 = top + placement.y * self.generator_preview_scale
            x2 = left + (placement.x + placement.width) * self.generator_preview_scale
            y2 = top + (placement.y + placement.height) * self.generator_preview_scale
            self.generator_preview.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline="#ffcc33",
                width=2,
                tags=("generator_overlay",),
            )
            self.generator_preview.create_rectangle(
                x2 - 7,
                y2 - 7,
                x2 + 7,
                y2 + 7,
                fill="#ffcc33",
                outline="#20242b",
                tags=("generator_overlay",),
            )
            self.generator_preview.create_text(
                x1 + 4,
                y1 - 10,
                text=placement.label,
                anchor=tk.W,
                fill="#ffcc33",
                tags=("generator_overlay",),
            )
        self._draw_generator_number_preview(left, top)

    def _generator_number_preview_available(self) -> bool:
        if not self.generator_number_preview_enabled_var.get():
            return False
        return bool(self._generator_number_preview_text())

    def _generator_number_preview_text(self) -> str:
        return "".join(
            character
            for character in self.generator_number_preview_text_var.get()
            if character.isdigit()
        )

    def _generator_number_preview_scale(self) -> int:
        try:
            value = self.generator_number_preview_scale_var.get()
        except tk.TclError:
            value = 100
        value = max(5, min(500, value))
        self.generator_number_preview_scale_var.set(value)
        return value

    def _draw_generator_number_preview(self, preview_left: int, preview_top: int) -> None:
        if not self._generator_number_preview_available():
            self.generator_number_preview_image = None
            return
        try:
            from PIL import Image, ImageTk

            image = self._build_generator_number_preview_image()
        except Exception:
            self.generator_number_preview_image = None
            return
        if image is None:
            self.generator_number_preview_image = None
            return

        scale_percent = self._generator_number_preview_scale()
        texture_width = max(1, round(image.width * scale_percent / 100))
        texture_height = max(1, round(image.height * scale_percent / 100))
        try:
            x = max(0, min(2048, int(self.generator_number_preview_x_var.get())))
            y = max(0, min(2048, int(self.generator_number_preview_y_var.get())))
        except tk.TclError:
            x, y = 1160, 780
        self.generator_number_preview_x_var.set(x)
        self.generator_number_preview_y_var.set(y)
        self.generator_image_rects["preview_number"] = (
            x,
            y,
            texture_width,
            texture_height,
        )

        canvas_width = max(1, round(texture_width * self.generator_preview_scale))
        canvas_height = max(1, round(texture_height * self.generator_preview_scale))
        display = image.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        self.generator_number_preview_image = ImageTk.PhotoImage(display)
        x1 = preview_left + x * self.generator_preview_scale
        y1 = preview_top + y * self.generator_preview_scale
        x2 = x1 + canvas_width
        y2 = y1 + canvas_height
        self.generator_preview.create_image(
            x1,
            y1,
            image=self.generator_number_preview_image,
            anchor=tk.NW,
            tags=("generator_overlay",),
        )
        if self.generator_selected_image_key != "preview_number":
            return
        self.generator_preview.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline="#ffcc33",
            width=2,
            tags=("generator_overlay",),
        )
        self.generator_preview.create_rectangle(
            x2 - 7,
            y2 - 7,
            x2 + 7,
            y2 + 7,
            fill="#ffcc33",
            outline="#20242b",
            tags=("generator_overlay",),
        )
        self.generator_preview.create_text(
            x1 + 4,
            y1 - 10,
            text="Preview number",
            anchor=tk.W,
            fill="#ffcc33",
            tags=("generator_overlay",),
        )

    def _build_generator_number_preview_image(self):
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Preview number requires Pillow.") from exc

        digits = []
        for character in self._generator_number_preview_text():
            path = self.number_creator_digit_paths.get(character)
            if path is None or not path.exists():
                return None
            with Image.open(path) as opened:
                digit = opened.convert("RGBA")
            bbox = digit.getchannel("A").getbbox()
            if bbox is not None:
                left, top, right, bottom = bbox
                padding = max(2, round(digit.height * 0.03))
                digit = digit.crop(
                    (
                        max(0, left - padding),
                        max(0, top - padding),
                        min(digit.width, right + padding),
                        min(digit.height, bottom + padding),
                    )
                )
            digits.append(digit)
        if not digits:
            return None
        gap = max(2, round(max(digit.height for digit in digits) * 0.04))
        width = sum(digit.width for digit in digits) + gap * (len(digits) - 1)
        height = max(digit.height for digit in digits)
        number = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        x = 0
        for digit in digits:
            y = (height - digit.height) // 2
            number.alpha_composite(digit, (x, y))
            x += digit.width + gap
        return number

    def reset_generator_number_preview(self) -> None:
        self.generator_number_preview_enabled_var.set(True)
        self.generator_number_preview_text_var.set("15")
        self.generator_number_preview_x_var.set(1160)
        self.generator_number_preview_y_var.set(780)
        self.generator_number_preview_scale_var.set(100)
        self._redraw_generator_preview_overlays()

    def _generator_preview_press(self, event: tk.Event) -> None:
        hit = self._hit_generator_image(event.x, event.y)
        if hit is None:
            self.generator_drag_state = None
            self.generator_selected_image_key = None
            self._draw_generator_image_boxes()
            return
        key, mode = hit
        self.generator_selected_image_key = key
        self._draw_generator_image_boxes()
        texture_x, texture_y = self._preview_to_texture(event.x, event.y)
        rect = self.generator_image_rects[key]
        self.generator_drag_state = {
            "key": key,
            "mode": mode,
            "start": (texture_x, texture_y),
            "rect": rect,
            "front_offset": (
                self._front_wordmark_offset_x(),
                self._front_wordmark_offset_y(),
            ),
            "front_scale": self._front_wordmark_scale_percent(),
            "logos": tuple(self.generator_logo_placements),
            "trim_placements": dict(self.generator_trim_placements),
            "placements": {
                placement.key: placement
                for placement in image_placement_rects(
                    self._current_generator_template(),
                    self._generator_inputs(),
                )
            },
            "preview_number": (
                self.generator_number_preview_x_var.get(),
                self.generator_number_preview_y_var.get(),
                self._generator_number_preview_scale(),
            ),
        }

    def _generator_preview_drag(self, event: tk.Event) -> None:
        if not self.generator_drag_state:
            return
        texture_x, texture_y = self._preview_to_texture(event.x, event.y)
        start_x, start_y = self.generator_drag_state["start"]
        delta_x = round(texture_x - start_x)
        delta_y = round(texture_y - start_y)
        key = self.generator_drag_state["key"]
        mode = self.generator_drag_state["mode"]

        if key == "front_wordmark":
            self._drag_front_wordmark(mode, delta_x, delta_y, texture_x)
        elif key.startswith("logo:"):
            self._drag_logo(key, mode, delta_x, delta_y, texture_x, texture_y)
        elif key in SIDE_PANEL_GENERATOR_KEYS:
            self._drag_side_panel(key, mode, delta_x, delta_y, texture_x, texture_y)
        elif key == "preview_number":
            self._drag_generator_number_preview(mode, delta_x, delta_y, texture_x)
            self._draw_generator_image_boxes()
            return
        self._schedule_generator_preview_refresh()

    def _generator_preview_release(self, _event: tk.Event) -> None:
        if self.generator_drag_state:
            if self.generator_drag_state["key"] == "preview_number":
                self._draw_generator_image_boxes()
                self._refresh_blender_preview_files_if_active()
            else:
                self._cancel_generator_preview_refresh()
                self.generate_jersey_preview(select_tab=False, update_status=False)
        self.generator_drag_state = None

    def _drag_front_wordmark(
        self,
        mode: str,
        delta_x: int,
        delta_y: int,
        texture_x: float,
        texture_y: float,
    ) -> None:
        if self.generator_drag_state is None:
            return
        if mode == "move":
            start_x, start_y = self.generator_drag_state["front_offset"]
            self.front_wordmark_offset_x_var.set(start_x + delta_x)
            self.front_wordmark_offset_y_var.set(start_y + delta_y)
            return

        rect_x, _rect_y, rect_width, _rect_height = self.generator_drag_state["rect"]
        new_width = max(1, texture_x - rect_x)
        start_scale = self.generator_drag_state["front_scale"]
        self.front_wordmark_scale_var.set(
            max(1, min(500, round(start_scale * new_width / max(1, rect_width))))
        )

    def _drag_generator_number_preview(
        self,
        mode: str,
        delta_x: int,
        delta_y: int,
        texture_x: float,
    ) -> None:
        if self.generator_drag_state is None:
            return
        start_x, start_y, start_scale = self.generator_drag_state["preview_number"]
        if mode == "move":
            self.generator_number_preview_x_var.set(max(0, min(2048, start_x + delta_x)))
            self.generator_number_preview_y_var.set(max(0, min(2048, start_y + delta_y)))
            return
        rect_x, _rect_y, rect_width, _rect_height = self.generator_drag_state["rect"]
        new_width = max(1, texture_x - rect_x)
        self.generator_number_preview_scale_var.set(
            max(5, min(500, round(start_scale * new_width / max(1, rect_width))))
        )

    def _drag_logo(
        self,
        key: str,
        mode: str,
        delta_x: int,
        delta_y: int,
        texture_x: float,
        texture_y: float,
    ) -> None:
        if self.generator_drag_state is None:
            return
        index = int(key.split(":")[1])
        original_logos: tuple[LogoPlacement, ...] = self.generator_drag_state["logos"]
        if not (0 <= index < len(original_logos)):
            return
        logo = original_logos[index]
        if mode == "move":
            if logo.stretch_x:
                updated = replace(
                    logo,
                    offset_x=0,
                    offset_y=logo.offset_y + delta_y,
                )
                self.generator_logo_placements[index] = updated
                self._refresh_generator_logo_list()
                return
            updated = replace(
                logo,
                offset_x=logo.offset_x + delta_x,
                offset_y=logo.offset_y + delta_y,
            )
        else:
            rect_x, rect_y, rect_width, rect_height = self.generator_drag_state["rect"]
            if logo.stretch_x:
                new_height = max(1, texture_y - rect_y)
                updated = replace(
                    logo,
                    offset_x=0,
                    scale_percent=max(
                        1,
                        min(
                            500,
                            round(logo.scale_percent * new_height / max(1, rect_height)),
                        ),
                    ),
                )
                self.generator_logo_placements[index] = updated
                self._refresh_generator_logo_list()
                return
            new_width = max(1, texture_x - rect_x)
            updated = replace(
                logo,
                scale_percent=max(
                    1,
                    min(500, round(logo.scale_percent * new_width / max(1, rect_width))),
                ),
            )
        self.generator_logo_placements[index] = updated
        self._refresh_generator_logo_list()

    def _drag_side_panel(
        self,
        key: str,
        mode: str,
        delta_x: int,
        delta_y: int,
        texture_x: float,
        texture_y: float,
    ) -> None:
        if self.generator_drag_state is None:
            return
        original_placements: dict[str, TrimPlacementSettings] = (
            self.generator_drag_state["trim_placements"]
        )
        panel = original_placements.get(key, TrimPlacementSettings())
        if mode == "move":
            self.generator_trim_placements[key] = replace(
                panel,
                offset_x=panel.offset_x + delta_x,
                offset_y=panel.offset_y + delta_y,
            )
            return

        rect_x, rect_y, rect_width, rect_height = self.generator_drag_state["rect"]
        new_width = max(1, texture_x - rect_x)
        new_height = max(1, texture_y - rect_y)
        width_scale = _scale_dimension_percent(
            panel.scale_width_percent,
            panel.scale_percent,
            new_width,
            rect_width,
        )
        height_scale = _scale_dimension_percent(
            panel.scale_height_percent,
            panel.scale_percent,
            new_height,
            rect_height,
        )
        offset_x = panel.offset_x
        offset_y = panel.offset_y
        placement = self.generator_drag_state["placements"].get(key)
        if placement is not None and placement.clip_x is not None:
            zone_x = placement.clip_x
            zone_y = placement.clip_y or 0
            zone_width = placement.clip_width or 1
            zone_height = placement.clip_height or 1
            offset_x = round(rect_x - (zone_x + (zone_width - new_width) / 2))
            offset_y = round(rect_y - (zone_y + (zone_height - new_height) / 2))
        self.generator_trim_placements[key] = replace(
            panel,
            offset_x=offset_x,
            offset_y=offset_y,
            scale_percent=width_scale,
            scale_width_percent=width_scale,
            scale_height_percent=height_scale,
        )

    def _hit_generator_image(self, canvas_x: int, canvas_y: int) -> tuple[str, str] | None:
        if self.generator_preview_rect is None:
            return None
        left, top, _width, _height = self.generator_preview_rect
        for key, (x, y, width, height) in reversed(list(self.generator_image_rects.items())):
            x1 = left + x * self.generator_preview_scale
            y1 = top + y * self.generator_preview_scale
            x2 = left + (x + width) * self.generator_preview_scale
            y2 = top + (y + height) * self.generator_preview_scale
            if x2 - 10 <= canvas_x <= x2 + 10 and y2 - 10 <= canvas_y <= y2 + 10:
                return key, "resize"
            if x1 <= canvas_x <= x2 and y1 <= canvas_y <= y2:
                return key, "move"
        return None

    def _preview_to_texture(self, canvas_x: int, canvas_y: int) -> tuple[float, float]:
        if self.generator_preview_rect is None:
            return 0, 0
        left, top, _width, _height = self.generator_preview_rect
        return (
            (canvas_x - left) / self.generator_preview_scale,
            (canvas_y - top) / self.generator_preview_scale,
        )

    def load_template_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Load Jersey Template Image",
            filetypes=(
                ("Image files", "*.png *.gif *.ppm *.pgm"),
                ("All files", "*.*"),
            ),
        )
        if not selected:
            return
        try:
            image_width, image_height = read_image_size(Path(selected))
        except (RuntimeError, OSError) as exc:
            messagebox.showerror(
                "Template image failed",
                f"Could not load this image.\n\n{exc}\n\nExport PNG from Photoshop for best results.",
            )
            return

        self.template_image_path = Path(selected)
        self.template_original_size = (image_width, image_height)
        self.template_zoom = 1.0
        self._render_template_image(fit=True)
        self.template_status.configure(
            text=f"Loaded {Path(selected).name} ({image_width} x {image_height}). Drag on the image to create zones."
        )
        self.tabs.select(self.template_tab)

    def load_master_template(self) -> None:
        image_path, zones_path = self._current_template_master_paths()
        if not image_path.exists() or not zones_path.exists():
            messagebox.showerror(
                "Master Template Missing",
                "The built-in master template files were not found.",
            )
            return

        try:
            image_width, image_height = read_image_size(image_path)
            template = load_template(zones_path)
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Master Template failed", str(exc))
            return

        self.template_image_path = image_path
        self.template_original_size = (image_width, image_height)
        self.template_zones = list(template.zones)
        self.template_zoom = 1.0
        self._render_template_image(fit=True)
        self.template_status.configure(
            text=f"Loaded {self._current_template_master_label()} ({image_width} x {image_height})."
        )
        self.tabs.select(self.template_tab)

    def _current_template_master_paths(self) -> tuple[Path, Path]:
        if self.template_garment_var.get() == "Shorts":
            return SHORTS_TEMPLATE_OPTIONS.get(
                self.template_shorts_template_var.get(),
                SHORTS_TEMPLATE_OPTIONS["Retro shorts"],
            )
        return JERSEY_TEMPLATE_OPTIONS.get(
            self.template_jersey_template_var.get(),
            JERSEY_TEMPLATE_OPTIONS["Jersey color"],
        )

    def _current_template_master_label(self) -> str:
        if self.template_garment_var.get() == "Shorts":
            return self.template_shorts_template_var.get()
        return (
            f"{self.template_jersey_cut_var.get()} / "
            f"{self.template_jersey_template_var.get()}"
        )

    def _on_template_master_choice_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_template_master_controls()
        self.load_master_template()

    def _sync_template_master_controls(self) -> None:
        is_shorts = self.template_garment_var.get() == "Shorts"
        if is_shorts:
            if self.template_jersey_cut_box.winfo_manager():
                self.template_jersey_cut_box.pack_forget()
            if not self.template_shorts_template_box.winfo_manager():
                self.template_shorts_template_box.pack(side=tk.LEFT)
            self.template_jersey_template_box.configure(state="disabled")
        else:
            if self.template_shorts_template_box.winfo_manager():
                self.template_shorts_template_box.pack_forget()
            if not self.template_jersey_cut_box.winfo_manager():
                self.template_jersey_cut_box.pack(side=tk.LEFT)
            self.template_jersey_template_box.configure(state="readonly")

    def choose_zone_color(self) -> None:
        color = colorchooser.askcolor(color=self.zone_color_var.get())[1]
        if not color:
            return
        normalized = self._normalize_hex_color(color)
        if normalized is None:
            return
        self.zone_color_var.set(normalized)
        self.zone_color_swatch.configure(background=normalized)

    def create_template_zone_from_hex(self) -> None:
        if self.template_image_path is None:
            messagebox.showinfo("Template Editor", "Load a template image first.")
            return
        color = self._normalize_hex_color(self.zone_color_var.get())
        if color is None or not color:
            messagebox.showinfo("Template Editor", "Enter a valid zone hex color.")
            return
        try:
            bbox = find_hex_color_zone_bbox(self.template_image_path, color, tolerance=4)
        except (RuntimeError, ValueError) as exc:
            messagebox.showerror("Create Zone From Hex failed", str(exc))
            return
        if bbox is None:
            messagebox.showinfo(
                "Template Editor",
                f"No pixels matching {color} were found in the template.",
            )
            return

        x, y, width, height = bbox
        zone = TemplateZone(
            name=self.zone_name_var.get().strip() or f"zone_{len(self.template_zones) + 1}",
            zone_type=self.zone_type_var.get(),
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            layer=template_zone_layer(self.zone_type_var.get()),
        )
        self.template_zones.append(zone)
        index = len(self.template_zones) - 1
        self.zone_color_var.set(color)
        self.zone_color_swatch.configure(background=color)
        self._refresh_template_zone_list(selected_index=index)
        self._load_template_zone_into_editor(index)
        self._redraw_template_zones(refresh_list=False)
        self.template_status.configure(
            text=f"Created zone {zone.name} from {color}: X {x}, Y {y}, W {width}, H {height}."
        )

    def _on_template_zone_select(self, _event: tk.Event | None = None) -> None:
        index = self._selected_template_zone_index()
        if index is None:
            return
        self._load_template_zone_into_editor(index)
        self._redraw_template_zones(refresh_list=False)

    def _open_template_zone_popup_from_click(self, event: tk.Event) -> None:
        item_id = self.zone_list.identify_row(event.y)
        if item_id:
            self.zone_list.selection_set(item_id)
            self.zone_list.focus(item_id)
        index = self._selected_template_zone_index()
        if index is None:
            return
        self._open_template_zone_popup(index)

    def _open_template_zone_popup(self, index: int) -> None:
        if not (0 <= index < len(self.template_zones)):
            return
        zone = self.template_zones[index]
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Zone: {zone.name}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        name_var = tk.StringVar(value=zone.name)
        type_var = tk.StringVar(value=zone.zone_type)
        color_var = tk.StringVar(value=zone.color)
        x_var = tk.IntVar(value=zone.x)
        y_var = tk.IntVar(value=zone.y)
        width_var = tk.IntVar(value=zone.width)
        height_var = tk.IntVar(value=zone.height)
        layer_var = tk.IntVar(value=zone.layer)

        body = ttk.Frame(dialog, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        ttk.Label(body, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=name_var, width=34).grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(2, 8)
        )

        ttk.Label(body, text="Type").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            body,
            textvariable=type_var,
            values=(
                "base",
                "wordmark",
                "number",
                "name",
                "logo",
                "patch",
                "stripe",
                "trim",
                "pattern",
                "mask",
            ),
            state="readonly",
            width=18,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))

        ttk.Label(body, text="Hex").grid(row=2, column=2, sticky="w", padx=(8, 0))
        color_row = ttk.Frame(body)
        color_row.grid(row=3, column=2, columnspan=2, sticky="ew", padx=(8, 0), pady=(2, 8))
        color_swatch = tk.Label(
            color_row,
            width=4,
            background=zone.color,
            relief=tk.SOLID,
            borderwidth=1,
        )
        color_swatch.pack(side=tk.RIGHT)
        ttk.Entry(color_row, textvariable=color_var, width=11).pack(side=tk.LEFT)

        def choose_color() -> None:
            chosen = colorchooser.askcolor(color=color_var.get(), parent=dialog)[1]
            if not chosen:
                return
            normalized = self._normalize_hex_color(chosen)
            if normalized is None:
                return
            color_var.set(normalized)
            color_swatch.configure(background=normalized)

        ttk.Button(color_row, text="Pick", command=choose_color).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )

        for column, (label, variable) in enumerate(
            (
                ("X", x_var),
                ("Y", y_var),
                ("W", width_var),
                ("H", height_var),
                ("Layer", layer_var),
            )
        ):
            ttk.Label(body, text=label).grid(row=4, column=column, sticky="w")
            tk.Spinbox(
                body,
                from_=-9999 if label in {"X", "Y"} else 1,
                to=9999,
                increment=1,
                width=7,
                textvariable=variable,
            ).grid(row=5, column=column, sticky="ew", padx=(0, 6), pady=(2, 8))

        error_var = tk.StringVar(value="")
        ttk.Label(body, textvariable=error_var, style="Muted.TLabel").grid(
            row=6,
            column=0,
            columnspan=5,
            sticky="w",
            pady=(0, 8),
        )

        def apply_changes() -> None:
            color = self._normalize_hex_color(color_var.get())
            if color is None or not color:
                error_var.set("Enter a valid hex color.")
                return
            try:
                x = int(x_var.get())
                y = int(y_var.get())
                width = max(1, int(width_var.get()))
                height = max(1, int(height_var.get()))
                layer = int(layer_var.get())
            except (tk.TclError, ValueError):
                error_var.set("Enter valid numbers for X, Y, W, H, and Layer.")
                return

            if self.template_image_path is not None:
                try:
                    source_width, source_height = self._template_source_size()
                except RuntimeError:
                    source_width = source_height = None
                if source_width is not None and source_height is not None:
                    x = max(0, min(source_width - 1, x))
                    y = max(0, min(source_height - 1, y))
                    width = max(1, min(source_width - x, width))
                    height = max(1, min(source_height - y, height))

            self.template_zones[index] = replace(
                self.template_zones[index],
                name=name_var.get().strip() or self.template_zones[index].name,
                zone_type=type_var.get(),
                x=x,
                y=y,
                width=width,
                height=height,
                color=color,
                layer=layer,
            )
            self._refresh_template_zone_list(selected_index=index)
            self._load_template_zone_into_editor(index)
            self._redraw_template_zones(refresh_list=False)
            if self._is_editing_master_template():
                try:
                    self._write_master_template_zones()
                except OSError as exc:
                    messagebox.showerror("Save Master failed", str(exc), parent=dialog)
                    return
            self.template_status.configure(
                text=f"Updated zone {self.template_zones[index].name}."
            )
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=5, sticky="e")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Apply", command=apply_changes).pack(
            side=tk.RIGHT,
            padx=(0, 8),
        )
        dialog.bind("<Return>", lambda _event: apply_changes())
        dialog.wait_window()

    def _selected_template_zone_index(self) -> int | None:
        selected = self.zone_list.selection()
        if not selected:
            return None
        try:
            index = int(selected[0].split(":", 1)[1])
        except (IndexError, ValueError):
            return None
        if 0 <= index < len(self.template_zones):
            return index
        return None

    def _load_template_zone_into_editor(self, index: int) -> None:
        zone = self.template_zones[index]
        self.zone_name_var.set(zone.name)
        self.zone_type_var.set(zone.zone_type)
        self.zone_color_var.set(zone.color)
        self.zone_color_swatch.configure(background=zone.color)
        self.zone_x_var.set(zone.x)
        self.zone_y_var.set(zone.y)
        self.zone_width_var.set(zone.width)
        self.zone_height_var.set(zone.height)
        self.zone_layer_var.set(zone.layer)

    def _commit_selected_template_zone_edits(self) -> int | None:
        index = self._selected_template_zone_index()
        if index is None:
            return None
        color = self._normalize_hex_color(self.zone_color_var.get())
        if color is None or not color:
            raise ValueError("Enter a valid zone color.")
        try:
            x = int(self.zone_x_var.get())
            y = int(self.zone_y_var.get())
            width = max(1, int(self.zone_width_var.get()))
            height = max(1, int(self.zone_height_var.get()))
            layer = int(self.zone_layer_var.get())
        except tk.TclError:
            raise ValueError("Enter valid numbers for X, Y, W, H, and Layer.")

        if self.template_image_path is not None:
            try:
                source_width, source_height = self._template_source_size()
            except RuntimeError:
                source_width = source_height = None
            if source_width is not None and source_height is not None:
                x = max(0, min(source_width - 1, x))
                y = max(0, min(source_height - 1, y))
                width = max(1, min(source_width - x, width))
                height = max(1, min(source_height - y, height))

        self.zone_color_var.set(color)
        self.zone_color_swatch.configure(background=color)
        self.template_zones[index] = replace(
            self.template_zones[index],
            name=self.zone_name_var.get().strip() or self.template_zones[index].name,
            zone_type=self.zone_type_var.get(),
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            layer=layer,
        )
        return index

    def apply_selected_template_zone_edits(self) -> None:
        try:
            index = self._commit_selected_template_zone_edits()
        except ValueError as exc:
            messagebox.showinfo("Template Editor", str(exc))
            return
        if index is None:
            messagebox.showinfo("Template Editor", "Select a zone first.")
            return
        self._refresh_template_zone_list(selected_index=index)
        item_id = f"zone:{index}"
        self.zone_list.selection_set(item_id)
        self.zone_list.focus(item_id)
        self.zone_list.see(item_id)
        self._load_template_zone_into_editor(index)
        self._redraw_template_zones(refresh_list=False)
        if self._is_editing_master_template():
            try:
                self._write_master_template_zones()
            except OSError as exc:
                messagebox.showerror("Save Master failed", str(exc))
                return
            self.template_status.configure(
                text=f"Updated and saved master zone {self.template_zones[index].name}."
            )
        else:
            self.template_status.configure(text=f"Updated zone {self.template_zones[index].name}.")

    def save_template_zones(self) -> None:
        if self.template_image_path is None:
            messagebox.showinfo("Save Zones", "Load a template image first.")
            return
        try:
            committed_index = self._commit_selected_template_zone_edits()
        except ValueError as exc:
            messagebox.showinfo("Template Editor", str(exc))
            return
        if committed_index is not None:
            self._refresh_template_zone_list(selected_index=committed_index)
            self._load_template_zone_into_editor(committed_index)
            self._redraw_template_zones(refresh_list=False)
        selected = filedialog.asksaveasfilename(
            title="Save Jersey Template Zones",
            defaultextension=".json",
            filetypes=(("Template JSON", "*.json"), ("All files", "*.*")),
        )
        if not selected:
            return
        template = JerseyTemplate(
            image_path=str(self.template_image_path),
            zones=tuple(self.template_zones),
        )
        try:
            save_template(Path(selected), template)
        except OSError as exc:
            messagebox.showerror("Save Zones failed", str(exc))
            return
        self.template_status.configure(text=f"Saved zones to {selected}.")

    def save_master_template_zones(self) -> None:
        if not self.template_zones:
            messagebox.showinfo("Save Master", "No template zones are loaded.")
            return
        if self.template_image_path is None:
            messagebox.showinfo("Save Master", "Load the master template first.")
            return
        try:
            committed_index = self._commit_selected_template_zone_edits()
        except ValueError as exc:
            messagebox.showinfo("Template Editor", str(exc))
            return
        if committed_index is not None:
            self._refresh_template_zone_list(selected_index=committed_index)
            self._load_template_zone_into_editor(committed_index)
            self._redraw_template_zones(refresh_list=False)
        try:
            self._write_master_template_zones()
        except OSError as exc:
            messagebox.showerror("Save Master failed", str(exc))
            return
        self.template_status.configure(
            text=f"Saved {len(self.template_zones)} zones to {self._current_template_master_label()}."
        )

    def save_template_uv_map(self) -> None:
        if self.template_garment_var.get() == "Shorts":
            messagebox.showinfo("Save UV Map", "UV maps are only set up for jerseys right now.")
            return
        source_path = self.template_image_path
        if source_path is None:
            source_path, _zones_path = JERSEY_TEMPLATE_OPTIONS["Jersey color"]
        if self.template_jersey_template_var.get() == "Jersey UV":
            source_path = JERSEY_CUT_IMAGE_OPTIONS.get(
                self.template_jersey_cut_var.get(),
                MASTER_TEMPLATE_IMAGE,
            )
        output_path = JERSEY_CUT_UV_OPTIONS.get(
            self.template_jersey_cut_var.get(),
            JERSEY_UV_TEMPLATE_IMAGE,
        )
        if not source_path.exists():
            messagebox.showinfo("Save UV Map", "Load a template image first.")
            return
        try:
            create_uv_overlay_from_template(source_path, output_path)
            image_width, image_height = read_image_size(output_path)
        except (RuntimeError, OSError, tk.TclError) as exc:
            messagebox.showerror("Save UV Map failed", str(exc))
            return
        self.template_jersey_template_var.set("Jersey UV")
        self.template_image_path = output_path
        self.template_original_size = (image_width, image_height)
        self.template_zoom = 1.0
        try:
            template = load_template(JERSEY_CUT_TEMPLATE_OPTIONS.get(
                self.template_jersey_cut_var.get(),
                MASTER_TEMPLATE_ZONES,
            ))
            self.template_zones = list(template.zones)
        except (OSError, ValueError, TypeError):
            pass
        self._sync_template_master_controls()
        self._render_template_image(fit=True)
        self.template_status.configure(text=f"Saved UV map to {output_path.name}.")

    def _is_editing_master_template(self) -> bool:
        image_path, _zones_path = self._current_template_master_paths()
        return (
            self.template_image_path is not None
            and self.template_image_path.resolve() == image_path.resolve()
        )

    def _write_master_template_zones(self) -> None:
        image_path, zones_path = self._current_template_master_paths()
        template = JerseyTemplate(
            image_path=str(image_path),
            zones=tuple(self.template_zones),
        )
        save_template(zones_path, template)

    def load_template_zones(self) -> None:
        selected = filedialog.askopenfilename(
            title="Load Jersey Template Zones",
            filetypes=(("Template JSON", "*.json"), ("All files", "*.*")),
        )
        if not selected:
            return
        try:
            template = load_template(Path(selected))
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Load Zones failed", str(exc))
            return

        self.template_zones = list(template.zones)
        if template.image_path and Path(template.image_path).exists():
            try:
                image_width, image_height = read_image_size(Path(template.image_path))
            except (RuntimeError, OSError):
                image_width = image_height = None
            if image_width is not None and image_height is not None:
                self.template_image_path = Path(template.image_path)
                self.template_original_size = (image_width, image_height)
                self.template_zoom = 1.0
                self._render_template_image(fit=True)
            else:
                self._redraw_template_zones()
        else:
            self._redraw_template_zones()
        self._refresh_template_zone_list()
        self.template_status.configure(
            text=f"Loaded {len(self.template_zones)} zones from {selected}."
        )
        self.tabs.select(self.template_tab)

    def delete_selected_template_zone(self) -> None:
        selected = self.zone_list.selection()
        if not selected:
            return
        indexes = sorted((int(item.split(":", 1)[1]) for item in selected), reverse=True)
        for index in indexes:
            if 0 <= index < len(self.template_zones):
                del self.template_zones[index]
        self._redraw_template_zones()
        self._refresh_template_zone_list()

    def fit_template_to_view(self) -> None:
        self._render_template_image(fit=True)

    def template_zoom_actual(self) -> None:
        self.template_zoom = 1.0
        self._render_template_image()

    def adjust_template_zoom(self, factor: float) -> None:
        self.template_zoom = max(0.1, min(4.0, self.template_zoom * factor))
        self._render_template_image()

    def _template_canvas_configured(self, _event: tk.Event) -> None:
        if self.template_image is None and self.template_image_path is not None:
            self._render_template_image(fit=True)

    def _render_template_image(self, fit: bool = False) -> None:
        if self.template_image_path is None:
            return
        try:
            original_width, original_height = self._template_source_size()
        except RuntimeError as exc:
            messagebox.showerror("Template render failed", str(exc))
            return

        if fit:
            canvas_width = max(1, self.template_canvas.winfo_width() - 24)
            canvas_height = max(1, self.template_canvas.winfo_height() - 24)
            if canvas_width <= 1 or canvas_height <= 1:
                self.update_idletasks()
                canvas_width = max(1, self.template_canvas.winfo_width() - 24)
                canvas_height = max(1, self.template_canvas.winfo_height() - 24)
            self.template_zoom = min(
                1.0,
                canvas_width / original_width,
                canvas_height / original_height,
            )

        render_width = max(1, int(original_width * self.template_zoom))
        render_height = max(1, int(original_height * self.template_zoom))
        self.template_image = load_scaled_photo_image(
            self.template_image_path,
            render_width,
            render_height,
        )

        self.template_canvas.delete("all")
        self.template_canvas.create_image(
            0,
            0,
            image=self.template_image,
            anchor=tk.NW,
            tags=("image",),
        )
        self.template_canvas.configure(scrollregion=(0, 0, render_width, render_height))
        self._redraw_template_zones()
        self.template_status.configure(
            text=f"Template view: {int(self.template_zoom * 100)}% | saved zones use original {original_width} x {original_height} coordinates."
        )

    def _template_source_size(self) -> tuple[int, int]:
        if self.template_original_size:
            return self.template_original_size
        if self.template_image_path is None:
            raise RuntimeError("No template image loaded.")
        self.template_original_size = read_image_size(self.template_image_path)
        return self.template_original_size

    def _template_event_to_image_coords(self, event: tk.Event) -> tuple[int, int]:
        canvas_x = self.template_canvas.canvasx(event.x)
        canvas_y = self.template_canvas.canvasy(event.y)
        width, height = self._template_source_size()
        x = int(canvas_x / self.template_zoom)
        y = int(canvas_y / self.template_zoom)
        return max(0, min(width, x)), max(0, min(height, y))

    def _template_image_to_canvas_coords(self, x: int, y: int) -> tuple[int, int]:
        return int(x * self.template_zoom), int(y * self.template_zoom)

    def _update_template_mouse_coordinates(self, event: tk.Event) -> None:
        if self.template_image_path is None:
            self.template_mouse_coord_var.set("Mouse: --")
            return
        canvas_x = self.template_canvas.canvasx(event.x)
        canvas_y = self.template_canvas.canvasy(event.y)
        width, height = self._template_source_size()
        x = int(canvas_x / self.template_zoom)
        y = int(canvas_y / self.template_zoom)
        inside = 0 <= x < width and 0 <= y < height
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        suffix = "" if inside else " (edge)"
        self.template_mouse_coord_var.set(f"Mouse: X {x}  Y {y}{suffix}")

    def _clear_template_mouse_coordinates(self, _event: tk.Event | None = None) -> None:
        self.template_mouse_coord_var.set("Mouse: --")

    def _template_drag_start(self, event: tk.Event) -> None:
        if self.template_image_path is None:
            return
        self._update_template_mouse_coordinates(event)
        x, y = self._template_event_to_image_coords(event)
        self.template_drag_start = (x, y)
        if self.template_preview_id:
            self.template_canvas.delete(self.template_preview_id)
            self.template_preview_id = None

    def _template_drag_move(self, event: tk.Event) -> None:
        if self.template_drag_start is None:
            return
        self._update_template_mouse_coordinates(event)
        x0, y0 = self.template_drag_start
        x1, y1 = self._template_event_to_image_coords(event)
        sx0, sy0 = self._template_image_to_canvas_coords(x0, y0)
        sx1, sy1 = self._template_image_to_canvas_coords(x1, y1)
        if self.template_preview_id:
            self.template_canvas.coords(self.template_preview_id, sx0, sy0, sx1, sy1)
        else:
            self.template_preview_id = self.template_canvas.create_rectangle(
                sx0,
                sy0,
                sx1,
                sy1,
                outline=self.zone_color_var.get(),
                width=2,
                dash=(4, 2),
            )

    def _template_drag_end(self, event: tk.Event) -> None:
        if self.template_drag_start is None:
            return
        self._update_template_mouse_coordinates(event)
        x0, y0 = self.template_drag_start
        x1, y1 = self._template_event_to_image_coords(event)
        self.template_drag_start = None
        if self.template_preview_id:
            self.template_canvas.delete(self.template_preview_id)
            self.template_preview_id = None

        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        width = right - left
        height = bottom - top
        if width < 4 or height < 4:
            self._select_template_zone_at_point(x1, y1)
            return

        zone = TemplateZone(
            name=self.zone_name_var.get().strip() or f"zone_{len(self.template_zones) + 1}",
            zone_type=self.zone_type_var.get(),
            x=left,
            y=top,
            width=width,
            height=height,
            color=self.zone_color_var.get(),
            layer=template_zone_layer(self.zone_type_var.get()),
        )
        self.template_zones.append(zone)
        self._redraw_template_zones()
        self._refresh_template_zone_list()

    def _select_template_zone_at_point(self, x: int, y: int) -> bool:
        for index in range(len(self.template_zones) - 1, -1, -1):
            zone = self.template_zones[index]
            if zone.x <= x <= zone.x + zone.width and zone.y <= y <= zone.y + zone.height:
                item_id = f"zone:{index}"
                self.zone_list.selection_set(item_id)
                self.zone_list.focus(item_id)
                self.zone_list.see(item_id)
                self._load_template_zone_into_editor(index)
                self._redraw_template_zones(refresh_list=False)
                self.template_status.configure(text=f"Selected zone {zone.name}.")
                return True
        return False

    def _redraw_template_zones(self, *, refresh_list: bool = True) -> None:
        self.template_canvas.delete("zone")
        selected_index = self._selected_template_zone_index()
        for index, zone in enumerate(self.template_zones):
            x1 = zone.x + zone.width
            y1 = zone.y + zone.height
            sx0, sy0 = self._template_image_to_canvas_coords(zone.x, zone.y)
            sx1, sy1 = self._template_image_to_canvas_coords(x1, y1)
            is_selected = index == selected_index
            self.template_canvas.create_rectangle(
                sx0,
                sy0,
                sx1,
                sy1,
                outline=zone.color,
                width=4 if is_selected else 2,
                tags=("zone",),
            )
            if is_selected:
                self.template_canvas.create_rectangle(
                    sx0,
                    sy0,
                    sx1,
                    sy1,
                    outline="#ffffff",
                    width=1,
                    dash=(5, 3),
                    tags=("zone",),
                )
            label_id = self.template_canvas.create_text(
                sx0 + 4,
                sy0 + 4,
                text=zone.name,
                fill="#ffffff",
                anchor=tk.NW,
                tags=("zone",),
            )
            label_box = self.template_canvas.bbox(label_id)
            if label_box is not None:
                bx0, by0, bx1, by1 = label_box
                background_id = self.template_canvas.create_rectangle(
                    bx0 - 3,
                    by0 - 2,
                    bx1 + 3,
                    by1 + 2,
                    fill="#111827",
                    outline="#ffffff" if is_selected else "",
                    tags=("zone",),
                )
                self.template_canvas.tag_lower(background_id, label_id)
        if refresh_list:
            self._refresh_template_zone_list()

    def _refresh_template_zone_list(self, selected_index: int | None = None) -> None:
        if selected_index is None:
            selected_index = self._selected_template_zone_index()
        self.zone_list.delete(*self.zone_list.get_children())
        for index, zone in enumerate(self.template_zones):
            self.zone_list.insert(
                "",
                tk.END,
                iid=f"zone:{index}",
                text=zone.name,
                values=(
                    zone.zone_type,
                    zone.color,
                    zone.layer,
                    zone.x,
                    zone.y,
                    zone.width,
                    zone.height,
                ),
            )
        if selected_index is not None and 0 <= selected_index < len(self.template_zones):
            item_id = f"zone:{selected_index}"
            self.zone_list.selection_set(item_id)
            self.zone_list.focus(item_id)

    def open_selected_texture(self, kind: str | None = None) -> None:
        resource = self._selected_texture_resource(kind)
        if resource is None:
            messagebox.showinfo("Open texture", "Select a row with that file type first.")
            return

        if resource.kind == "DDS":
            path = self._resolve_or_export_dds(resource)
            if path is None:
                return
            self._open_texture_path(path, resource, prefer_photoshop=True)
            return

        if resource.kind == "TXTR":
            path = self._resolve_sidecar_resource(resource)
            if path is None:
                path = self._ask_for_texture_file(
                    resource,
                    "Select the TXTR file to open",
                    (("TXTR files", "*.txtr"), ("All files", "*.*")),
                )
            if path is None:
                return
            self._open_texture_path(path, resource, prefer_photoshop=False)

    def import_texture_replacement(self) -> None:
        resource = self._selected_texture_resource("DDS")
        if resource is None:
            messagebox.showinfo("Import replacement", "Select a row with a .dds file first.")
            return
        if resource.kind != "DDS":
            messagebox.showinfo(
                "Import replacement",
                "DDS replacement is supported first. TXTR replacement needs the packed TXTR range.",
            )
            return
        if not can_replace_resource(resource):
            messagebox.showinfo(
                "Import replacement",
                (
                    f"{resource.name} is not a replaceable DDS entry yet."
                ),
            )
            return

        selected = filedialog.askopenfilename(
            title=f"Select replacement DDS for {resource.name}",
            filetypes=(("DDS files", "*.dds"), ("All files", "*.*")),
        )
        if not selected:
            return

        replacement_path = Path(selected)
        try:
            replacement_size = replacement_path.stat().st_size
        except OSError as exc:
            messagebox.showerror("Replacement failed", str(exc))
            return

        if (
            resource.archive_path is None
            and resource.size is not None
            and replacement_size > resource.size
        ):
            messagebox.showerror(
                "Replacement too large",
                (
                    f"The replacement is {format_bytes(replacement_size)}, but the "
                    f"embedded DDS slot is only {format_bytes(resource.size)}. "
                    "Use the same compression/settings or a smaller texture."
                ),
            )
            return

        self.pending_replacements[resource.offset] = Replacement(resource, replacement_path)
        self.summary.configure(
            text=(
                f"{len(self.pending_replacements)} replacement staged for modified .iff export: "
                f"{replacement_path.name}"
            )
        )
        if messagebox.askyesno(
            "Replacement staged",
            "Replacement staged. Save a modified .iff copy now?",
        ):
            self.save_modified_iff_as()

    def save_modified_iff_as(self) -> None:
        if self.scan_result is None:
            messagebox.showinfo("Save modified .iff", "Import an .iff file first.")
            return
        if not self.pending_replacements:
            messagebox.showinfo(
                "Save modified .iff",
                "No DDS replacements have been staged yet.",
            )
            return

        selected = filedialog.asksaveasfilename(
            title="Save Modified IFF As",
            defaultextension=".iff",
            initialfile=f"{self.scan_result.path.stem}_modded.iff",
            filetypes=(("NBA 2K IFF files", "*.iff"), ("All files", "*.*")),
        )
        if not selected:
            return

        try:
            apply_replacements(
                self.scan_result.path,
                Path(selected),
                list(self.pending_replacements.values()),
            )
        except Exception as exc:  # noqa: BLE001 - GUI boundary, report cleanly.
            messagebox.showerror("Save modified .iff failed", str(exc))
            return

        self.summary.configure(text=f"Saved modified .iff: {selected}")
        messagebox.showinfo("Saved", f"Modified .iff saved:\n\n{selected}")

    def _open_texture_from_click(self, event: tk.Event) -> None:
        row_id = self.textures.identify_row(event.y)
        if row_id:
            self.textures.selection_set(row_id)
        column = self.textures.identify_column(event.x)
        if column in {"#1", "#4"}:
            self.open_selected_texture("DDS")
        elif column in {"#2", "#5"}:
            self.open_selected_texture("TXTR")
        else:
            self.open_selected_texture()

    def _selected_texture_resource(self, kind: str | None = None) -> ResourceHit | None:
        selected = self.textures.selection()
        if not selected:
            return None
        dds_hit, txtr_hit = self._texture_row_index.get(selected[0], (None, None))
        if kind == "DDS":
            return dds_hit
        if kind == "TXTR":
            return txtr_hit
        return dds_hit or txtr_hit

    def _resolve_or_export_dds(self, resource: ResourceHit) -> Path | None:
        sidecar = self._resolve_sidecar_resource(resource)
        if sidecar:
            return sidecar
        if self.scan_result is None:
            return None
        if resource.archive_path:
            return self._export_archive_resource(resource)
        if not can_replace_embedded_resource(resource):
            return self._ask_for_texture_file(
                resource,
                "Select the DDS file to open",
                (("DDS files", "*.dds"), ("All files", "*.*")),
            )

        assert resource.size is not None
        data = self.scan_result.path.read_bytes()
        export_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / self.scan_result.path.stem
        )
        export_dir.mkdir(parents=True, exist_ok=True)
        safe_name = safe_filename(resource.name)
        output_path = export_dir / safe_name
        output_path.write_bytes(data[resource.offset : resource.offset + resource.size])
        return output_path

    def _export_archive_resource(self, resource: ResourceHit) -> Path | None:
        if self.scan_result is None or resource.archive_path is None:
            return None
        import zipfile

        export_dir = (
            Path(tempfile.gettempdir())
            / "nba2k_jersey_modder"
            / self.scan_result.path.stem
        )
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / safe_filename(resource.name)
        with zipfile.ZipFile(self.scan_result.path, "r") as archive:
            output_path.write_bytes(archive.read(resource.archive_path))
        return output_path

    def _resolve_sidecar_resource(self, resource: ResourceHit) -> Path | None:
        override = self.texture_file_overrides.get(_resource_key(resource))
        if override and override.exists():
            return override
        if self.scan_result is None:
            return None
        if resource.archive_path:
            return self._export_archive_resource(resource)
        base_dir = self.scan_result.path.parent
        normalized = resource.name.replace("/", "\\")
        candidate = base_dir / normalized
        if candidate.exists():
            return candidate
        candidate = base_dir / Path(resource.name).name
        if candidate.exists():
            return candidate
        file_name = Path(resource.name).name
        try:
            for found in base_dir.rglob(file_name):
                if found.is_file():
                    return found
        except OSError:
            pass
        return None

    def _ask_for_texture_file(
        self,
        resource: ResourceHit,
        title: str,
        filetypes: tuple[tuple[str, str], ...],
    ) -> Path | None:
        selected = filedialog.askopenfilename(
            title=f"{title}: {resource.name}",
            initialfile=Path(resource.name).name,
            filetypes=filetypes,
        )
        if not selected:
            return None
        path = Path(selected)
        self.texture_file_overrides[_resource_key(resource)] = path
        self.summary.configure(text=f"Linked {resource.name} to {path.name} for this session.")
        return path

    def _open_texture_path(
        self,
        path: Path,
        resource: ResourceHit,
        prefer_photoshop: bool,
    ) -> None:
        try:
            open_texture_file(path, resource.kind, prefer_photoshop=prefer_photoshop)
        except OSError as exc:
            messagebox.showerror(
                "Open failed",
                (
                    f"Could not open {path.name}.\n\n"
                    f"Reason: {exc}\n\n"
                    "If this is a DDS file, make sure Photoshop is installed with DDS support "
                    "or set DDS files to open with your texture editor in Windows."
                ),
            )

    def open_rdat(self) -> None:
        selected = filedialog.askopenfilename(
            title="Open RDAT file",
            filetypes=(
                ("RDAT / IFF files", "*.rdat *.iff"),
                ("RDAT files", "*.rdat"),
                ("IFF files", "*.iff"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self._load_rdat_file(Path(selected))

    def save_rdat(self) -> None:
        if self.rdat_path is None:
            self.save_rdat_as()
            return
        self._write_rdat_file(self.rdat_path)

    def save_rdat_as(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Save RDAT file",
            defaultextension=".rdat",
            filetypes=(
                ("RDAT / IFF files", "*.rdat *.iff"),
                ("RDAT files", "*.rdat"),
                ("IFF files", "*.iff"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ),
        )
        if selected:
            self._write_rdat_file(Path(selected))

    def load_selected_rdat_reference(self) -> None:
        selected = self.rdat_refs.selection()
        if not selected:
            messagebox.showinfo("Load RDAT", "Select an RDAT reference first.")
            return
        resource = self._rdat_resource_index.get(selected[0])
        if resource is None:
            return
        if resource.archive_path and self.scan_result is not None:
            self._load_rdat_file(self.scan_result.path, archive_entry=resource.archive_path)
            return
        path = self._resolve_rdat_reference(resource)
        if path is None:
            messagebox.showinfo(
                "RDAT not found",
                (
                    f"{resource.name} was referenced in the .iff, but no matching "
                    "file was found next to the imported .iff. Open it manually if "
                    "it lives somewhere else."
                ),
            )
            return
        self._load_rdat_file(path)

    def _open_selected_rdat_reference(self, _event: tk.Event) -> None:
        self.load_selected_rdat_reference()

    def _load_rdat_file(self, path: Path, archive_entry: str | None = None) -> None:
        try:
            entry_name, data = self._read_rdat_data(path, archive_entry)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            messagebox.showerror("Open RDAT failed", str(exc))
            return

        text, encoding = decode_text_file(data)
        self.rdat_path = path
        self.rdat_archive_entry = entry_name
        self.rdat_encoding = encoding
        self.rdat_editor.delete("1.0", tk.END)
        self.rdat_editor.insert("1.0", text)
        self.rdat_editor.edit_modified(False)
        self.rdat_dirty = False
        if entry_name:
            self.rdat_status.configure(text=f"Loaded {entry_name} from {path.name} ({encoding}).")
        else:
            self.rdat_status.configure(text=f"Loaded {path} ({encoding}).")
        self.tabs.select(self.rdat_tab)

    def _write_rdat_file(self, path: Path) -> None:
        text = self.rdat_editor.get("1.0", "end-1c")
        try:
            if self.rdat_archive_entry and path.suffix.lower() == ".iff":
                self._write_rdat_archive_entry(path, text)
            else:
                path.write_text(text, encoding=self.rdat_encoding, newline="")
                if path.suffix.lower() != ".iff":
                    self.rdat_archive_entry = None
        except (OSError, zipfile.BadZipFile) as exc:
            messagebox.showerror("Save RDAT failed", str(exc))
            return
        self.rdat_path = path
        self.rdat_dirty = False
        self.rdat_editor.edit_modified(False)
        if self.rdat_archive_entry and path.suffix.lower() == ".iff":
            self.rdat_status.configure(text=f"Saved {self.rdat_archive_entry} inside {path}.")
        else:
            self.rdat_status.configure(text=f"Saved {path}.")

    def _resolve_rdat_reference(self, resource: ResourceHit) -> Path | None:
        if self.scan_result is None:
            return None
        if resource.archive_path:
            return self.scan_result.path
        base_dir = self.scan_result.path.parent
        candidate = base_dir / resource.name.replace("/", "\\")
        if candidate.exists():
            return candidate
        candidate = base_dir / Path(resource.name).name
        if candidate.exists():
            return candidate
        return None

    def _read_rdat_data(self, path: Path, archive_entry: str | None = None) -> tuple[str | None, bytes]:
        if archive_entry is not None:
            with zipfile.ZipFile(path, "r") as archive:
                return archive_entry, archive.read(archive_entry)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as archive:
                entries = [
                    info.filename
                    for info in archive.infolist()
                    if not info.is_dir() and info.filename.lower().endswith(".rdat")
                ]
                if not entries:
                    raise ValueError("No .rdat file was found inside this IFF.")
                entry = self._choose_rdat_archive_entry(entries)
                if entry is None:
                    raise ValueError("No RDAT entry selected.")
                return entry, archive.read(entry)
        if path.suffix.lower() == ".iff":
            raise ValueError(
                "This IFF is not a readable archive-style RDAT container. "
                "Import it first and use an RDAT reference, or open a loose .rdat file."
            )
        return None, path.read_bytes()

    def _choose_rdat_archive_entry(self, entries: list[str]) -> str | None:
        if len(entries) == 1:
            return entries[0]

        dialog = tk.Toplevel(self)
        dialog.title("Choose RDAT")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Choose the RDAT file to edit:").grid(
            row=0,
            column=0,
            sticky="w",
            padx=12,
            pady=(12, 6),
        )
        listbox = tk.Listbox(dialog, width=64, height=min(10, len(entries)))
        listbox.grid(row=1, column=0, sticky="nsew", padx=12)
        for entry in entries:
            listbox.insert(tk.END, entry)
        listbox.selection_set(0)
        selected: dict[str, str | None] = {"value": None}

        def accept() -> None:
            selection = listbox.curselection()
            if selection:
                selected["value"] = entries[selection[0]]
            dialog.destroy()

        def cancel() -> None:
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=2, column=0, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Open", command=accept).pack(side=tk.RIGHT, padx=(0, 8))
        listbox.bind("<Double-1>", lambda _event: accept())
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.wait_window()
        return selected["value"]

    def _write_rdat_archive_entry(self, output_path: Path, text: str) -> None:
        if self.rdat_path is None or self.rdat_archive_entry is None:
            raise OSError("No source IFF RDAT entry is loaded.")
        replacement_data = text.encode(self.rdat_encoding)
        same_path = self.rdat_path.resolve() == output_path.resolve()
        target_path = output_path
        temp_output: Path | None = None
        if same_path:
            handle = tempfile.NamedTemporaryFile(
                prefix=f"{output_path.stem}_",
                suffix=output_path.suffix,
                dir=output_path.parent,
                delete=False,
            )
            temp_output = Path(handle.name)
            handle.close()
            target_path = temp_output

        with zipfile.ZipFile(self.rdat_path, "r") as source:
            with zipfile.ZipFile(target_path, "w") as target:
                for info in source.infolist():
                    data = (
                        replacement_data
                        if info.filename == self.rdat_archive_entry
                        else source.read(info.filename)
                    )
                    new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    new_info.compress_type = info.compress_type
                    new_info.comment = info.comment
                    new_info.extra = info.extra
                    new_info.internal_attr = info.internal_attr
                    new_info.external_attr = info.external_attr
                    target.writestr(new_info, data)
        if temp_output is not None:
            temp_output.replace(output_path)

    def _on_rdat_modified(self, _event: tk.Event) -> None:
        if not self.rdat_editor.edit_modified():
            return
        self.rdat_dirty = True
        label = self.rdat_path.name if self.rdat_path else "untitled.rdat"
        self.rdat_status.configure(text=f"Editing {label} - unsaved changes.")
        self.rdat_editor.edit_modified(False)

def _nudge_image(image, offset_x: int, offset_y: int):
    from PIL import Image

    canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    return _paste_image_on_canvas(image, canvas, offset_x, offset_y)


def _paste_image_on_canvas(image, canvas, offset_x: int, offset_y: int):
    source_left = max(0, -offset_x)
    source_top = max(0, -offset_y)
    dest_left = max(0, offset_x)
    dest_top = max(0, offset_y)
    paste_width = min(image.width - source_left, canvas.width - dest_left)
    paste_height = min(image.height - source_top, canvas.height - dest_top)
    source_right = source_left + paste_width
    source_bottom = source_top + paste_height
    if source_right <= source_left or source_bottom <= source_top:
        return canvas
    cropped = image.crop((source_left, source_top, source_right, source_bottom))
    canvas.alpha_composite(cropped, (dest_left, dest_top))
    return canvas


def _place_image_visible_center(image, size: tuple[int, int], target_center: tuple[float, float]):
    from PIL import Image

    cell = Image.new("RGBA", size, (0, 0, 0, 0))
    working = image.convert("RGBA")
    if working.width > size[0] or working.height > size[1]:
        working.thumbnail(size, Image.Resampling.LANCZOS)
    center = _visible_image_center(working)
    if center is None:
        return cell
    offset_x = round(target_center[0] - center[0])
    offset_y = round(target_center[1] - center[1])
    return _paste_image_on_canvas(working, cell, offset_x, offset_y)


def _visible_image_center(image) -> tuple[float, float] | None:
    bbox = _visible_image_bounds(image)
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    return ((left + right - 1) / 2, (top + bottom - 1) / 2)


def _visible_image_bounds(image) -> tuple[int, int, int, int] | None:
    alpha = image.convert("RGBA").getchannel("A")
    return alpha.getbbox()


def _align_image_to_visible_center(image, target_center: tuple[float, float]):
    center = _visible_image_center(image)
    if center is None:
        return image
    offset_x = round(target_center[0] - center[0])
    offset_y = round(target_center[1] - center[1])
    if offset_x == 0 and offset_y == 0:
        return image
    return _nudge_image(image, offset_x, offset_y)


def _recolor_font_image(
    image,
    dark_color: tuple[int, int, int] | None,
    light_color: tuple[int, int, int] | None,
    *,
    edge_protection: float = 0.75,
    outline_thickness: int = 0,
):
    rgba = image.convert("RGBA")
    if dark_color is None and light_color is None:
        return rgba
    edge_protection = _clamp(edge_protection, 0.0, 1.0)
    outline_thickness = max(0, min(3, int(outline_thickness)))
    rgba_data = getattr(rgba, "get_flattened_data", rgba.getdata)
    pixels = list(rgba_data())
    distances = _font_alpha_edge_distances(rgba)
    fill_mixes = _font_fill_region_mixes(pixels, distances, edge_protection)
    if fill_mixes is None:
        return rgba
    if outline_thickness:
        fill_mixes = _thicken_font_outline_mixes(
            pixels,
            fill_mixes,
            rgba.width,
            rgba.height,
            outline_thickness,
        )

    recolored = []
    for index, (red, green, blue, alpha) in enumerate(pixels):
        if alpha == 0:
            recolored.append((red, green, blue, alpha))
            continue
        mix = fill_mixes[index]
        original = (red, green, blue)
        outline = dark_color if dark_color is not None else original
        fill = light_color if light_color is not None else original
        recolored.append((*_blend_rgb(outline, fill, mix), alpha))
    rgba.putdata(recolored)
    return rgba


def _thicken_font_outline_mixes(
    pixels: list[tuple[int, int, int, int]],
    fill_mixes: list[float],
    width: int,
    height: int,
    amount: int,
) -> list[float]:
    mixes = list(fill_mixes)
    outline = {
        index
        for index, (_red, _green, _blue, alpha) in enumerate(pixels)
        if alpha > 0 and mixes[index] <= 0.52
    }
    visible = {index for index, pixel in enumerate(pixels) if pixel[3] > 0}
    for _step in range(amount):
        next_outline = set(outline)
        for index in outline:
            x = index % width
            y = index // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if neighbor in visible and mixes[neighbor] > 0.52:
                        next_outline.add(neighbor)
        if len(next_outline) == len(outline):
            break
        outline = next_outline
    for index in outline:
        mixes[index] = 0.0
    return mixes


def _font_fill_region_mixes(
    pixels: list[tuple[int, int, int, int]],
    distances: list[float],
    edge_protection: float,
) -> list[float] | None:
    visible_indices = [
        index
        for index, (_red, _green, _blue, alpha) in enumerate(pixels)
        if alpha > 0
    ]
    if not visible_indices:
        return None

    visible_distances = [distances[index] for index in visible_indices]
    distance_mixes = _font_distance_fill_mixes(
        visible_indices,
        distances,
        edge_protection,
        len(pixels),
    )
    centers = _font_outline_fill_color_centers(pixels, distances, visible_indices)
    if centers is None:
        return distance_mixes

    outline_center, fill_center = centers
    separation = _rgb_distance(outline_center, fill_center)
    color_weight = _clamp((separation - 16.0) / 72.0, 0.0, 1.0)
    if color_weight <= 0:
        return distance_mixes

    max_distance = max(visible_distances) if visible_distances else 1.0
    mixes = [0.0] * len(pixels)
    edge_gate_weight = 0.42 * edge_protection
    for index in visible_indices:
        red, green, blue, _alpha = pixels[index]
        color = (red, green, blue)
        outline_distance = _rgb_distance(color, outline_center)
        fill_distance = _rgb_distance(color, fill_center)
        color_mix = outline_distance / max(1.0, outline_distance + fill_distance)
        color_mix = _smoothstep(_clamp(color_mix, 0.0, 1.0))
        distance_mix = distance_mixes[index]
        if max_distance > 1:
            interior_ratio = _clamp(distances[index] / max_distance, 0.0, 1.0)
            edge_gate = _smoothstep(interior_ratio)
            color_mix *= (1.0 - edge_gate_weight) + edge_gate_weight * edge_gate
        mixes[index] = (
            color_mix * color_weight
            + distance_mix * (1.0 - color_weight)
        )
    return mixes


def _font_distance_fill_mixes(
    visible_indices: list[int],
    distances: list[float],
    edge_protection: float,
    pixel_count: int,
) -> list[float]:
    edge_threshold = 0.75 + (edge_protection * 2.75)
    edge_softness = max(0.65, 2.2 - (edge_protection * 1.25))
    mixes = [0.0] * pixel_count
    for index in visible_indices:
        mixes[index] = _smoothstep(
            _clamp((distances[index] - edge_threshold) / edge_softness, 0.0, 1.0)
        )
    return mixes


def _font_outline_fill_color_centers(
    pixels: list[tuple[int, int, int, int]],
    distances: list[float],
    visible_indices: list[int],
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    if len(visible_indices) < 2:
        return None
    distance_values = sorted(distances[index] for index in visible_indices)
    edge_cutoff = _percentile(distance_values, 0.28)
    fill_cutoff = _percentile(distance_values, 0.72)
    edge_indices = [
        index for index in visible_indices if distances[index] <= edge_cutoff
    ] or visible_indices
    fill_indices = [
        index for index in visible_indices if distances[index] >= fill_cutoff
    ] or visible_indices
    centers = [
        _average_rgb(pixels, edge_indices),
        _average_rgb(pixels, fill_indices),
    ]
    if _rgb_distance(centers[0], centers[1]) < 8:
        return None

    assignments: dict[int, list[int]] = {0: [], 1: []}
    for _iteration in range(8):
        assignments = {0: [], 1: []}
        for index in visible_indices:
            red, green, blue, _alpha = pixels[index]
            color = (red, green, blue)
            group = (
                0
                if _rgb_distance(color, centers[0]) <= _rgb_distance(color, centers[1])
                else 1
            )
            assignments[group].append(index)
        if not assignments[0] or not assignments[1]:
            return None
        next_centers = [
            _average_rgb(pixels, assignments[0]),
            _average_rgb(pixels, assignments[1]),
        ]
        if all(_rgb_distance(centers[index], next_centers[index]) < 0.5 for index in (0, 1)):
            centers = next_centers
            break
        centers = next_centers

    mean_distances = [
        sum(distances[index] for index in assignments[group]) / len(assignments[group])
        for group in (0, 1)
    ]
    if abs(mean_distances[0] - mean_distances[1]) < 0.35:
        return None
    fill_group = 0 if mean_distances[0] > mean_distances[1] else 1
    outline_group = 1 - fill_group
    return centers[outline_group], centers[fill_group]


def _average_rgb(
    pixels: list[tuple[int, int, int, int]],
    indices: list[int],
) -> tuple[float, float, float]:
    if not indices:
        return (0.0, 0.0, 0.0)
    red = sum(pixels[index][0] for index in indices) / len(indices)
    green = sum(pixels[index][1] for index in indices) / len(indices)
    blue = sum(pixels[index][2] for index in indices) / len(indices)
    return red, green, blue


def _rgb_distance(
    first: tuple[float, float, float] | tuple[int, int, int],
    second: tuple[float, float, float] | tuple[int, int, int],
) -> float:
    return (
        (first[0] - second[0]) ** 2
        + (first[1] - second[1]) ** 2
        + (first[2] - second[2]) ** 2
    ) ** 0.5


def _blend_rgb(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    mix: float,
) -> tuple[int, int, int]:
    return (
        round(start[0] * (1 - mix) + end[0] * mix),
        round(start[1] * (1 - mix) + end[1] * mix),
        round(start[2] * (1 - mix) + end[2] * mix),
    )


def _font_alpha_edge_distances(image) -> list[float]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    alpha_channel = rgba.getchannel("A")
    alpha_data = getattr(alpha_channel, "get_flattened_data", alpha_channel.getdata)
    alpha_values = list(alpha_data())
    large = width + height + 2
    distances = [large if alpha > 0 else 0 for alpha in alpha_values]

    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            if distances[index] == 0:
                continue
            if x == 0 or y == 0:
                distances[index] = min(distances[index], 1)
            if x > 0:
                distances[index] = min(distances[index], distances[index - 1] + 1)
            if y > 0:
                distances[index] = min(distances[index], distances[index - width] + 1)

    for y in range(height - 1, -1, -1):
        row = y * width
        for x in range(width - 1, -1, -1):
            index = row + x
            if distances[index] == 0:
                continue
            if x == width - 1 or y == height - 1:
                distances[index] = min(distances[index], 1)
            if x + 1 < width:
                distances[index] = min(distances[index], distances[index + 1] + 1)
            if y + 1 < height:
                distances[index] = min(distances[index], distances[index + width] + 1)

    return [float(distance) for distance in distances]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _smoothstep(value: float) -> float:
    return value * value * (3 - (2 * value))


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ratio = _clamp(ratio, 0.0, 1.0)
    position = ratio * (len(values) - 1)
    lower_index = int(position)
    upper_index = min(len(values) - 1, lower_index + 1)
    mix = position - lower_index
    return values[lower_index] * (1.0 - mix) + values[upper_index] * mix


def _pixel_luminance(red: int, green: int, blue: int) -> float:
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _crop_trim_image(image, crop_top: int, crop_bottom: int):
    from PIL import Image

    crop_top = int(crop_top)
    crop_bottom = int(crop_bottom)
    pad_top = max(0, -crop_top)
    pad_bottom = max(0, -crop_bottom)
    remove_top = min(max(0, crop_top), max(0, image.height - 1))
    remove_bottom = min(
        max(0, crop_bottom),
        max(0, image.height - remove_top - 1),
    )
    cropped = image.crop((0, remove_top, image.width, image.height - remove_bottom))
    if pad_top == 0 and pad_bottom == 0:
        return cropped
    expanded = Image.new(
        "RGBA",
        (cropped.width, cropped.height + pad_top + pad_bottom),
        (0, 0, 0, 0),
    )
    expanded.alpha_composite(cropped, (0, pad_top))
    return expanded


def _trim_transparent_padding(image, *, padding: int = 8):
    from PIL import Image

    rgba = image.convert("RGBA")
    alpha_box = rgba.getchannel("A").getbbox()
    if alpha_box is None:
        return Image.new("RGBA", (max(1, padding * 2), max(1, padding * 2)), (0, 0, 0, 0))
    left, top, right, bottom = alpha_box
    cropped = rgba.crop((left, top, right, bottom))
    padded = Image.new(
        "RGBA",
        (cropped.width + padding * 2, cropped.height + padding * 2),
        (0, 0, 0, 0),
    )
    padded.alpha_composite(cropped, (padding, padding))
    return padded


def _fit_transparent_image_to_square(
    image,
    size: int,
    *,
    padding_ratio: float = 0.08,
):
    from PIL import Image

    size = max(1, int(size))
    transparent = image.convert("RGBA")
    alpha_box = transparent.getchannel("A").getbbox()
    if alpha_box is None:
        return Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cropped = transparent.crop(alpha_box)
    padding = max(0, min(size // 3, round(size * padding_ratio)))
    max_content = max(1, size - padding * 2)
    scale = min(max_content / cropped.width, max_content / cropped.height)
    fitted_size = (
        max(1, round(cropped.width * scale)),
        max(1, round(cropped.height * scale)),
    )
    fitted = cropped.resize(fitted_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(
        fitted,
        (
            (size - fitted.width) // 2,
            (size - fitted.height) // 2,
        ),
    )
    return canvas


def _loaded_number_digit_keys(digit_paths: dict[str, Path]) -> set[str]:
    return {
        str(index)
        for index in range(10)
        if (path := digit_paths.get(str(index))) is not None and path.exists()
    }


def _remove_sampled_color_background(
    image,
    color: tuple[int, int, int],
    *,
    outside_only: bool = True,
    tolerance: int = 32,
):
    cleaned = image.copy()
    pixels = cleaned.load()
    tolerance = max(0, min(255, int(tolerance)))

    def matches(x: int, y: int) -> bool:
        red, green, blue, alpha = pixels[x, y]
        if alpha < 16:
            return False
        return max(
            abs(red - color[0]),
            abs(green - color[1]),
            abs(blue - color[2]),
        ) <= tolerance

    if not outside_only:
        for y in range(cleaned.height):
            for x in range(cleaned.width):
                if matches(x, y):
                    red, green, blue, _alpha = pixels[x, y]
                    pixels[x, y] = (red, green, blue, 0)
        return cleaned

    width, height = cleaned.size
    visited = bytearray(width * height)
    queue: list[tuple[int, int]] = []

    def maybe_queue(x: int, y: int) -> None:
        index = y * width + x
        if visited[index] or not matches(x, y):
            return
        visited[index] = 1
        queue.append((x, y))

    for x in range(width):
        maybe_queue(x, 0)
        maybe_queue(x, height - 1)
    for y in range(1, height - 1):
        maybe_queue(0, y)
        maybe_queue(width - 1, y)

    index = 0
    while index < len(queue):
        x, y = queue[index]
        index += 1
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        if x > 0:
            maybe_queue(x - 1, y)
        if x < width - 1:
            maybe_queue(x + 1, y)
        if y > 0:
            maybe_queue(x, y - 1)
        if y < height - 1:
            maybe_queue(x, y + 1)
    return cleaned


def _replace_trim_color(
    image,
    source_color: tuple[int, int, int],
    replacement_color: tuple[int, int, int],
    tolerance: int,
):
    corrected = image.copy()
    pixels = corrected.load()
    tolerance = max(0, min(255, int(tolerance)))
    for y in range(corrected.height):
        for x in range(corrected.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            distance = max(
                abs(red - source_color[0]),
                abs(green - source_color[1]),
                abs(blue - source_color[2]),
            )
            if distance > tolerance:
                continue
            pixels[x, y] = (
                replacement_color[0],
                replacement_color[1],
                replacement_color[2],
                alpha,
            )
    return corrected


def _dominant_visible_color(image) -> tuple[int, int, int] | None:
    pixels = image.load()
    buckets: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha < 16:
                continue
            bucket = (red // 16, green // 16, blue // 16)
            buckets.setdefault(bucket, []).append((red, green, blue))
    if not buckets:
        return None
    samples = max(buckets.values(), key=len)
    return (
        round(sum(color[0] for color in samples) / len(samples)),
        round(sum(color[1] for color in samples) / len(samples)),
        round(sum(color[2] for color in samples) / len(samples)),
    )


def _rgb_to_hex(color: tuple[int, int, int]) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    normalized = color.strip().lstrip("#")
    if len(normalized) == 3:
        normalized = "".join(character * 2 for character in normalized)
    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
    )


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an available file name near {path.name}.")


def texture_rows_for_pair(
    pair: TexturePair,
) -> list[tuple[ResourceHit | None, ResourceHit | None]]:
    row_count = max(len(pair.dds_hits), len(pair.txtr_hits), 1)
    rows: list[tuple[ResourceHit | None, ResourceHit | None]] = []
    for index in range(row_count):
        dds_hit = pair.dds_hits[index] if index < len(pair.dds_hits) else None
        txtr_hit = pair.txtr_hits[index] if index < len(pair.txtr_hits) else None
        rows.append((dds_hit, txtr_hit))
    return rows


def template_zone_layer(zone_type: str) -> int:
    return {
        "base": 0,
        "pattern": 10,
        "stripe": 20,
        "trim": 30,
        "wordmark": 40,
        "number": 40,
        "name": 40,
        "logo": 50,
        "patch": 50,
        "mask": 60,
    }.get(zone_type, 10)


def texture_row_status(
    dds_hit: ResourceHit | None,
    txtr_hit: ResourceHit | None,
) -> str:
    if dds_hit and txtr_hit:
        return "Matched"
    if dds_hit:
        return "Missing .txtr"
    return "Missing .dds"


def texture_row_source(
    dds_hit: ResourceHit | None,
    txtr_hit: ResourceHit | None,
) -> str:
    sources = []
    if dds_hit:
        sources.append(dds_hit.source)
    if txtr_hit:
        sources.append(txtr_hit.source)
    return " / ".join(dict.fromkeys(sources))


def offsets_summary(hits: tuple[ResourceHit, ...]) -> str:
    if not hits:
        return ""
    shown = ", ".join(hex_offset(hit.offset) for hit in hits[:4])
    if len(hits) > 4:
        shown += f", +{len(hits) - 4} more"
    return shown


def texture_hit_summary(hits: tuple[ResourceHit, ...]) -> str:
    if not hits:
        return "none"
    label = "hit" if len(hits) == 1 else "hits"
    return f"{len(hits)} {label}: {offsets_summary(hits)}"


def resource_column_value(resource: ResourceHit, kind: str) -> str:
    if resource.kind != kind:
        return ""
    value = hex_offset(resource.offset)
    if resource.size:
        value += f" | {format_bytes(resource.size)}"
    return value


def _pair_source_summary(pair: TexturePair) -> str:
    if pair.dds_hits and pair.txtr_hits:
        return "grouped by matching texture name"
    return "needs matching counterpart"


def _resource_key(resource: ResourceHit) -> tuple[str, int, str]:
    return (resource.kind, resource.offset, resource.name.lower())


def decode_text_file(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"


def read_image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError:
        image = tk.PhotoImage(file=str(path))
        return image.width(), image.height()

    with Image.open(path) as image:
        return image.size


def image_content_type(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    if extension == ".gif":
        return "image/gif"
    if extension == ".bmp":
        return "image/bmp"
    return "image/png"


def load_scaled_photo_image(path: Path, width: int, height: int) -> tk.PhotoImage:
    try:
        from PIL import Image, ImageTk
    except ImportError:
        image = tk.PhotoImage(file=str(path))
        if width >= image.width() or height >= image.height():
            return image
        step = max(1, round(max(image.width() / width, image.height() / height)))
        return image.subsample(step, step)

    image = Image.open(path).convert("RGBA")
    image = image.resize((width, height), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image)


def open_texture_file(
    path: Path,
    kind: str,
    prefer_photoshop: bool = False,
) -> None:
    if kind == "DDS" and prefer_photoshop:
        photoshop = find_photoshop_executable()
        if photoshop:
            subprocess.Popen([str(photoshop), str(path)])
            return
    if kind == "TXTR":
        subprocess.Popen(["notepad.exe", str(path)])
        return
    os.startfile(path)


def find_photoshop_executable() -> Path | None:
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ]
    candidates: list[Path] = []
    for root in roots:
        adobe_dir = root / "Adobe"
        if not adobe_dir.exists():
            continue
        candidates.extend(adobe_dir.glob("Adobe Photoshop*\\Photoshop.exe"))
    return sorted(candidates, reverse=True)[0] if candidates else None


def safe_filename(name: str) -> str:
    cleaned = Path(name.replace("\\", "/")).name
    return "".join(char if char not in '<>:"/\\|?*' else "_" for char in cleaned)


def hex_offset(offset: int) -> str:
    return f"0x{offset:08X}"


def format_bytes(size: int | None) -> str:
    if size is None:
        return ""
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def _point_to_segment_distance(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    dx = x2 - x1
    dy = y2 - y1
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return _distance(px, py, x1, y1)
    amount = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_squared))
    closest_x = x1 + amount * dx
    closest_y = y1 + amount * dy
    return _distance(px, py, closest_x, closest_y)


def _trim_name_for_generator_key(key: str) -> str | None:
    for trim_name, generator_key in TRIM_GENERATOR_KEYS.items():
        if generator_key == key:
            return trim_name
    return None


def _clamp_overlay_to_clip(
    x: float,
    y: float,
    width: float,
    height: float,
    clip_x: int,
    clip_y: int,
    clip_width: int,
    clip_height: int,
) -> tuple[float, float, float, float]:
    clip_right = clip_x + clip_width
    clip_bottom = clip_y + clip_height
    width = max(1.0, width)
    height = max(1.0, height)
    if width <= clip_width:
        x = max(clip_x, min(x, clip_right - width))
    else:
        x = max(clip_right - width, min(x, clip_x))
    if height <= clip_height:
        y = max(clip_y, min(y, clip_bottom - height))
    else:
        y = max(clip_bottom - height, min(y, clip_y))
    return x, y, width, height


def _scale_dimension_percent(
    current_scale: int | None,
    fallback_scale: int,
    new_size: float,
    current_size: float,
) -> int:
    base_scale = fallback_scale if current_scale is None else current_scale
    scale = round(max(1, base_scale) * new_size / max(1, current_size))
    return max(1, min(500, scale))


def main() -> None:
    app = JerseyModderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
