from __future__ import annotations

import math
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ...generator import remove_detected_background, remove_image_background, upscale_logo_image
from ...trim_creator import correct_trim_strip, create_trim_strip_from_line
from ..document import ProjectDocument
from ..services import GeneratorService
from ..widgets import FileField, ImageView, PageHeader, pil_to_qimage
from .base import FeaturePage


WORK_DIR = Path(tempfile.gettempdir()) / "nba2k_jersey_modder" / "modern_creators"
LOGO_TYPES = (
    ("Center Chest Logo", "front_center_chest_logo"), ("Left Chest Logo", "front_left_chest_logo"),
    ("Right Chest Logo", "front_right_chest_logo"), ("Front Wordmark", "front_wordmark"),
    ("Wrap Logo", "wrap_across_front_back_logo"), ("Back Neck Logo", "back_neck_logo"),
    ("Back Center Logo", "back_center_logo"), ("Belt Buckle Logo", "shorts_belt_buckle_logo"),
)


class LogoCreatorPage(FeaturePage):
    documentChanged = Signal(); statusChanged = Signal(str)

    def __init__(self, document: ProjectDocument, parent=None) -> None:
        super().__init__(parent); self.document = document; self.reference: Path | None = None; self.output: Path | None = None; self.points = []; self.staged = []
        root = QVBoxLayout(self); root.setContentsMargins(18, 16, 18, 16); root.addWidget(PageHeader("Logo Creator", "Select, clean, upscale, and stage logos before placing them on a uniform."))
        split = QSplitter(Qt.Orientation.Horizontal); root.addWidget(split, 1)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0,0,8,0); self.reference_field = FileField("Reference image"); self.reference_field.changed.connect(self._load); ll.addWidget(self.reference_field)
        self.reference_view = ImageView(); self.reference_view.pointClicked.connect(self._point); ll.addWidget(self.reference_view, 1)
        self.selection = QLabel("Click two points to define a box selection."); self.selection.setObjectName("muted"); ll.addWidget(self.selection); split.addWidget(left)
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(8,0,0,0)
        self.preview = ImageView(); self.preview.setMinimumHeight(260); rl.addWidget(self.preview, 1)
        row = QHBoxLayout(); row.addWidget(QLabel("Logo type")); self.logo_type = QComboBox(); self.logo_type.addItems([label for label,_ in LOGO_TYPES]); row.addWidget(self.logo_type,1); rl.addLayout(row)
        self.auto = QCheckBox("Auto background"); self.white = QCheckBox("Remove white"); self.black = QCheckBox("Remove black"); self.outside = QCheckBox("Outside only"); self.outside.setChecked(True)
        checks=QHBoxLayout(); [checks.addWidget(x) for x in (self.auto,self.white,self.black,self.outside)]; rl.addLayout(checks)
        row=QHBoxLayout(); row.addWidget(QLabel("Tolerance")); self.tolerance=QSlider(Qt.Orientation.Horizontal); self.tolerance.setRange(0,255); self.tolerance.setValue(32); row.addWidget(self.tolerance,1); rl.addLayout(row)
        row=QHBoxLayout(); row.addWidget(QLabel("Upscale")); self.upscale=QComboBox(); self.upscale.addItems(("1x","2x","4x")); self.upscale.setCurrentText("4x"); row.addWidget(self.upscale,1); rl.addLayout(row)
        refresh=QPushButton("Refresh Logo Preview"); refresh.clicked.connect(self._create); rl.addWidget(refresh)
        buttons=QHBoxLayout(); stage=QPushButton("Stage Current Logo"); send=QPushButton("Send Staged to Generator"); buttons.addWidget(stage); buttons.addWidget(send); rl.addLayout(buttons); stage.clicked.connect(self._stage); send.clicked.connect(self._send)
        self.list=QListWidget(); self.list.setMaximumHeight(150); rl.addWidget(self.list); clear=QPushButton("Clear Staged"); clear.clicked.connect(self._clear); rl.addWidget(clear); split.addWidget(_scrollable(right)); split.setSizes([650,480])

    def load_document(self, document): self.document=document
    def _load(self,path):
        self.reference=path; self.points=[]
        if path and self.reference_view.load_path(path): self.selection.setText("Click the top-left and bottom-right of the logo.")
    def _point(self,x,y):
        if not self.reference: return
        self.points.append((round(x),round(y))); self.points=self.points[-2:]
        self.selection.setText("First point selected." if len(self.points)==1 else f"Selection: {self.points[0]} to {self.points[1]}")
        if len(self.points)==2:self._create()
    def _create(self):
        if not self.reference:return
        with Image.open(self.reference) as opened: image=opened.convert("RGBA")
        if len(self.points)==2:
            x1,y1=self.points[0]; x2,y2=self.points[1]; box=(max(0,min(x1,x2)),max(0,min(y1,y2)),min(image.width,max(x1,x2)),min(image.height,max(y1,y2)))
            if box[2]>box[0] and box[3]>box[1]: image=image.crop(box)
        if self.auto.isChecked(): image=remove_detected_background(image,tolerance=self.tolerance.value())
        image=remove_image_background(image,remove_white=self.white.isChecked(),remove_black=self.black.isChecked(),outside_only=self.outside.isChecked(),tolerance=self.tolerance.value())
        factor=int(self.upscale.currentText()[0]); image=upscale_logo_image(image,scale_factor=factor,sharpen=True) if factor>1 else image
        WORK_DIR.mkdir(parents=True,exist_ok=True); self.output=WORK_DIR/"current_logo.png"; image.save(self.output); self.preview.set_image(pil_to_qimage(image))
    def _stage(self):
        if not self.output:self._create()
        if not self.output:return
        key=dict(LOGO_TYPES)[self.logo_type.currentText()]; path=WORK_DIR/f"staged_logo_{len(self.staged)+1}.png"; path.write_bytes(self.output.read_bytes()); self.staged.append((key,path)); self.list.addItem(f"{self.logo_type.currentText()} | {path.name}")
    def _send(self):
        for key,path in self.staged:
            if key=="front_wordmark": self.document.generator["images"]["front_wordmark_image"]=str(path)
            else:self.document.generator["logos"].append({"path":str(path),"targetName":key,"offsetX":0,"offsetY":0,"scalePercent":100,"scaleWidthPercent":100,"scaleHeightPercent":100,"stretchX":key=="wrap_across_front_back_logo"})
        if self.staged:self.documentChanged.emit(); self.statusChanged.emit(f"Sent {len(self.staged)} staged logo(s) to Generator.")
    def _clear(self):self.staged=[];self.list.clear()


class TrimCreatorPage(FeaturePage):
    documentChanged=Signal();statusChanged=Signal(str)
    def __init__(self,document,parent=None):
        super().__init__(parent);self.document=document;self.reference=None;self.points=[];self.current=None;self.staged=[]
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Trim Creator","Sample a straight cross-section from a mockup and rebuild it as a clean trim strip."))
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1);left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,8,0)
        self.file=FileField("Jersey mockup");self.file.changed.connect(self._load);ll.addWidget(self.file);self.view=ImageView();self.view.pointClicked.connect(self._point);ll.addWidget(self.view,1);self.pick_status=QLabel("Choose a mockup, then click two points across the trim.");self.pick_status.setObjectName("muted");ll.addWidget(self.pick_status);split.addWidget(left)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(8,0,0,0);self.preview=ImageView();self.preview.setMinimumHeight(220);rl.addWidget(self.preview,1)
        row=QHBoxLayout();row.addWidget(QLabel("Trim type"));self.target=QComboBox();self.target.addItems(("Collar Trim","Left Arm Hole Trim","Right Arm Hole Trim","Waistband"));row.addWidget(self.target,1);rl.addLayout(row)
        crop=QHBoxLayout();crop.addWidget(QLabel("Crop top"));self.top=QSpinBox();self.top.setRange(-64,64);crop.addWidget(self.top);crop.addWidget(QLabel("Crop bottom"));self.bottom=QSpinBox();self.bottom.setRange(-64,64);crop.addWidget(self.bottom);rl.addLayout(crop)
        self.sharpen=QCheckBox("Correct gaps and even lines");self.sharpen.setChecked(True);rl.addWidget(self.sharpen);create=QPushButton("Create Trim Preview");create.clicked.connect(self._create);rl.addWidget(create)
        actions=QHBoxLayout();stage=QPushButton("Stage Current Trim");send=QPushButton("Send Staged to Generator");actions.addWidget(stage);actions.addWidget(send);rl.addLayout(actions);stage.clicked.connect(self._stage);send.clicked.connect(self._send)
        self.list=QListWidget();self.list.setMaximumHeight(145);rl.addWidget(self.list);buttons=QHBoxLayout();save=QPushButton("Save Trim PNG As");remove=QPushButton("Remove Selected");buttons.addWidget(save);buttons.addWidget(remove);rl.addLayout(buttons);save.clicked.connect(self._save);remove.clicked.connect(self._remove);split.addWidget(_scrollable(right));split.setSizes([650,480])
    def load_document(self,d):self.document=d
    def _load(self,p):self.reference=p;self.points=[];self.view.load_path(p) if p else None
    def _point(self,x,y):
        self.points.append((round(x),round(y)));self.points=self.points[-2:];self.pick_status.setText("First point selected." if len(self.points)==1 else f"Line: {self.points[0]} to {self.points[1]}")
        if len(self.points)==2:self._create()
    def _create(self):
        if not self.reference or len(self.points)!=2:return
        WORK_DIR.mkdir(parents=True,exist_ok=True);path=WORK_DIR/"current_trim.png";create_trim_strip_from_line(self.reference,path,*self.points,crop_top=self.top.value(),crop_bottom=self.bottom.value())
        if self.sharpen.isChecked():correct_trim_strip(path,path,max_gap=3)
        self.current=path;self.preview.load_path(path)
    def _stage(self):
        if not self.current:self._create()
        if not self.current:return
        path=WORK_DIR/f"staged_trim_{len(self.staged)+1}.png";path.write_bytes(self.current.read_bytes());target=self.target.currentText();self.staged.append((target,path));self.list.addItem(f"{target} | {path.name}")
    def _send(self):
        keys={"Collar Trim":"collar_trim_image","Left Arm Hole Trim":"left_arm_hole_trim_image","Right Arm Hole Trim":"right_arm_hole_trim_image","Waistband":"waistband_image"}
        for target,path in self.staged:self.document.generator["images"][keys[target]]=str(path)
        if self.staged:self.documentChanged.emit();self.statusChanged.emit(f"Sent {len(self.staged)} staged trim(s) to Generator.")
    def _save(self):
        if not self.current:return
        p,_=QFileDialog.getSaveFileName(self,"Save trim PNG","trim.png","PNG (*.png)");Path(p).write_bytes(self.current.read_bytes()) if p else None
    def _remove(self):
        row=self.list.currentRow()
        if row>=0:self.staged.pop(row);self.list.takeItem(row)


class TrimPathPage(FeaturePage):
    documentChanged=Signal();statusChanged=Signal(str)
    def __init__(self,document,service:GeneratorService,parent=None):
        super().__init__(parent);self.document=document;self.service=service;self.pattern=None;self.points=[]
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Trim Path Lab","Draw multi-point trim paths over the active generator texture."))
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1);left=QWidget();ll=QVBoxLayout(left);ll.setContentsMargins(0,0,8,0);self.view=ImageView();self.view.pointClicked.connect(self._point);ll.addWidget(self.view,1);self.readout=QLabel("Click points on the texture. Right-side controls finish the path.");self.readout.setObjectName("muted");ll.addWidget(self.readout);split.addWidget(left)
        right=QWidget();rl=QVBoxLayout(right);rl.setContentsMargins(8,0,0,0);self.pattern_field=FileField("Trim pattern");self.pattern_field.changed.connect(lambda p:setattr(self,"pattern",p));rl.addWidget(self.pattern_field)
        row=QHBoxLayout();row.addWidget(QLabel("Path shape"));self.shape=QComboBox();self.shape.addItems(("Straight segments","Smooth curve","T shape"));row.addWidget(self.shape,1);rl.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel("Trim width"));self.width=QSpinBox();self.width.setRange(2,300);self.width.setValue(64);row.addWidget(self.width);rl.addLayout(row)
        self.mirror_panel=QCheckBox("Create opposite-panel copy");self.mirror_x=QCheckBox("Create X-axis mirror");rl.addWidget(self.mirror_panel);rl.addWidget(self.mirror_x)
        finish=QPushButton("Finish Path and Send to Generator");finish.clicked.connect(self._finish);rl.addWidget(finish);undo=QPushButton("Undo Point");undo.clicked.connect(self._undo);clear=QPushButton("Clear Points");clear.clicked.connect(self._clear);rl.addWidget(undo);rl.addWidget(clear)
        self.layers=QListWidget();rl.addWidget(QLabel("Generator trim paths"));rl.addWidget(self.layers,1);remove=QPushButton("Remove Selected Layer");remove.clicked.connect(self._remove);rl.addWidget(remove);split.addWidget(_scrollable(right));split.setSizes([760,360]);self.load_document(document)
    def load_document(self,d):self.document=d;self._render_background();self._refresh()
    def _render_background(self):
        try:self.view.set_image(pil_to_qimage(self.service.render_preview(self.document)))
        except Exception as e:self.show_error("Trim Path Lab",e)
    def _point(self,x,y):
        if not(0<=x<=2048 and 0<=y<=2048):return
        if self.shape.currentText()=="T shape" and len(self.points)>=3:self.points=[]
        self.points.append((round(x),round(y)))
        angle="--"
        if len(self.points)>1:
            a,b=self.points[-2:];angle=f"{math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])):.1f} degrees"
        self.readout.setText(f"Points: {len(self.points)} | Current angle: {angle}")
    def _finish(self):
        needed=3 if self.shape.currentText()=="T shape" else 2
        if not self.pattern or len(self.points)<needed:self.show_info("Trim Path Lab",f"Choose a trim and select at least {needed} points.");return
        WORK_DIR.mkdir(parents=True,exist_ok=True);base=Image.new("RGBA",(2048,2048),(0,0,0,0));pattern=Image.open(self.pattern).convert("RGBA")
        segments=[(self.points[i],self.points[i+1]) for i in range(len(self.points)-1)]
        if self.shape.currentText()=="T shape":segments=[(self.points[0],self.points[1]),(self.points[2],self.points[1])]
        for start,end in segments:_stamp_pattern_segment(base,pattern,start,end,self.width.value())
        paths=[base]
        if self.mirror_panel.isChecked():paths.append(base.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
        if self.mirror_x.isChecked():paths.append(base.transpose(Image.Transpose.FLIP_TOP_BOTTOM))
        for image in paths:
            index=len(self.document.generator["trimPathLayers"])+1;path=WORK_DIR/f"trim_path_{index}.png";image.save(path)
            self.document.generator["trimPathLayers"].append({"name":f"Trim Path {index}","path":str(path),"garment":self.document.garment,"templateName":self.document.template_name,"x":0,"y":0,"width":2048,"height":2048,"rotationDegrees":0,"defaultX":0,"defaultY":0,"defaultWidth":2048,"defaultHeight":2048})
        self.points=[];self._refresh();self.documentChanged.emit();self.statusChanged.emit(f"Added {len(paths)} trim path layer(s).")
    def _undo(self):
        if self.points:self.points.pop();self.readout.setText(f"Points: {len(self.points)}")
    def _clear(self):self.points=[];self.readout.setText("Points cleared.")
    def _refresh(self):
        self.layers.clear()
        for item in self.document.generator.get("trimPathLayers",[]):self.layers.addItem(f"{item.get('name')} | {item.get('garment')}")
    def _remove(self):
        row=self.layers.currentRow()
        if row>=0:self.document.generator["trimPathLayers"].pop(row);self._refresh();self.documentChanged.emit()


def _stamp_pattern_segment(canvas,pattern,start,end,width):
    dx,dy=end[0]-start[0],end[1]-start[1];length=max(1,round(math.hypot(dx,dy)));strip=pattern.resize((length,width),Image.Resampling.LANCZOS)
    angle=math.degrees(math.atan2(dy,dx));rotated=strip.rotate(-angle,expand=True,resample=Image.Resampling.BICUBIC)
    x=round((start[0]+end[0]-rotated.width)/2);y=round((start[1]+end[1]-rotated.height)/2);canvas.alpha_composite(rotated,(x,y))


def _scrollable(widget):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll
