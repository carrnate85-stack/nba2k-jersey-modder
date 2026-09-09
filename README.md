# NBA 2K Jersey Modder

An Electron desktop workspace for jersey and shorts textures, logos, trim paths, number recoloring, uniform tweaks, and Blender previews. Python provides the image and file-format engine.

## Run

Double-click `Launch NBA 2K Jersey Modder.bat`. Projects live in `projects/` beside the launcher. The launcher checks GitHub using fast-forward updates and builds from the checked-in dependency lockfile. If an update fails, it opens the last installed Electron build. It never rebases local work or silently switches to an older interface.

First-time source setup requires Python, Node.js, and pnpm. The launcher prepares `.venv` and the Electron package. The repository contains the Blender scripts, models, templates, and application icon. Keep that folder structure intact.

## Projects and Recovery

- Save with the top-bar button or Ctrl+S.
- Unsaved project changes get a recovery copy after a brief pause. Closing or switching projects offers Save, Discard, or Cancel.
- Normal saves replace the project atomically and retain the previous file as `.bak`.
- On opening a project, a newer recovery copy can be restored. Invalid project JSON can fall back to the previous backup.
- Logos, trims, imported numbers, and references are kept inside each project. Asset paths inside the project are saved relative to its folder.
- Export packages include referenced source assets alongside the source project and generated textures.
- Project files use version 3. Newer, unsupported versions are rejected rather than silently downgraded.

## Development

The active frontend is `electron/src/renderer/`, with individual tools under `pages/`. `electron/src/main.ts` owns file dialogs, restricted file access, project saves, and the persistent Python process. `assets/project-defaults.json` is the shared default document for Electron, Python, and the historical WPF interface.

`tools/wpf_engine.py` retains its historical filename for compatibility. It imports domain modules, including `font_recolor.py`, rather than the old desktop UI. Browser editor documents live in `assets/editors/`; common controls use `assets/editor-theme.css`.

`wpf/` and the earlier Python interfaces are historical compatibility sources, not active launch targets. Do not add new UI features there. See `docs/ARCHITECTURE.md`.

## Verification

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
cd electron
pnpm run typecheck
pnpm test
pnpm run package
pnpm run test:ui
```

The UI test requires Playwright (installed in the environment or supplied through `JERSEY_PLAYWRIGHT_PATH`). It launches the packaged Electron app against an isolated test workspace and captures desktop and smaller-window screenshots. Never point its test root at a real project.

## Git and Updates

Project folders, preview caches, generated exports, and installed dependencies are excluded from Git. Commit source changes and push them to GitHub to make them available on another machine. Startup downloads updates; it does not upload local changes.
