from __future__ import annotations


APP_STYLE = """
QWidget {
    color: #1c2429;
    background: #f3f5f4;
    font-family: "Segoe UI";
    font-size: 10pt;
    letter-spacing: 0px;
}
QMainWindow, QDialog { background: #f3f5f4; }
QWidget#sidebar { background: #172126; color: #eef3f2; }
QWidget#sidebar QLabel { background: transparent; color: #eef3f2; }
QLabel#brand { font-size: 15pt; font-weight: 700; }
QLabel#brandSubtle { color: #8ca19e; font-size: 9pt; }
QPushButton#navButton {
    background: transparent;
    color: #c8d3d1;
    border: 0;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 10px 13px;
    text-align: left;
}
QPushButton#navButton:hover { background: #213036; color: white; }
QPushButton#navButton:checked {
    background: #26383e;
    border-left-color: #42b8a9;
    color: white;
    font-weight: 600;
}
QLabel#pageTitle { font-size: 18pt; font-weight: 700; color: #172126; }
QLabel#pageSubtitle, QLabel#muted { color: #657277; }
QFrame#section { background: #ffffff; border: 1px solid #d6dddb; border-radius: 5px; }
QToolButton#sectionHeader {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #e3e8e7;
    padding: 8px 10px;
    text-align: left;
    font-weight: 600;
}
QPushButton, QToolButton {
    background: #ffffff;
    border: 1px solid #bfc9c7;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton:hover, QToolButton:hover { border-color: #42a99d; background: #f8fbfa; }
QPushButton:pressed, QToolButton:pressed { background: #e7f2f0; }
QPushButton#primaryBar {
    background: #167f75;
    color: white;
    border-color: #167f75;
    font-weight: 650;
    padding: 9px 12px;
}
QPushButton#primaryBar:hover { background: #126f67; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget, QTableWidget {
    background: white;
    border: 1px solid #c7d0ce;
    border-radius: 3px;
    selection-background-color: #29988c;
    selection-color: white;
    padding: 4px;
}
QComboBox, QSpinBox, QDoubleSpinBox { min-height: 24px; }
QHeaderView::section {
    background: #e9eeed;
    border: 0;
    border-right: 1px solid #d1d9d7;
    border-bottom: 1px solid #c7d0ce;
    padding: 6px;
    font-weight: 600;
}
QScrollArea { border: 0; background: transparent; }
QSplitter::handle { background: #d6dddb; width: 1px; height: 1px; }
QStatusBar { background: #ffffff; color: #536167; border-top: 1px solid #d6dddb; }
QMenuBar, QMenu { background: #ffffff; }
QMenuBar::item:selected, QMenu::item:selected { background: #dcecea; }
QSlider::groove:horizontal { height: 5px; background: #d3dcda; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #167f75; border-radius: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QProgressBar { border: 1px solid #c7d0ce; border-radius: 3px; background: white; text-align: center; }
QProgressBar::chunk { background: #42a99d; }
"""
