# Active Architecture

Electron owns the desktop shell, navigation, project state, dialogs, and web editor windows. React pages edit the shared project. Python owns image rendering, DDS/IFF/RDAT processing, templates, manifest discovery, and Blender preparation.

## Project Contract

`assets/project-defaults.json` is the shared default document. `project-storage.ts` and Python `ProjectDocument` handle normalization. Version 1/2 panel colors migrate into separate shorts fields. Unsupported future versions fail explicitly. Unknown extension fields are preserved.

Explicit saves write a temporary file, flush it, keep the previous save, and replace the original. Recovery snapshots are separate from explicit saves. Relative asset paths are resolved against the opened project folder. The UI must never clear a newer dirty revision when an older save finishes.

## Previews

Each preview channel has one active request and one replaceable pending request. React revision checks prevent older images from replacing newer previews. Preview data is read asynchronously. Export operations are not discarded by the preview queue. Temporary render/font/thumbnail outputs retain recent files while older surplus outputs are pruned; staged source assets are not pruned.

## Editors

Editor windows are modal to prevent concurrent edits to two snapshots of the same project. They use sandboxed, isolated browser contexts, deny unexpected navigation, and publish revisions to the desktop. The Python server is stopped on return. Layout and interaction tests must cover actual handoffs, not only the presence of JavaScript strings.

HTML editor documents are under `assets/editors/`, separate from HTTP handlers. Shared control tokens are in `assets/editor-theme.css`. Treat labels and filenames as text when inserting them into the DOM.

## File Access

IPC requests must originate in the main window's top frame. Reads are limited to project assets, bundled assets, temporary previews, cache files, and files selected in a native dialog. Writes require project, temporary, or dialog-granted destinations. Paths are resolved through filesystem links before checking directory boundaries.

## Historical Interfaces

The WPF and older Python UIs remain for reference and migration compatibility. The launcher no longer switches to them after an Electron build failure. Backend algorithms belong in domain modules, not UI files. Remove historical modules only after their remaining imports and compatibility tests have been migrated.
