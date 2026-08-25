from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__
from .document import ProjectDocument
from .pages.advanced_pages import IffTexturesPage, RdatEditorPage, TemplateEditorPage
from .pages.creator_pages import LogoCreatorPage, TrimCreatorPage, TrimPathPage
from .pages.generator_page import GeneratorPage
from .pages.number_tweak_pages import NumberEditorPage, TweakEditorPage
from .pages.texture_page import TextureCreatorPage
from .services import GeneratorService


PROJECT_FILTER = "NBA 2K Modder Project (*.nba2kproject.json *.json);;JSON (*.json)"


class MainWindow(QMainWindow):
    def __init__(self, document: ProjectDocument | None = None, parent=None) -> None:
        super().__init__(parent)
        self.document = document or ProjectDocument()
        self.service = GeneratorService()
        self.dirty = False
        self.settings = QSettings("NBA2KModTools", "JerseyModder")
        self.setWindowTitle(__app_name__)
        self.setMinimumSize(980, 680)
        self.resize(self.settings.value("windowSize", QSize(1440, 900)))
        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        shell = QWidget()
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(shell)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 14)
        side.setSpacing(2)
        brand = QLabel("NBA 2K\nJersey Modder")
        brand.setObjectName("brand")
        side.addWidget(brand)
        subtitle = QLabel("Uniform texture workspace")
        subtitle.setObjectName("brandSubtle")
        side.addWidget(subtitle)
        side.addSpacing(16)

        self.stack = QStackedWidget()
        self.pages = [
            ("Generator", GeneratorPage(self.document, self.service)),
            ("Logo Creator", LogoCreatorPage(self.document)),
            ("Trim Creator", TrimCreatorPage(self.document)),
            ("Trim Path Lab", TrimPathPage(self.document, self.service)),
            ("Number Editor", NumberEditorPage()),
            ("Tweak Editor", TweakEditorPage()),
            ("Texture Creator", TextureCreatorPage(self.document, self.service)),
            ("IFF Textures", IffTexturesPage()),
            ("RDAT Editor", RdatEditorPage()),
            ("Template Editor", TemplateEditorPage()),
        ]
        self.page_buttons = QButtonGroup(self)
        self.page_buttons.setExclusive(True)
        for index, (name, page) in enumerate(self.pages):
            if index == 7:
                side.addSpacing(10)
                advanced = QLabel("ADVANCED")
                advanced.setObjectName("brandSubtle")
                side.addWidget(advanced)
                side.addSpacing(3)
            button = QPushButton(name)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, i=index: self._select_page(i))
            self.page_buttons.addButton(button, index)
            side.addWidget(button)
            self.stack.addWidget(page)
            if hasattr(page, "statusChanged"):
                page.statusChanged.connect(self._show_status)
            if hasattr(page, "documentChanged"):
                page.documentChanged.connect(lambda p=page: self._document_changed(p))
        side.addStretch(1)
        version = QLabel("Modern desktop edition")
        version.setObjectName("brandSubtle")
        side.addWidget(version)
        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.pages[0][1].webEditorRequested.connect(self._open_classic_workspace)
        self.pages[0][1].blenderRequested.connect(self.open_blender_preview)
        self.page_buttons.button(0).setChecked(True)
        self._select_page(0)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self._action(file_menu, "&New Project", self.new_project, QKeySequence.StandardKey.New)
        self._action(file_menu, "&Open Project...", self.open_project, QKeySequence.StandardKey.Open)
        file_menu.addSeparator()
        self._action(file_menu, "&Save Project", self.save_project, QKeySequence.StandardKey.Save)
        self._action(file_menu, "Save Project &As...", self.save_project_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        self._action(file_menu, "Export Package As...", self.export_package)
        file_menu.addSeparator()
        self._action(file_menu, "E&xit", self.close, QKeySequence.StandardKey.Quit)

        preview_menu = self.menuBar().addMenu("&Preview")
        self._action(preview_menu, "Open Blender Preview", self.open_blender_preview)
        self._action(preview_menu, "Open Classic Web Workspace", self._open_classic_workspace)

        advanced_menu = self.menuBar().addMenu("&Advanced")
        for index in (7, 8, 9):
            self._action(advanced_menu, self.pages[index][0], lambda checked=False, i=index: self._select_page(i))

    def _action(self, menu, text, callback, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        button = self.page_buttons.button(index)
        if button:
            button.setChecked(True)
        page = self.pages[index][1]
        if hasattr(page, "load_document"):
            page.load_document(self.document)

    def _document_changed(self, source) -> None:
        self.dirty = True
        self._update_title()
        for _name, page in self.pages:
            if page is not source and isinstance(page, (GeneratorPage, TextureCreatorPage, TrimPathPage)):
                if isinstance(page, GeneratorPage):
                    page.load_document(self.document)
        self._show_status("Project updated")

    def _replace_document(self, document: ProjectDocument) -> None:
        self.document = document
        self.dirty = False
        for _name, page in self.pages:
            if hasattr(page, "load_document"):
                page.load_document(document)
        self._update_title()

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._replace_document(ProjectDocument())
        self._select_page(0)
        self._show_status("Created a new project")

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", PROJECT_FILTER)
        if not path:
            return
        try:
            self._replace_document(ProjectDocument.load(Path(path)))
            self._select_page(0)
            self._show_status(f"Opened {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self, "Open project", str(exc))

    def save_project(self) -> bool:
        if self.document.path is None:
            return self.save_project_as()
        try:
            path = self.document.save()
            self.dirty = False
            self._update_title()
            self._show_status(f"Saved {path.name}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save project", str(exc))
            return False

    def save_project_as(self) -> bool:
        suggested = self.document.path.name if self.document.path else "uniform.nba2kproject.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save project", suggested, PROJECT_FILTER)
        if not path:
            return False
        try:
            saved = self.document.save(Path(path))
            self.dirty = False
            self._update_title()
            self._show_status(f"Saved {saved.name}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save project", str(exc))
            return False

    def export_package(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose export package location")
        if not folder:
            return
        try:
            package = self.service.export_package(self.document, Path(folder))
            self._show_status(f"Exported package to {package.name}")
            QMessageBox.information(self, "Export complete", f"Package created at:\n{package}")
        except Exception as exc:
            QMessageBox.critical(self, "Export package", str(exc))

    def open_blender_preview(self) -> None:
        blender = self.service.find_blender()
        if blender is None:
            selected, _ = QFileDialog.getOpenFileName(self, "Choose blender.exe", "", "Blender (blender.exe);;All files (*.*)")
            if not selected:
                return
            blender = Path(selected)
        try:
            model, color, normal, settings = self.service.prepare_blender_preview(self.document)
            subprocess.Popen(
                [str(blender), str(model), "--python", str(self.service.blender_script), "--", str(color), str(normal), "0.35", str(settings)],
                cwd=str(self.service.project_root),
            )
            self._show_status("Opened Blender uniform preview")
        except Exception as exc:
            QMessageBox.critical(self, "Blender preview", str(exc))

    def _open_classic_workspace(self) -> None:
        answer = QMessageBox.question(
            self,
            "Classic web workspace",
            "The browser-based layer editor is still hosted by the classic workspace during this conversion. Open it in a separate window?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        bridge = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "modern_bridge_project.json"
        bridge.parent.mkdir(parents=True, exist_ok=True)
        bridge.write_text(json.dumps(self.document.payload, indent=2), encoding="utf-8")
        environment = os.environ.copy()
        environment["NBA2K_BRIDGE_PROJECT"] = str(bridge)
        environment["NBA2K_BRIDGE_OPEN_WEB"] = "1"
        args = [sys.executable, str(self.service.project_root / "main.py"), "--legacy"]
        subprocess.Popen(args, cwd=str(self.service.project_root), env=environment)
        self._show_status("Opened classic workspace for the browser editor")

    def _show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)

    def _update_title(self) -> None:
        name = self.document.path.name if self.document.path else "Untitled project"
        marker = " *" if self.dirty else ""
        self.setWindowTitle(f"{name}{marker} - {__app_name__}")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved changes",
            "Save the current project before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if result == QMessageBox.StandardButton.Save:
            return self.save_project()
        return result == QMessageBox.StandardButton.Discard

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        self.settings.setValue("windowSize", self.size())
        event.accept()
