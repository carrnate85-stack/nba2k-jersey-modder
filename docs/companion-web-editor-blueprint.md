# Companion Web Editor Blueprint

This document defines the reusable browser-editor pattern used by NBA 2K Jersey Modder. Use it when building a companion editor that should share the same visual language, canvas controls, layer behavior, and desktop-app handoff.

## Product Shape

The editor is a local browser workspace launched by a desktop application. The browser handles responsive, high-frequency canvas interaction while the desktop application owns projects, file dialogs, persistence, and export.

The browser must feel like a focused editing surface, not a website:

- Persistent command bar across the top.
- Full-height canvas workspace on the left.
- Fixed-width, vertically scrollable inspector on the right.
- Immediate visual feedback while dragging.
- Project updates sent to the desktop backend after an interaction finishes.
- A prominent `Return to App` action that saves state and restores the desktop window.

## Visual System

Use the accompanying `companion-web-editor-profile.json` as the source of truth.

Core presentation:

- Font: Segoe UI, then Arial, sans-serif.
- Application background: `#171a20`.
- Canvas workspace: `#11141a`.
- Header: `#222833` with a `#343b49` bottom border.
- Inspector: `#1d222c` with a `#343b49` left border.
- Inspector panels: `#202632`.
- Primary text: `#edf1f7`.
- Muted text: `#aab3c2`.
- Primary command: amber `#f0b429` with dark text.
- Return/success command: teal `#168579` or green `#2f7655` with white text.
- Selected layer: amber border, white text.
- Controls use 5-6 px corner radii. Avoid oversized rounding.

## Layout

```text
+---------------------------------------------------------------------+
| Tool title | commands | zoom | status              | Return to App |
+----------------------------------------------------+----------------+
|                                                    | View controls  |
|                                                    |----------------|
|                 CANVAS WORKSPACE                   | Layer list     |
|                                                    |----------------|
|                                                    | Inspector      |
|                                                    |----------------|
|                                                    | Output/actions |
+----------------------------------------------------+----------------+
```

Recommended dimensions:

- Header: 48-52 px high.
- Inspector: 300-390 px wide depending on control density.
- Header padding: 14 px.
- Inspector padding: 12-14 px.
- Control gap: 8 px.
- Canvas should consume all remaining space.
- Hide optional header controls below 820 px rather than allowing overlap.

## Canvas Behavior

### Navigation

- Mouse wheel zooms around the pointer location.
- Middle-mouse drag pans.
- `Shift` plus drag may also pan for trackpads or two-button mice.
- `Fit` centers the full document in the available workspace.
- Explicit `Zoom -` and `Zoom +` buttons remain available.
- Clamp zoom so the document cannot disappear or become unusably large.

### Selection

- Clicking visible image pixels selects the topmost eligible layer.
- Transparent pixels should click through to lower layers.
- Use an alpha hit threshold near `12/255`.
- Search layers from top to bottom during hit testing.
- Clicking empty canvas deselects everything.
- The layer list and canvas selection must remain synchronized.
- Selected layers receive a high-contrast outline and stable resize handles.

### Transforming

- Drag the artwork itself to move it.
- Draw resize handles in canvas coordinates but keep their screen size visually stable.
- Width and height are independent unless a layer explicitly requests aspect locking.
- Rotation must preserve usable handle hit areas.
- Numeric X, Y, width, height, and rotation fields provide exact edits.
- Arrow keys nudge one document pixel.
- `Shift` plus an arrow key nudges ten document pixels.
- Render locally on every pointer move; persist only on pointer release or debounced keyboard completion.

### Layer Controls

- Show one flat, ordered layer list.
- Display a clear layer label and short role description.
- Support layer up/down when the layer can be reordered.
- Support visibility, flip, cleanup, and transform controls only when allowed by that layer's capabilities.
- Derived or mirrored artwork becomes a separate layer.
- Linked layers may move together, but every layer remains independently selectable and unlinkable.

## Path Drawing Mode

For tools similar to Trim Path Lab:

- `New Path` begins a clean drawing.
- Left click adds points.
- A live segment extends from the last point to the pointer.
- Display exact angle and length while drawing.
- Right click, Escape, or `Finish Path` ends the current path.
- Default to straight segments.
- Also support smooth curves with adjustable bend and T shapes with open/closed junction modes.
- Angle snapping options: off, 1, 5, 15, and 45 degrees.
- Holding `Alt` temporarily bypasses snapping.
- Pattern width, length scale, and offset each have a slider plus editable number field.
- UV overlays and source-preview opacity are guides only and never export.
- Export each finished path as a separate full-resolution transparent PNG layer.

## Image Cleanup

Each supported image layer may expose:

- Auto background detection.
- Remove white.
- Remove black.
- Outside-only removal to preserve enclosed letter holes.
- Tolerance from 0-255.
- Reset to project defaults.

Cleanup should be non-destructive. Keep the original source path and derive the preview/output dynamically or cache a processed copy.

## Desktop Session Contract

Use a loopback-only HTTP server bound to `127.0.0.1` on an available port. Do not expose the editor to the local network.

Desktop launch sequence:

1. Desktop app writes a project snapshot into a unique temporary session folder.
2. Desktop app starts the companion backend with project, state, and asset paths.
3. Backend prints one JSON line containing the editor URL.
4. Desktop app opens that URL in the user's browser.
5. Browser loads project metadata and images through local API endpoints.
6. Browser renders interactions immediately in memory.
7. Backend writes updates atomically to `state.json`.
8. Desktop app polls the state file every 350-500 ms and applies newer revisions.
9. `Return to App` sets `returnRequested: true`, then the desktop app restores and focuses its window.
10. Closing the desktop app terminates the local backend process tree.

Recommended state envelope:

```json
{
  "revision": 12,
  "returnRequested": false,
  "project": {}
}
```

Write atomically by creating a sibling temporary file and replacing `state.json` after serialization completes.

## Suggested HTTP API

```text
GET  /                         Editor HTML
GET  /api/project              Document metadata and layer capabilities
GET  /api/base.png             Current generated preview
GET  /api/uv.png               Optional UV or guide overlay
GET  /api/image/{layerKey}     Original or processed layer pixels
POST /api/update               Position, size, and rotation update
POST /api/reorder              Layer order update
POST /api/transparency         Per-layer cleanup override
POST /api/flip                 Horizontal flip
POST /api/reset                Reset editor-owned changes
POST /api/return               Save state and return focus to desktop
```

Path-oriented tools may add:

```text
GET  /api/path/project
GET  /api/path/background
GET  /api/path/pattern
POST /api/path/send
POST /api/path/return
```

## Layer Payload

```json
{
  "key": "logo:0",
  "label": "Center Chest Logo",
  "layerLabel": "Logo layer 1",
  "imageUrl": "/api/image/logo%3A0",
  "x": 864,
  "y": 620,
  "width": 320,
  "height": 180,
  "rotation": 0,
  "visible": true,
  "canTransform": true,
  "canRotate": true,
  "canReorder": true,
  "canCleanup": true,
  "canFlip": false,
  "lockAspect": false,
  "clipBox": null,
  "excludeBoxes": []
}
```

Capabilities belong in the payload. The browser should not infer business rules from layer names.

## Performance Rules

- Keep original image pixels; never repeatedly resize an already-resized preview.
- Cache decoded `Image` objects by layer key and source version.
- Cache-bust only when the backing asset or project revision changes.
- Use `requestAnimationFrame` to collapse repeated draw requests.
- Perform drag and resize rendering entirely in the browser.
- Send updates only on pointer release or after a short keyboard debounce.
- Avoid reloading every layer after a transform response; patch the affected layer in place.
- Keep canvas dimensions equal to document dimensions for exports, but scale only the view transform.
- Use a separate 1x1 canvas for alpha hit testing instead of reading the entire canvas.

## Accessibility and Reliability

- Every numeric control and slider requires a visible label.
- Disabled controls must visibly communicate unavailable capabilities.
- Preserve keyboard nudge behavior when the canvas is focused.
- Prevent text fields from triggering canvas shortcuts.
- Keep status messages concise and visible in the header.
- Failed images should identify the affected layer without blocking the remaining editor.
- Empty states should explain the one next action needed.
- Confirm destructive reset or clear-all commands.

## Copy-Ready Implementation Prompt

```text
Build a local browser companion editor using the NBA 2K Jersey Modder Companion Web Editor Blueprint and companion-web-editor-profile.json.

Use a persistent 48-52 px command bar, full-height canvas workspace, and a 300-390 px scrollable right inspector. Match the supplied dark color tokens and compact 5-6 px control radii. This is a working editor, not a landing page.

Implement pointer-centered wheel zoom, middle-button and Shift-drag panning, fit/zoom buttons, alpha-aware topmost layer selection, empty-canvas deselection, independent width/height resizing, rotation, numeric transforms, arrow-key nudging, layer reordering, per-layer capability flags, optional UV overlay, non-destructive background cleanup, reset, and a prominent Return to App button.

Keep drag feedback entirely client-side and persist after pointer release. Use requestAnimationFrame for drawing, cache decoded images, and never resample from an already resized image. Communicate with a loopback-only local backend using project/image/update/return endpoints and an atomically written revisioned state file. The desktop app owns files, projects, persistence, and final export.

For path tools, support point placement, live angle/length readout, right-click finish, straight/smooth/T paths, open and closed T junctions, angle snapping, linked mirrors, UV guides, and one transparent full-resolution PNG per finished layer.
```

