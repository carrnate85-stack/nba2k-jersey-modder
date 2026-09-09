from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"

def load_editor_html(name: str) -> str:
    html = (ASSETS / "editors" / name).read_text(encoding="utf-8")
    theme = (ASSETS / "editor-theme.css").read_text(encoding="utf-8")
    return html.replace("</head>", f"<style>{theme}</style></head>", 1)
