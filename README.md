# NBA 2K Jersey Modder

A desktop workspace for designing NBA 2K jersey and shorts textures, preparing supporting maps, recoloring number fonts, editing uniform tweaks, and inspecting mod resources.

## Run

Double-click **`Launch NBA 2K Jersey Modder.bat`**.

On its first run, the launcher creates an isolated `.venv` for the Python image and file-format engine. It then builds and opens the C# WPF interface. Later runs reuse both environments. The launcher also checks the configured GitHub repository for updates before opening the app.

`run.bat` is a short alias for the same launcher. The earlier Python interfaces remain available as migration fallbacks:

```powershell
.venv\Scripts\python.exe main.py --legacy
```

## WPF Workspace

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

The persistent top command bar contains project, garment, template, save, package export, native layer editor, and Blender controls. A project stores generator colors, source images, logos, trim paths, UV settings, and placement state in versioned JSON. **Export Package** creates review PNGs, BC1 DDS files, and a copy of the project source.

The layer editor is native WPF. It supports independent width and height, rotation, arrow-key nudging, UV opacity, and per-layer background cleanup. Blender preview is persistently available from the top command bar.

The Number Editor's **Browse Game Fonts** catalog reads the NBA 2K26 manifest, searches by team name, uniform name, three-letter code, or IFF filename, and reuses persistent previews in `cache/font_previews`. **Cache Missing Previews** processes only entries that are not already present.

The Template Editor exposes all bundled masters through its Garment, Template, and Map selectors, including Retro U color, region, normal, and UV maps and the existing shorts color, UV, and normal maps.

## Architecture

The visible application and the established mod-processing code are intentionally separated:

- `wpf/JerseyModder.Wpf/`: C# WPF shell, native pages, shared project state, and native layer editor.
- `tools/wpf_engine.py`: persistent JSON bridge between WPF and Python.
- `nba2k_jersey_modder/modern/document.py`: version-tolerant project state and conversion to the existing renderer's structured inputs.
- `nba2k_jersey_modder/modern/services.py`: rendering, export, and Blender preview services.
- `nba2k_jersey_modder/modern/font_catalog.py`: manifest font discovery, friendly team/uniform metadata, and persistent preview caching.
- Existing modules such as `generator.py`, `scanner.py`, `font_iff.py`, `tweak_iff.py`, and `template.py` remain the tested domain layer.

See `docs/WPF_ARCHITECTURE.md` before adding a page or bridge operation.

## Tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

The suite covers resource scanning and replacement, template handling, trim creation, generator rendering, font recoloring, tweak editing, and modern project normalization.
