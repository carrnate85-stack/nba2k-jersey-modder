from __future__ import annotations

from pathlib import Path
import tempfile

from PIL import Image
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QVBoxLayout,
    QWidget,
)

from ...app import _recolor_font_image
from ...font_iff import extract_number_sheet_from_font_iff, inspect_font_number_texture, split_number_sheet_digits, write_number_sheet_to_font_iff
from ...tweak_iff import inspect_front_number_tweak, write_front_number_tweak
from ..widgets import ImageView, PageHeader, pil_to_qimage
from .base import FeaturePage


class NumberEditorPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.source=None;self.info=None;self.original=[];self.current=None
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Number Editor","Import a font IFF, recolor its fill and outline, then save a modified copy."))
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1);self.preview=ImageView();split.addWidget(self.preview)
        panel=QWidget();panel_layout=QVBoxLayout(panel);panel_layout.setContentsMargins(8,0,0,0)
        row=QHBoxLayout();load=QPushButton("Import Font IFF");save=QPushButton("Save Font IFF As");restore=QPushButton("Restore Original");row.addWidget(load);row.addWidget(save);row.addWidget(restore);panel_layout.addLayout(row);load.clicked.connect(self._load);save.clicked.connect(self._save);restore.clicked.connect(self._restore)
        controls=QFormLayout();panel_layout.addLayout(controls)
        self.fill_none=QCheckBox("No change");self.fill_none.setChecked(True);self.fill=QPushButton("#ffffff");controls.addRow("Fill",_row(self.fill_none,self.fill))
        self.outline_none=QCheckBox("No change");self.outline_none.setChecked(True);self.outline=QPushButton("#000000");controls.addRow("Outline",_row(self.outline_none,self.outline))
        self.edge=QSlider(Qt.Orientation.Horizontal);self.edge.setRange(0,100);self.edge.setValue(0);self.edge_value=QLabel("0%");controls.addRow("Edge protection",_row(self.edge,self.edge_value))
        self.thickness=QSlider(Qt.Orientation.Horizontal);self.thickness.setRange(0,20);self.thickness_value=QLabel("0 px");controls.addRow("Outline thickness",_row(self.thickness,self.thickness_value))
        apply=QPushButton("Apply Recolor");apply.setObjectName("primaryBar");apply.clicked.connect(self._apply);panel_layout.addWidget(apply);panel_layout.addStretch(1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame);scroll.setWidget(panel);split.addWidget(scroll);split.setSizes([720,420])
        self.fill.clicked.connect(lambda:self._pick(self.fill,self.fill_none));self.outline.clicked.connect(lambda:self._pick(self.outline,self.outline_none));self.edge.valueChanged.connect(lambda v:self.edge_value.setText(f"{v}%"));self.thickness.valueChanged.connect(lambda v:self.thickness_value.setText(f"{v} px"))
    def _load(self):
        p,_=QFileDialog.getOpenFileName(self,"Import font IFF","","Font IFF (*font*.iff *.iff);;IFF (*.iff)")
        if not p:return
        try:
            self.source=Path(p);self.info=inspect_font_number_texture(p);sheet=extract_number_sheet_from_font_iff(p);self.original=split_number_sheet_digits(sheet);self.current=sheet;self.preview.set_image(pil_to_qimage(sheet));self.statusChanged.emit(f"Loaded {self.source.name} ({sheet.width} x {sheet.height}).")
        except Exception as e:self.show_error("Number Editor",e)
    def _pick(self,button,checkbox):
        color=QColorDialog.getColor(parent=self)
        if color.isValid():button.setText(color.name());button.setStyleSheet(f"background:{color.name()};");checkbox.setChecked(False)
    def _apply(self):
        if not self.original or not self.info:return
        outline=None if self.outline_none.isChecked() else _rgb(self.outline.text());fill=None if self.fill_none.isChecked() else _rgb(self.fill.text())
        digits=[_recolor_font_image(image,outline,fill,edge_protection=self.edge.value()/100,outline_thickness=self.thickness.value()) for image in self.original]
        sheet=Image.new("RGBA",(self.info.width,self.info.height),(0,0,0,0));cell=self.info.cell_width
        for i,image in enumerate(digits):sheet.alpha_composite(image,(i*cell,0))
        self.current=sheet;self.preview.set_image(pil_to_qimage(sheet));self.statusChanged.emit("Recolor preview updated.")
    def _restore(self):
        if not self.original or not self.info:return
        sheet=Image.new("RGBA",(self.info.width,self.info.height),(0,0,0,0))
        for i,image in enumerate(self.original):sheet.alpha_composite(image,(i*self.info.cell_width,0))
        self.current=sheet;self.preview.set_image(pil_to_qimage(sheet))
    def _save(self):
        if not self.source or self.current is None:return
        p,_=QFileDialog.getSaveFileName(self,"Save font IFF as",self.source.stem+"_recolor.iff","IFF (*.iff)")
        if not p:return
        try:write_number_sheet_to_font_iff(self.source,p,self.current);self.statusChanged.emit(f"Saved {Path(p).name}.")
        except Exception as e:self.show_error("Number Editor",e)


class TweakEditorPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.source=None;self.info=None
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Tweak Editor","Adjust front jersey number position and size in clothing resource tweak IFF files."))
        row=QHBoxLayout();load=QPushButton("Import Tweak IFF");save=QPushButton("Save Tweak IFF As");row.addWidget(load);row.addWidget(save);row.addStretch();root.addLayout(row);load.clicked.connect(self._load);save.clicked.connect(self._save)
        form=QFormLayout();root.addLayout(form);self.values={}
        for key,label in (("x","X position - left / right"),("y","Y position - down / up"),("width","Width - smaller / bigger"),("height","Height - smaller / bigger")):
            value=QDoubleSpinBox();value.setDecimals(6);value.setSingleStep(.01);self.values[key]=value;form.addRow(label,value)
        self.lock=QCheckBox("Lock width and height");form.addRow("",self.lock);self.values["width"].valueChanged.connect(self._lock_width);self.values["height"].valueChanged.connect(self._lock_height);self._syncing=False;root.addStretch()
    def _load(self):
        p,_=QFileDialog.getOpenFileName(self,"Import tweak IFF","","Tweak IFF (*tweak*.iff *.iff);;IFF (*.iff)")
        if not p:return
        try:
            self.source=Path(p);self.info=inspect_front_number_tweak(p)
            for key,box in self.values.items():scalar=getattr(self.info,key);box.setRange(scalar.minimum,scalar.maximum);box.setValue(scalar.value)
            self.statusChanged.emit(f"Loaded {self.source.name}.")
        except Exception as e:self.show_error("Tweak Editor",e)
    def _lock_width(self,value):
        if self.lock.isChecked() and not self._syncing:self._syncing=True;self.values["height"].setValue(value);self._syncing=False
    def _lock_height(self,value):
        if self.lock.isChecked() and not self._syncing:self._syncing=True;self.values["width"].setValue(value);self._syncing=False
    def _save(self):
        if not self.source:return
        p,_=QFileDialog.getSaveFileName(self,"Save tweak IFF as",self.source.stem+"_edited.iff","Tweak IFF (*.iff)")
        if not p:return
        try:write_front_number_tweak(self.source,p,**{k:v.value() for k,v in self.values.items()});self.statusChanged.emit(f"Saved {Path(p).name}.")
        except Exception as e:self.show_error("Tweak Editor",e)


def _row(*widgets):
    widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0)
    for item in widgets:layout.addWidget(item)
    return widget
def _rgb(value):
    value=value.lstrip("#");return tuple(int(value[i:i+2],16) for i in (0,2,4))
