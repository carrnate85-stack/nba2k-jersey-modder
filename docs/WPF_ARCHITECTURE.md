# WPF Architecture

## Ownership

The C# WPF project owns every visible window, page, control, dialog, editor, and project command. Python owns image rendering, DDS/IFF/RDAT handling, template data, number-font processing, tweak values, manifest discovery, and Blender preparation.

`WorkspaceContext` is shared by all WPF pages. `ProjectStore` is the single in-memory project document. Pages update that document and ask `PythonBridge` for derived output instead of duplicating renderer logic.

## Bridge

`tools/wpf_engine.py` is a persistent process. It reads one JSON request per line and returns one JSON response per line. Standard output is reserved for protocol responses; library output is redirected to standard error.

Add a focused bridge method when a page needs domain work. Do not invoke a separate Python process for each slider change because startup and imports make interactive editing noticeably slower.

## Pages

Each main work area is a separate `ToolPageBase` implementation under `Views`. The fixed left rail changes the visible page. Global project, garment, template, export, layer-editor, and Blender commands remain in `MainWindow`.

IFF Textures, RDAT Editor, and Template Editor are grouped under Advanced because they are source-maintenance tools rather than the normal jersey-building sequence.

## Compatibility

Project files remain JSON and are normalized by both `ProjectStore` and Python's `ProjectDocument`. Existing projects, template masters, persistent number thumbnails in `cache/font_previews`, Blender files, and generated image paths are reused by WPF.
