from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox,QFileDialog,QHBoxLayout,QLabel,QPushButton,QSlider,QVBoxLayout
from ...dds import save_bc1_dds
from ..services import GeneratorService
from ..widgets import ImageView,PageHeader,pil_to_qimage
from .base import FeaturePage

class TextureCreatorPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,document,service:GeneratorService,parent=None):
        super().__init__(parent);self.document=document;self.service=service;self.image=None;self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(140);self.timer.timeout.connect(self.refresh)
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Texture Creator","Generate color, region, and normal textures from the current project."))
        row=QHBoxLayout();row.addWidget(QLabel("Texture"));self.kind=QComboBox();self.kind.addItems(("Color Texture","Region Texture","Normal Map"));row.addWidget(self.kind);row.addWidget(QLabel("Logo strength"));self.strength=QSlider(Qt.Orientation.Horizontal);self.strength.setRange(0,100);self.strength.setValue(15);row.addWidget(self.strength,1);self.strength_value=QLabel("15%");row.addWidget(self.strength_value);root.addLayout(row)
        buttons=QHBoxLayout();create=QPushButton("Update Preview");png=QPushButton("Save PNG As");dds=QPushButton("Save DDS BC1 As");psd=QPushButton("Save Layered PSD As");[buttons.addWidget(x) for x in (create,png,dds,psd)];root.addLayout(buttons)
        self.preview=ImageView();root.addWidget(self.preview,1);create.clicked.connect(self.refresh);self.kind.currentTextChanged.connect(lambda:self.refresh());self.strength.valueChanged.connect(self._strength);png.clicked.connect(self._save_png);dds.clicked.connect(self._save_dds);psd.clicked.connect(self._save_psd)
    def load_document(self,d):self.document=d;self.refresh()
    def _strength(self,v):self.strength_value.setText(f"{v}%");self.timer.start()
    def refresh(self):
        try:self.image=self.service.render_texture(self.document,self.kind.currentText(),self.strength.value());self.preview.set_image(pil_to_qimage(self.image));self.statusChanged.emit(f"Updated {self.kind.currentText().lower()} preview.")
        except Exception as e:self.image=None;self.show_error("Texture Creator",e)
    def _save_png(self):
        if self.image is None:self.refresh()
        if self.image is None:return
        p,_=QFileDialog.getSaveFileName(self,"Save texture PNG","texture.png","PNG (*.png)");self.image.save(p,"PNG",compress_level=1) if p else None
    def _save_dds(self):
        if self.image is None:self.refresh()
        if self.image is None:return
        p,_=QFileDialog.getSaveFileName(self,"Save DDS BC1","texture.dds","DDS (*.dds)");save_bc1_dds(self.image,Path(p)) if p else None
    def _save_psd(self):
        p,_=QFileDialog.getSaveFileName(self,"Save layered PSD","texture.psd","PSD (*.psd)")
        if p:
            try:self.service.save_psd(self.document,Path(p))
            except Exception as e:self.show_error("Texture Creator",e)
