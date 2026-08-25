from __future__ import annotations

from pathlib import Path
import threading

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QDialog, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea, QSlider,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...app import _recolor_font_image
from ...font_iff import extract_number_sheet_from_font_iff, inspect_font_number_texture, split_number_sheet_digits, write_number_sheet_to_font_iff
from ...game_manifest import DEFAULT_NBA2K26_ROOT, ManifestEntry
from ...tweak_iff import inspect_front_number_tweak, write_front_number_tweak
from ..font_catalog import FontCatalog, describe_manifest_font
from ..widgets import ImageView, PageHeader, pil_to_qimage
from .base import FeaturePage, Worker


class NumberEditorPage(FeaturePage):
    statusChanged=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.source=None;self.info=None;self.original=[];self.current=None
        root=QVBoxLayout(self);root.setContentsMargins(18,16,18,16);root.addWidget(PageHeader("Number Editor","Import a font IFF, recolor its fill and outline, then save a modified copy."))
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1);self.preview=ImageView();split.addWidget(self.preview)
        panel=QWidget();panel_layout=QVBoxLayout(panel);panel_layout.setContentsMargins(8,0,0,0)
        row=QHBoxLayout();load=QPushButton("Import Font IFF");browse=QPushButton("Browse Game Fonts");save=QPushButton("Save Font IFF As");restore=QPushButton("Restore Original");row.addWidget(load);row.addWidget(browse);row.addWidget(save);row.addWidget(restore);panel_layout.addLayout(row);load.clicked.connect(self._load);browse.clicked.connect(self._browse_game_fonts);save.clicked.connect(self._save);restore.clicked.connect(self._restore)
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
        if p:self._load_path(Path(p))
    def _load_path(self,path):
        try:
            self.source=Path(path);self.info=inspect_font_number_texture(path);sheet=extract_number_sheet_from_font_iff(path);self.original=split_number_sheet_digits(sheet);self.current=sheet;self.preview.set_image(pil_to_qimage(sheet));self.statusChanged.emit(f"Loaded {self.source.name} ({sheet.width} x {sheet.height}).")
        except Exception as e:self.show_error("Number Editor",e)
    def _browse_game_fonts(self):
        dialog=FontCatalogDialog(self);dialog.fontSelected.connect(self._load_path);dialog.exec()
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


class FontCatalogDialog(QDialog):
    fontSelected=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle("NBA 2K26 Game Fonts");self.resize(1180,720);self.setMinimumSize(860,560)
        self.pool=QThreadPool.globalInstance();self.workers=[];self.entries=[];self.search_terms=[];self.cached_stems=set();self.preview_token=0;self.stop_event=threading.Event();self.settings=QSettings("NBA2KModTools","JerseyModder");self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(180);self.search_timer.timeout.connect(self._filter)
        self.game_root=Path(str(self.settings.value("gameRoot",str(DEFAULT_NBA2K26_ROOT))));self.catalog=FontCatalog(self.game_root)
        root=QVBoxLayout(self);top=QHBoxLayout();top.addWidget(QLabel("Game folder"));self.root_label=QLabel(str(self.game_root));self.root_label.setObjectName("muted");top.addWidget(self.root_label,1);choose=QPushButton("Choose Folder");choose.clicked.connect(self._choose_root);top.addWidget(choose);root.addLayout(top)
        search_row=QHBoxLayout();search_row.addWidget(QLabel("Search"));self.search=QLineEdit();self.search.setPlaceholderText("Team, uniform, code, or IFF name");self.search.textChanged.connect(lambda:self.search_timer.start());search_row.addWidget(self.search,1);self.cache_button=QPushButton("Cache Missing Previews");self.cache_button.clicked.connect(self._cache_all);search_row.addWidget(self.cache_button);self.stop_button=QPushButton("Stop");self.stop_button.setEnabled(False);self.stop_button.clicked.connect(self.stop_event.set);search_row.addWidget(self.stop_button);root.addLayout(search_row)
        split=QSplitter(Qt.Orientation.Horizontal);root.addWidget(split,1);self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(("Team","Uniform","Font IFF","Archive","Cached"));self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection);self.table.horizontalHeader().setStretchLastSection(False);self.table.horizontalHeader().setSectionResizeMode(0,self.table.horizontalHeader().ResizeMode.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(1,self.table.horizontalHeader().ResizeMode.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(2,self.table.horizontalHeader().ResizeMode.Stretch);self.table.itemSelectionChanged.connect(self._preview_selected);self.table.cellDoubleClicked.connect(lambda *_:self._load_selected());split.addWidget(self.table)
        preview_panel=QWidget();pl=QVBoxLayout(preview_panel);pl.setContentsMargins(8,0,0,0);pl.addWidget(QLabel("Number sheet preview"));self.preview=ImageView();pl.addWidget(self.preview,1);self.preview_info=QLabel("Select a font to preview it.");self.preview_info.setWordWrap(True);self.preview_info.setObjectName("muted");pl.addWidget(self.preview_info);split.addWidget(preview_panel);split.setSizes([760,400])
        actions=QHBoxLayout();load=QPushButton("Load in Number Editor");load.setObjectName("primaryBar");load.clicked.connect(self._load_selected);actions.addWidget(load);export_iff=QPushButton("Export Font IFF As");export_iff.clicked.connect(self._export_iff);actions.addWidget(export_iff);export_sheet=QPushButton("Export Number Sheet PNG As");export_sheet.clicked.connect(self._export_sheet);actions.addWidget(export_sheet);actions.addStretch();root.addLayout(actions)
        self.status=QLabel("Reading the game manifest...");self.status.setObjectName("muted");root.addWidget(self.status);self.progress=QProgressBar();self.progress.setRange(0,1);self.progress.setValue(0);root.addWidget(self.progress);self._load_catalog()
    def _choose_root(self):
        p=QFileDialog.getExistingDirectory(self,"Choose NBA 2K26 game folder",str(self.game_root))
        if p:self.game_root=Path(p);self.settings.setValue("gameRoot",p);self.root_label.setText(p);self.catalog=FontCatalog(self.game_root);self._load_catalog()
    def _run(self,callback,done):
        worker=Worker(callback);self.workers.append(worker);worker.signals.finished.connect(done);worker.signals.failed.connect(lambda error:self.status.setText(error));self.pool.start(worker)
    def _load_catalog(self):
        self.status.setText("Reading the game manifest and cache index...");self.table.setRowCount(0);self._run(lambda:(self.catalog.entries(),self.catalog.cached_stems()),self._catalog_ready)
    def _catalog_ready(self,result):
        entries,cached_stems=result;self.entries=list(entries);self.cached_stems=set(cached_stems);self._populate_table();cached=self.catalog.cached_count(self.entries,self.cached_stems);self.progress.setRange(0,max(1,len(self.entries)));self.progress.setValue(cached);self.status.setText(f"Showing {len(self.entries):,} game fonts | {cached:,} previews cached.")
    def _populate_table(self):
        self.table.setUpdatesEnabled(False);self.table.setSortingEnabled(False);self.table.setRowCount(len(self.entries));self.search_terms=[]
        for row,entry in enumerate(self.entries):
            team,uniform,code=describe_manifest_font(entry);cached=self.catalog.cache_stem(entry) in self.cached_stems;self.search_terms.append(f"{entry.name} {entry.display_name} {team} {uniform} {code}".casefold())
            for col,value in enumerate((team,uniform,entry.display_name,entry.archive_id,"Yes" if cached else "")):self.table.setItem(row,col,QTableWidgetItem(str(value)))
            self.table.item(row,0).setData(Qt.ItemDataRole.UserRole,entry)
        self.table.setUpdatesEnabled(True)
    def _filter(self):
        query=self.search.text().strip().casefold();visible=0;self.table.setUpdatesEnabled(False)
        for row,haystack in enumerate(self.search_terms):
            show=not query or query in haystack;self.table.setRowHidden(row,not show);visible+=int(show)
        self.table.setUpdatesEnabled(True);self.table.viewport().update()
        if self.entries:self.status.setText(f"Showing {visible:,} of {len(self.entries):,} game fonts | search includes team and uniform names.")
    def _selected(self):
        row=self.table.currentRow();return self.table.item(row,0).data(Qt.ItemDataRole.UserRole) if row>=0 and self.table.item(row,0) else None
    def _preview_selected(self):
        entry=self._selected()
        if not entry:return
        self.preview_token+=1;token=self.preview_token;self.preview_info.setText(f"Loading preview for {entry.display_name}...");self._run(lambda:self.catalog.ensure_thumbnail(entry),lambda result:self._preview_ready(token,result))
    def _preview_ready(self,token,result):
        if token!=self.preview_token:return
        path,label,_cached=result;self.preview.load_path(path);self.preview_info.setText(label);entry=self._selected();self._mark_cached(entry)
    def _mark_cached(self,entry):
        if entry is None:return
        self.cached_stems.add(self.catalog.cache_stem(entry))
        for row in range(self.table.rowCount()):
            if self.table.item(row,0).data(Qt.ItemDataRole.UserRole)==entry:self.table.item(row,4).setText("Yes");break
    def _load_selected(self):
        entry=self._selected()
        if not entry:return
        self.status.setText(f"Loading {entry.display_name}...");self._run(lambda:self.catalog.ensure_working_iff(entry),lambda path:(self.fontSelected.emit(path),self.status.setText(f"Loaded {entry.display_name} in Number Editor.")))
    def _export_iff(self):
        entry=self._selected()
        if not entry:return
        p,_=QFileDialog.getSaveFileName(self,"Export Font IFF",entry.display_name,"IFF (*.iff)")
        if p:self._run(lambda:self.catalog.ensure_working_iff(entry),lambda source:(Path(p).write_bytes(Path(source).read_bytes()),self.status.setText(f"Exported {Path(p).name}.")))
    def _export_sheet(self):
        entry=self._selected()
        if not entry:return
        p,_=QFileDialog.getSaveFileName(self,"Export Number Sheet PNG",f"{Path(entry.display_name).stem}_numbers.png","PNG (*.png)")
        if p:self._run(lambda:self.catalog.ensure_working_iff(entry),lambda source:(extract_number_sheet_from_font_iff(source).save(p),self.status.setText(f"Exported {Path(p).name}.")))
    def _cache_all(self):
        if not self.entries:return
        missing=[entry for entry in self.entries if self.catalog.cache_stem(entry) not in self.cached_stems]
        if not missing:self.status.setText("All manifest font previews are already cached.");return
        self.stop_event.clear();self.cache_button.setEnabled(False);self.stop_button.setEnabled(True);self.progress.setRange(0,len(missing));worker=_FontCacheWorker(self.catalog,missing,self.stop_event);self.workers.append(worker);worker.signals.progress.connect(self._cache_progress);worker.signals.finished.connect(self._cache_finished);self.pool.start(worker)
    def _cache_progress(self,done,total,created,errors):
        self.progress.setMaximum(max(1,total));self.progress.setValue(done);self.status.setText(f"Caching previews: {done:,} of {total:,} | {created:,} new | {errors:,} skipped")
    def _cache_finished(self,done,total,created,errors,stopped):
        self.cache_button.setEnabled(True);self.stop_button.setEnabled(False);word="stopped" if stopped else "complete";self.status.setText(f"Preview cache {word}: {done:,} of {total:,} | {created:,} new | {errors:,} skipped.");self._run(self.catalog.cached_stems,self._cache_index_ready)
    def _cache_index_ready(self,stems):
        self.cached_stems=set(stems)
        for row,entry in enumerate(self.entries):self.table.item(row,4).setText("Yes" if self.catalog.cache_stem(entry) in self.cached_stems else "")
    def closeEvent(self,event):self.stop_event.set();super().closeEvent(event)


class _FontCacheSignals(QObject):
    progress=Signal(int,int,int,int);finished=Signal(int,int,int,int,bool)


class _FontCacheWorker(QRunnable):
    def __init__(self,catalog,entries,stop_event):super().__init__();self.catalog=catalog;self.entries=entries;self.stop_event=stop_event;self.signals=_FontCacheSignals()
    @Slot()
    def run(self):
        done=created=errors=0;total=len(self.entries)
        for entry in self.entries:
            if self.stop_event.is_set():break
            try:
                _path,_label,cached=self.catalog.ensure_thumbnail(entry);created+=0 if cached else 1
            except Exception:errors+=1
            done+=1
            if done==1 or done%5==0 or done==total:self.signals.progress.emit(done,total,created,errors)
        self.signals.finished.emit(done,total,created,errors,self.stop_event.is_set())


def _row(*widgets):
    widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0)
    for item in widgets:layout.addWidget(item)
    return widget
def _rgb(value):
    value=value.lstrip("#");return tuple(int(value[i:i+2],16) for i in (0,2,4))
