from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QPushButton, QScrollArea, QSlider, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from ...generator import DEFAULT_LOGO_TARGETS
from ..document import GENERATOR_DEFAULT_COLORS, ProjectDocument
from ..services import GeneratorService
from ..widgets import CollapsibleSection, ColorField, FileField, ImageView, PageHeader, pil_to_qimage
from .base import FeaturePage, Worker


IMAGE_ROWS = (
    ("front_wordmark_image", "Front wordmark"),
    ("jersey_background_image", "Background jersey image"),
    ("left_panel_image", "Left side panel"), ("right_panel_image", "Right side panel"),
    ("collar_trim_image", "Collar trim"),
    ("left_arm_hole_trim_image", "Left arm hole trim"),
    ("right_arm_hole_trim_image", "Right arm hole trim"),
)
SHORTS_IMAGE_ROWS = (("shorts_left_panel_image", "Left shorts panel"),
                     ("shorts_right_panel_image", "Right shorts panel"),
                     ("waistband_image", "Waistband image"))
LOGO_LABELS = {zone.name: zone.name.replace("_", " ").title() for zone in DEFAULT_LOGO_TARGETS}
LOGO_LABELS["shorts_belt_buckle_logo"] = "Shorts Belt Buckle Logo"


class GeneratorPage(FeaturePage):
    documentChanged = Signal()
    statusChanged = Signal(str)
    webEditorRequested = Signal()
    blenderRequested = Signal()

    def __init__(self, document: ProjectDocument, service: GeneratorService, parent=None) -> None:
        super().__init__(parent); self.document = document; self.service = service
        self.pool = QThreadPool.globalInstance(); self._revision = 0; self._loading = False
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(110); self.timer.timeout.connect(self.render_preview)
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(8)
        root.addWidget(PageHeader("Generator", "Build jersey and shorts color textures from reusable template zones."))
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False); root.addWidget(splitter, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setMinimumWidth(365); scroll.setMaximumWidth(540)
        controls = QWidget(); self.controls_layout = QVBoxLayout(controls); self.controls_layout.setContentsMargins(0, 0, 8, 0); self.controls_layout.setSpacing(4)
        scroll.setWidget(controls); splitter.addWidget(scroll)
        preview_side = QWidget(); preview_layout = QVBoxLayout(preview_side); preview_layout.setContentsMargins(0, 0, 0, 0); preview_layout.setSpacing(8)
        action_bar = QHBoxLayout()
        open_web = QPushButton("Open Web Editor"); open_web.setObjectName("primaryBar"); open_web.clicked.connect(self.webEditorRequested); action_bar.addWidget(open_web, 2)
        open_blender = QPushButton("Open Blender Preview"); open_blender.clicked.connect(self.blenderRequested); action_bar.addWidget(open_blender, 1)
        preview_layout.addLayout(action_bar)
        bar = QHBoxLayout(); self.preview_status = QLabel("Preparing preview..."); self.preview_status.setObjectName("muted"); bar.addWidget(self.preview_status, 1)
        fit = QToolButton(); fit.setText("Fit"); fit.clicked.connect(lambda: self.preview.fit_image()); bar.addWidget(fit); preview_layout.addLayout(bar)
        self.preview = ImageView(); preview_layout.addWidget(self.preview, 1); splitter.addWidget(preview_side); splitter.setSizes([410, 820])
        self._build_template(); self._build_colors(); self._build_images(); self._build_waistband(); self._build_logos(); self.controls_layout.addStretch()
        self.load_document(document)

    def _build_template(self) -> None:
        section = CollapsibleSection("Template", True); self.controls_layout.addWidget(section)
        row = QHBoxLayout(); row.addWidget(QLabel("Garment")); self.garment = QComboBox(); self.garment.addItems(("Jersey", "Shorts")); row.addWidget(self.garment, 1); section.body_layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel("Template")); self.template = QComboBox(); row.addWidget(self.template, 1); section.body_layout.addLayout(row)
        uv_row = QHBoxLayout(); self.uv_enabled = QCheckBox("UV overlay"); uv_row.addWidget(self.uv_enabled); uv_row.addWidget(QLabel("Opacity"))
        self.uv_opacity = QSlider(Qt.Orientation.Horizontal); self.uv_opacity.setRange(0, 100); uv_row.addWidget(self.uv_opacity, 1)
        self.uv_value = QLabel("45%"); self.uv_value.setMinimumWidth(38); uv_row.addWidget(self.uv_value); section.body_layout.addLayout(uv_row)
        generate = QPushButton("Generate Preview"); generate.clicked.connect(self.render_preview); section.body_layout.addWidget(generate)
        self.garment.currentTextChanged.connect(self._garment_changed); self.template.currentTextChanged.connect(self._template_changed)
        self.uv_enabled.toggled.connect(self._uv_changed); self.uv_opacity.valueChanged.connect(self._uv_changed)

    def _build_colors(self) -> None:
        self.colors_section = CollapsibleSection("Colors"); self.controls_layout.addWidget(self.colors_section); self.color_fields = {}
        labels = {"front_color":"Front", "back_color":"Back", "left_panel_color":"Left side panel", "right_panel_color":"Right side panel", "collar_background_color":"Collar background", "waistband_color":"Waistband"}
        for key, label in labels.items():
            field = ColorField(label, allow_none=key in {"left_panel_color", "right_panel_color"}); field.changed.connect(lambda value, k=key: self._set_color(k, value))
            self.color_fields[key] = field; self.colors_section.body_layout.addWidget(field)
        self.trim_section = CollapsibleSection("Trim Colors"); self.controls_layout.addWidget(self.trim_section)
        for key, label in (("left_arm_hole_trim_color","Left arm hole"),("right_arm_hole_trim_color","Right arm hole"),("collar_trim_color","Collar trim")):
            field = ColorField(label); field.changed.connect(lambda value, k=key: self._set_color(k, value)); self.color_fields[key] = field; self.trim_section.body_layout.addWidget(field)

    def _build_images(self) -> None:
        self.images_section = CollapsibleSection("Images"); self.controls_layout.addWidget(self.images_section); self.image_fields = {}
        for key, label in IMAGE_ROWS + SHORTS_IMAGE_ROWS:
            field = FileField(label); field.changed.connect(lambda path, k=key: self._set_image(k, path)); self.image_fields[key] = field; self.images_section.body_layout.addWidget(field)
        self.tile = QCheckBox("Tile background image"); self.images_section.body_layout.addWidget(self.tile)
        tile_row = QHBoxLayout(); tile_row.addWidget(QLabel("Tile size")); self.tile_size = QSlider(Qt.Orientation.Horizontal); self.tile_size.setRange(10, 200); tile_row.addWidget(self.tile_size, 1)
        self.tile_value = QLabel("100%"); tile_row.addWidget(self.tile_value); self.tile_widget = QWidget(); self.tile_widget.setLayout(tile_row); self.images_section.body_layout.addWidget(self.tile_widget)
        self.tile.toggled.connect(self._tile_changed); self.tile_size.valueChanged.connect(self._tile_changed)

    def _build_waistband(self) -> None:
        self.waistband_section = CollapsibleSection("Waistband"); self.controls_layout.addWidget(self.waistband_section)
        self.waistband_note = QLabel("Waistband color and image are edited in Colors and Images."); self.waistband_note.setObjectName("muted"); self.waistband_note.setWordWrap(True); self.waistband_section.body_layout.addWidget(self.waistband_note)

    def _build_logos(self) -> None:
        section = CollapsibleSection("Logos"); self.controls_layout.addWidget(section); self.logo_list = QListWidget(); self.logo_list.setMaximumHeight(150); section.body_layout.addWidget(self.logo_list)
        row = QHBoxLayout(); add = QPushButton("Add Logo"); remove = QPushButton("Remove Selected"); row.addWidget(add); row.addWidget(remove); section.body_layout.addLayout(row)
        add.clicked.connect(self._add_logo); remove.clicked.connect(self._remove_logo)

    def load_document(self, document: ProjectDocument) -> None:
        self._loading = True; self.document = document; g = document.generator
        self.garment.setCurrentText(document.garment); self._populate_templates(); self.template.setCurrentText(document.template_name)
        for key, field in self.color_fields.items(): field.set_color(str(g["colors"].get(key) or ""), emit=False)
        for key, field in self.image_fields.items(): field.set_path(g["images"].get(key), emit=False)
        self.tile.setChecked(bool(g["jerseyBackground"].get("tile", False))); self.tile_size.setValue(int(g["jerseyBackground"].get("tileScalePercent", 100)))
        self.uv_enabled.setChecked(bool(g["uvOverlay"].get("enabled", True))); self.uv_opacity.setValue(int(g["uvOverlay"].get("opacity", 45)))
        self._refresh_logo_list(); self._sync_garment(); self._tile_changed(); self._loading = False; self.schedule_preview()

    def _populate_templates(self) -> None:
        with QSignalBlocker(self.template):
            self.template.clear(); self.template.addItems(("Retro shorts", "Classic shorts", "Modern shorts") if self.garment.currentText() == "Shorts" else ("Retro U",))

    def _garment_changed(self, garment: str) -> None:
        if self._loading: return
        self.document.generator["garment"] = garment; self._populate_templates(); self._template_changed(self.template.currentText()); self._sync_garment(); self._changed()

    def _template_changed(self, value: str) -> None:
        if self._loading or not value: return
        self.document.generator["shortsTemplate" if self.garment.currentText() == "Shorts" else "jerseyCut"] = value; self._changed()

    def _sync_garment(self) -> None:
        shorts = self.garment.currentText() == "Shorts"
        for key in ("front_color","back_color","collar_background_color","left_arm_hole_trim_color","right_arm_hole_trim_color","collar_trim_color"):
            self.color_fields[key].setVisible(not shorts)
        self.color_fields["waistband_color"].setVisible(shorts); self.trim_section.setVisible(not shorts); self.waistband_section.setVisible(shorts)
        for key, field in self.image_fields.items(): field.setVisible((key in dict(SHORTS_IMAGE_ROWS)) if shorts else (key in dict(IMAGE_ROWS)))
        self.tile.setVisible(not shorts); self.tile_widget.setVisible(not shorts and self.tile.isChecked())

    def _set_color(self, key: str, value: str) -> None:
        if not self._loading: self.document.generator["colors"][key] = value; self._changed()

    def _set_image(self, key: str, path: Path | None) -> None:
        if not self._loading: self.document.generator["images"][key] = str(path) if path else None; self._changed()

    def _tile_changed(self, _value=None) -> None:
        self.tile_widget.setVisible(self.garment.currentText() == "Jersey" and self.tile.isChecked()); self.tile_value.setText(f"{self.tile_size.value()}%")
        if not self._loading:
            self.document.generator["jerseyBackground"].update(tile=self.tile.isChecked(), tileScalePercent=self.tile_size.value()); self._changed()

    def _uv_changed(self, _value=None) -> None:
        self.uv_value.setText(f"{self.uv_opacity.value()}%")
        if not self._loading:
            self.document.generator["uvOverlay"].update(enabled=self.uv_enabled.isChecked(), opacity=self.uv_opacity.value()); self._changed()

    def _add_logo(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Add logo", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path: return
        labels = list(LOGO_LABELS.values()); label, ok = QInputDialog.getItem(self, "Logo type", "Type", labels, 0, False)
        if not ok: return
        target = next(key for key, value in LOGO_LABELS.items() if value == label)
        self.document.generator["logos"].append({"path": path, "targetName": target, "offsetX": 0, "offsetY": 0, "scalePercent": 100, "scaleWidthPercent": 100, "scaleHeightPercent": 100, "stretchX": target == "wrap_across_front_back_logo"})
        self._refresh_logo_list(); self._changed()

    def _remove_logo(self) -> None:
        row = self.logo_list.currentRow()
        if row >= 0: self.document.generator["logos"].pop(row); self._refresh_logo_list(); self._changed()

    def _refresh_logo_list(self) -> None:
        self.logo_list.clear()
        for item in self.document.generator.get("logos", []):
            self.logo_list.addItem(f"{LOGO_LABELS.get(item.get('targetName'), item.get('targetName'))}  |  {Path(str(item.get('path'))).name}")

    def _changed(self) -> None: self.documentChanged.emit(); self.schedule_preview()
    def schedule_preview(self) -> None: self.timer.start()

    def render_preview(self) -> None:
        self._revision += 1; revision = self._revision; snapshot = ProjectDocument(self.document.clone_payload())
        self.preview_status.setText("Rendering 2048 x 2048 preview...")
        worker = Worker(lambda: (revision, pil_to_qimage(self.service.render_preview(snapshot))))
        worker.signals.finished.connect(self._preview_ready); worker.signals.failed.connect(lambda error: self._preview_failed(revision, error)); self.pool.start(worker)

    def _preview_ready(self, result: tuple[int, object]) -> None:
        revision, image = result
        if revision != self._revision: return
        self.preview.set_image(image); self.preview_status.setText(f"{self.document.garment} | {self.document.template_name} | 2048 x 2048")

    def _preview_failed(self, revision: int, error: str) -> None:
        if revision == self._revision: self.preview_status.setText(error); self.statusChanged.emit(error)
