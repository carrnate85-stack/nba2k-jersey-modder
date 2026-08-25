# NBA 2K Jersey Modder

A desktop workspace for designing NBA 2K jersey and shorts textures, preparing supporting maps, recoloring number fonts, editing uniform tweaks, and inspecting mod resources.

## Run

Double-click **`Launch NBA 2K Jersey Modder.bat`**.

On its first run, the launcher creates an isolated `.venv` and installs the modern PySide6 desktop components. Later runs skip that setup unless `requirements.txt` changes. The launcher also checks the configured GitHub repository for updates before opening the app.

`run.bat` is a short alias for the same launcher. The classic Tk workspace is still available during the conversion:

```powershell
.venv\Scripts\python.exe main.py --legacy
```

## Modern Workspace

The fixed left navigation contains:

- Generator
- Logo Creator
- Trim Creator
- Trim Path Lab
- Number Editor
- Tweak Editor
- Texture Creator
- IFF Textures
- RDAT Editor
- Template Editor

Project commands are under **File**. A project stores generator colors, source images, logos, trim paths, UV settings, and placement state in a versioned JSON file. **Export Package As** creates review PNGs, BC1 DDS files, and a copy of the project source.

The current browser layer editor is available through **Open Web Editor** as a temporary classic-workspace bridge. Blender preview remains available from the Generator and Preview menu.

## Architecture

The modern UI is intentionally separated from texture and IFF logic:

- `nba2k_jersey_modder/modern/main_window.py`: window, left navigation, menus, and shared project lifecycle.
- `nba2k_jersey_modder/modern/pages/`: one module per tool family.
- `nba2k_jersey_modder/modern/document.py`: version-tolerant project state and conversion to the existing renderer's structured inputs.
- `nba2k_jersey_modder/modern/services.py`: rendering, export, and Blender preview services.
- Existing modules such as `generator.py`, `scanner.py`, `font_iff.py`, `tweak_iff.py`, and `template.py` remain the tested domain layer.

See `docs/MODERN_UI.md` before adding a page or migrating more classic-only behavior.

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

The suite covers resource scanning and replacement, template handling, trim creation, generator rendering, font recoloring, tweak editing, and modern project normalization.
