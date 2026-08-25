from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QFrame, QGraphicsPixmapItem, QGraphicsScene,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)


def pil_to_qimage(image) -> QImage:
    rgba = image.convert("RGBA")
    return QImage(rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height,
                  rgba.width * 4, QImage.Format.Format_RGBA8888).copy()


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 14); layout.setSpacing(3)
        heading = QLabel(title); heading.setObjectName("pageTitle"); layout.addWidget(heading)
        if subtitle:
            caption = QLabel(subtitle); caption.setObjectName("pageSubtitle"); caption.setWordWrap(True); layout.addWidget(caption)


class CollapsibleSection(QWidget):
    def __init__(self, title: str, expanded: bool = False, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 8); layout.setSpacing(0)
        self.toggle = QToolButton(); self.toggle.setText(title); self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded); self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setObjectName("sectionHeader"); layout.addWidget(self.toggle)
        self.body = QFrame(); self.body.setObjectName("sectionBody")
        self.body_layout = QVBoxLayout(self.body); self.body_layout.setContentsMargins(10, 10, 10, 8); self.body_layout.setSpacing(8)
        self.body.setVisible(expanded); layout.addWidget(self.body)
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, checked: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.body.setVisible(checked)


class ColorField(QWidget):
    changed = Signal(str)

    def __init__(self, label: str, color: str = "", allow_none: bool = False, parent=None) -> None:
        super().__init__(parent); self.allow_none = allow_none
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(7)
        name = QLabel(label); name.setMinimumWidth(118); layout.addWidget(name)
        self.none_button = QToolButton(); self.none_button.setText("No color"); self.none_button.setCheckable(True)
        self.none_button.setVisible(allow_none); layout.addWidget(self.none_button)
        self.edit = QLineEdit(); self.edit.setMaximumWidth(90); layout.addWidget(self.edit)
        self.pick = QPushButton(); self.pick.setObjectName("colorSwatch"); self.pick.setFixedSize(34, 28); self.pick.setToolTip("Pick color")
        layout.addWidget(self.pick)
        self.pick.clicked.connect(self._pick); self.edit.editingFinished.connect(self._edited)
        self.none_button.toggled.connect(self._none_toggled); self.set_color(color, emit=False)

    def color(self) -> str: return "" if self.none_button.isChecked() else self.edit.text().strip().lower()

    def set_color(self, color: str, emit: bool = True) -> None:
        value = color.strip().lower(); is_none = self.allow_none and not value
        self.none_button.blockSignals(True); self.none_button.setChecked(is_none); self.none_button.blockSignals(False)
        self.edit.setEnabled(not is_none); self.pick.setEnabled(not is_none)
        self.edit.setText(value or "#ffffff"); self._update_swatch()
        if emit: self.changed.emit(self.color())

    def _pick(self) -> None:
        selected = QColorDialog.getColor(QColor(self.edit.text()), self, "Pick color")
        if selected.isValid(): self.set_color(selected.name())

    def _edited(self) -> None:
        value = self.edit.text().strip()
        if not value.startswith("#"): value = "#" + value
        color = QColor(value)
        if color.isValid(): self.set_color(color.name())
        else: self.set_color("#ffffff")

    def _none_toggled(self, checked: bool) -> None:
        self.edit.setEnabled(not checked); self.pick.setEnabled(not checked); self._update_swatch(); self.changed.emit(self.color())

    def _update_swatch(self) -> None:
        color = "transparent" if self.none_button.isChecked() else self.edit.text()
        self.pick.setStyleSheet(f"background:{color}; border:1px solid #8b9299; border-radius:4px;")


class FileField(QWidget):
    changed = Signal(object)

    def __init__(self, label: str, filters: str = "Images (*.png *.jpg *.jpeg *.bmp *.webp *.dds *.psd);;All files (*.*)", parent=None) -> None:
        super().__init__(parent); self.filters = filters; self.path: Path | None = None
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        name = QLabel(label); name.setMinimumWidth(150); layout.addWidget(name)
        self.file_name = QLabel("None"); self.file_name.setObjectName("muted"); self.file_name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.file_name)
        browse = QToolButton(); browse.setText("..."); browse.setToolTip("Choose file"); layout.addWidget(browse)
        clear = QToolButton(); clear.setText("x"); clear.setToolTip("Clear image"); layout.addWidget(clear)
        browse.clicked.connect(self._browse); clear.clicked.connect(lambda: self.set_path(None))

    def set_path(self, path: Path | str | None, emit: bool = True) -> None:
        self.path = Path(path) if path else None
        self.file_name.setText(self.path.name if self.path else "None"); self.file_name.setToolTip(str(self.path or ""))
        if emit: self.changed.emit(self.path)

    def _browse(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Choose file", "", self.filters)
        if selected: self.set_path(Path(selected))


class ImageView(QGraphicsView):
    pointClicked = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent); self.setScene(QGraphicsScene(self)); self.item = QGraphicsPixmapItem(); self.scene().addItem(self.item)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag); self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter); self.setBackgroundBrush(QColor("#17191c"))
        self._middle_pan = False; self._pan_start = QPoint(); self._has_image = False

    def set_image(self, image: QImage | QPixmap) -> None:
        pixmap = image if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        self.item.setPixmap(pixmap); self.scene().setSceneRect(self.item.boundingRect()); self._has_image = not pixmap.isNull(); self.fit_image()

    def load_path(self, path: Path) -> bool:
        image = QImage(str(path))
        if image.isNull(): return False
        self.set_image(image); return True

    def fit_image(self) -> None:
        if self._has_image: self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15; self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_pan = True; self._pan_start = event.position().toPoint(); self.setCursor(Qt.CursorShape.ClosedHandCursor); event.accept(); return
        if event.button() == Qt.MouseButton.LeftButton and self._has_image:
            point = self.mapToScene(event.position().toPoint()); self.pointClicked.emit(point.x(), point.y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._middle_pan:
            delta = event.position().toPoint() - self._pan_start; self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y()); event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_pan = False; self.setCursor(Qt.CursorShape.ArrowCursor); event.accept(); return
        super().mouseReleaseEvent(event)

