# Modern UI Development Notes

## Design Boundary

PySide6 owns windows, dialogs, navigation, page layouts, and user interaction. The existing pure Python modules own image rendering, IFF parsing, font texture handling, tweak values, and template data. Keep those responsibilities separate so a creator page can be redesigned without rewriting file formats.

## Shared Project State

`ProjectDocument` is the source of truth for project-backed pages. Pages receive the same document instance and emit `documentChanged` after a real edit. `MainWindow` then marks the project dirty and refreshes dependent previews.

New project fields must:

1. Receive a safe default in `new_project_payload()`.
2. Be merged in `_normalize()` so older project files still open.
3. Be translated in `to_generator_inputs()` only when the renderer needs them.
4. Receive a focused test in `tests/test_modern_document.py` or the domain suite.

## Adding A Page

1. Derive the page from `FeaturePage`.
2. Put long control columns inside `QScrollArea`.
3. Use `PageHeader`, `ImageView`, `ColorField`, and `FileField` before creating a new local widget pattern.
4. Add the page to `MainWindow.pages` in the intended navigation order.
5. Expose `statusChanged(str)` for useful completion messages.
6. Expose `documentChanged()` only if the page changes project state.

## Long Operations

Use `Worker` and `QThreadPool` for 2048 texture rendering, scanning large IFFs, thumbnail caching, or other work that can block the event loop. Debounce sliders with a single-shot `QTimer`; do not render a full texture for every raw movement event.

The manifest catalog cache remains at `cache/font_previews`, matching the classic workspace. Cache keys include the resolved game root and manifest entry identity. Preserve this format so users do not need to rebuild thousands of previews after UI changes.

## Migration Status

All major desktop tools have PySide6 pages. The browser layer editor still uses the classic application's established host callbacks, so **Open Web Editor** launches the classic workspace during this transition. The next clean migration step is a standalone `WebEditorAdapter` backed by `ProjectDocument` and `GeneratorService`; after that, the classic bridge and the Number Editor's temporary recolor import from `app.py` can be removed.
