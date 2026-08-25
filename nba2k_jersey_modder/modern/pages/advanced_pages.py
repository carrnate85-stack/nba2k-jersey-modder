from __future__ import annotations

import os
from pathlib import Path
import tempfile
import zipfile

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from ...iff_patch import Replacement, apply_replacements, can_replace_resource
from ...scanner import ResourceHit, scan_iff
from ...template import JerseyTemplate, TemplateZone, load_template, save_template
from ..widgets import ImageView, PageHeader
from .base import FeaturePage


class IffTexturesPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.result=None;self.replacements={}
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("IFF Textures","Inspect paired DDS and TXTR resources, export entries, and stage DDS replacements."))
        row=QHBoxLayout();open_button=QPushButton("Import IFF");export=QPushButton("Export Selected");replace=QPushButton("Choose Replacement DDS");save=QPushButton("Save Modified IFF As");[row.addWidget(x) for x in (open_button,export,replace,save)];row.addStretch();root.addLayout(row)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(("Texture","DDS","TXTR","Status","Replacement"));self.table.horizontalHeader().setStretchLastSection(True);self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);root.addWidget(self.table,1)
        open_button.clicked.connect(self._open);export.clicked.connect(self._export);replace.clicked.connect(self._replace);save.clicked.connect(self._save);self.table.cellDoubleClicked.connect(lambda *_:self._export(open_after=True))
    def _open(self):
        p,_=QFileDialog.getOpenFileName(self,"Import IFF","","IFF (*.iff);;All files (*.*)")
        if not p:return
        try:self.result=scan_iff(p);self.replacements={};self._populate();self.statusChanged.emit(f"Loaded {Path(p).name}: {len(self.result.texture_pairs)} texture pair(s).")
        except Exception as e:self.show_error("IFF Textures",e)
    def _populate(self):
        self.table.setRowCount(0)
        for pair in self.result.texture_pairs:
            row=self.table.rowCount();self.table.insertRow(row);dds=pair.dds_hits[0] if pair.dds_hits else None;txtr=pair.txtr_hits[0] if pair.txtr_hits else None
            values=(pair.key,dds.name if dds else "",txtr.name if txtr else "",pair.status,"")
            for col,value in enumerate(values):self.table.setItem(row,col,QTableWidgetItem(value))
            self.table.item(row,0).setData(Qt.ItemDataRole.UserRole,(dds,txtr))
    def _selected_resource(self):
        row=self.table.currentRow()
        if row<0:return None
        dds,txtr=self.table.item(row,0).data(Qt.ItemDataRole.UserRole);return dds or txtr
    def _bytes(self,resource):
        if resource.archive_path:
            with zipfile.ZipFile(self.result.path) as z:return z.read(resource.archive_path)
        if resource.size:return self.result.path.read_bytes()[resource.offset:resource.offset+resource.size]
        raise ValueError("This reference has no safe embedded byte range.")
    def _export(self,checked=False,open_after=False):
        resource=self._selected_resource()
        if not resource:return
        p,_=QFileDialog.getSaveFileName(self,"Export resource",resource.name,"All files (*.*)")
        if p:
            try:Path(p).write_bytes(self._bytes(resource));os.startfile(p) if open_after else None
            except Exception as e:self.show_error("IFF Textures",e)
    def _replace(self):
        row=self.table.currentRow();resource=self._selected_resource()
        if row<0 or not resource or resource.kind!="DDS":return
        p,_=QFileDialog.getOpenFileName(self,"Replacement DDS","","DDS (*.dds)")
        if p:self.replacements[resource]=Path(p);self.table.setItem(row,4,QTableWidgetItem(Path(p).name))
    def _save(self):
        if not self.result or not self.replacements:return
        p,_=QFileDialog.getSaveFileName(self,"Save modified IFF",self.result.path.stem+"_modified.iff","IFF (*.iff)")
        if p:
            try:apply_replacements(self.result.path,Path(p),[Replacement(k,v) for k,v in self.replacements.items()]);self.statusChanged.emit(f"Saved {Path(p).name}.")
            except Exception as e:self.show_error("IFF Textures",e)


class RdatEditorPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.path=None;self.entry=None;self.encoding="utf-8"
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("RDAT Editor","Edit loose RDAT text or an RDAT entry stored inside an archive-style IFF."))
        row=QHBoxLayout();open_button=QPushButton("Open RDAT or IFF");save=QPushButton("Save");save_as=QPushButton("Save As");row.addWidget(open_button);row.addWidget(save);row.addWidget(save_as);row.addStretch();root.addLayout(row);self.editor=QTextEdit();self.editor.setAcceptRichText(False);root.addWidget(self.editor,1)
        open_button.clicked.connect(self._open);save.clicked.connect(self._save);save_as.clicked.connect(lambda:self._save(True))
    def _open(self):
        p,_=QFileDialog.getOpenFileName(self,"Open RDAT or IFF","","RDAT / IFF (*.rdat *.iff);;All files (*.*)")
        if not p:return
        try:
            self.path=Path(p);self.entry=None
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z:
                    names=[n for n in z.namelist() if n.lower().endswith(".rdat")]
                    if not names:raise ValueError("No RDAT entry was found in this IFF.")
                    self.entry=names[0] if len(names)==1 else QInputDialog.getItem(self,"Choose RDAT","Entry",names,0,False)[0];data=z.read(self.entry)
            else:data=self.path.read_bytes()
            text,self.encoding=_decode(data);self.editor.setPlainText(text);self.statusChanged.emit(f"Loaded {self.entry or self.path.name} ({self.encoding}).")
        except Exception as e:self.show_error("RDAT Editor",e)
    def _save(self,save_as=False):
        if not self.path:return
        output=self.path
        if save_as:
            p,_=QFileDialog.getSaveFileName(self,"Save RDAT",self.path.name,"RDAT / IFF (*.rdat *.iff)");output=Path(p) if p else None
        if not output:return
        try:
            data=self.editor.toPlainText().encode(self.encoding)
            if self.entry:
                handle,temp_name=tempfile.mkstemp(suffix=".iff");os.close(handle);temp=Path(temp_name)
                with zipfile.ZipFile(self.path) as source,zipfile.ZipFile(temp,"w") as target:
                    for info in source.infolist():target.writestr(info,data if info.filename==self.entry else source.read(info.filename))
                temp.replace(output)
            else:output.write_bytes(data)
            self.path=output;self.statusChanged.emit(f"Saved {output.name}.")
        except Exception as e:self.show_error("RDAT Editor",e)


class TemplateEditorPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.image_path=None;self.zones_path=None;self.zones=[]
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Template Editor","Maintain color-coded template zones and exact 2048 coordinate data."))
        row=QHBoxLayout();image=QPushButton("Open Template Image");zones=QPushButton("Open Zones");save=QPushButton("Save Zones As");add=QPushButton("Add Zone");remove=QPushButton("Remove Zone");[row.addWidget(x) for x in (image,zones,save,add,remove)];row.addStretch();root.addLayout(row)
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1);self.preview=ImageView();self.preview.pointClicked.connect(self._coordinate);split.addWidget(self.preview);right=QWidget();rl=QVBoxLayout(right);self.coord=QLabel("Mouse: --");self.coord.setObjectName("muted");rl.addWidget(self.coord)
        self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(("Name","Type","X","Y","Width","Height","Hex","Layer"));self.table.horizontalHeader().setStretchLastSection(True);rl.addWidget(self.table,1);split.addWidget(right);split.setSizes([650,520])
        image.clicked.connect(self._open_image);zones.clicked.connect(self._open_zones);save.clicked.connect(self._save);add.clicked.connect(self._add);remove.clicked.connect(self._remove)
    def _open_image(self):
        p,_=QFileDialog.getOpenFileName(self,"Open template image","","Images (*.png *.jpg *.jpeg)")
        if p:self.image_path=Path(p);self.preview.load_path(self.image_path)
    def _open_zones(self):
        p,_=QFileDialog.getOpenFileName(self,"Open zones","","Zones JSON (*.json)")
        if not p:return
        try:self.zones_path=Path(p);template=load_template(self.zones_path);self.zones=list(template.zones);self._populate();self.statusChanged.emit(f"Loaded {len(self.zones)} zones.")
        except Exception as e:self.show_error("Template Editor",e)
    def _populate(self):
        self.table.setRowCount(len(self.zones))
        for row,z in enumerate(self.zones):
            for col,value in enumerate((z.name,z.zone_type,z.x,z.y,z.width,z.height,z.color,z.layer)):self.table.setItem(row,col,QTableWidgetItem(str(value)))
    def _read(self):
        result=[]
        for r in range(self.table.rowCount()):
            values=[self.table.item(r,c).text() if self.table.item(r,c) else "" for c in range(8)]
            result.append(TemplateZone(values[0] or f"zone_{r+1}",values[1] or "custom",*[int(values[i] or 0) for i in range(2,6)],values[6] or "#ffffff",int(values[7] or 10)))
        return result
    def _save(self):
        p,_=QFileDialog.getSaveFileName(self,"Save template zones",self.zones_path.name if self.zones_path else "template.zones.json","JSON (*.json)")
        if p:
            try:self.zones=self._read();save_template(Path(p),JerseyTemplate(str(self.image_path or ""),tuple(self.zones)));self.statusChanged.emit(f"Saved {len(self.zones)} zones.")
            except Exception as e:self.show_error("Template Editor",e)
    def _add(self):
        row=self.table.rowCount();self.table.insertRow(row)
        for col,value in enumerate((f"new_zone_{row+1}","custom","0","0","100","100","#ffffff","10")):self.table.setItem(row,col,QTableWidgetItem(value))
    def _remove(self):
        if self.table.currentRow()>=0:self.table.removeRow(self.table.currentRow())
    def _coordinate(self,x,y):self.coord.setText(f"Mouse: X {round(x)} | Y {round(y)}")


def _decode(data):
    for encoding in ("utf-8-sig","utf-8","utf-16"):
        try:return data.decode(encoding),encoding
        except UnicodeDecodeError:pass
    return data.decode("latin-1"),"latin-1"
