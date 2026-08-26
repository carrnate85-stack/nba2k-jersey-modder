# Jersey Modder Style Brief

## Overall Direction

NBA 2K Jersey Modder is a quiet, work-focused desktop tool. Its visual identity combines a light neutral workspace with a dark charcoal-green navigation rail and restrained teal accents. It should feel like a practical creative utility: clean, compact, organized, and modern without looking like a marketing page.

## Core Palette

| Role | Color |
|---|---|
| Main text / ink | `#182329` |
| Muted text | `#65757B` |
| App background / paper | `#F4F6F5` |
| Panels and top bar | `#FFFFFF` |
| Borders and dividers | `#CED7D5` |
| Main accent | `#168579` |
| Sidebar | `#172329` |
| Sidebar hover | `#22333A` |
| Selected navigation | `#293C43` |
| Selected navigation marker | `#43B9AA` |
| Brand highlight | `#58C9BA` |
| Pressed light-accent state | `#E4F1EF` |
| Sidebar primary text | `#C9D5D2` |
| Sidebar muted text | `#83959A` |

Use teal as a functional accent, not a dominant fill. Most of the interface should remain white, soft gray, and charcoal.

## Layout

- Fixed dark sidebar on the left, approximately `226 px` wide.
- Persistent white global toolbar across the top, approximately `76 px` high.
- Main page content uses the soft gray `#F4F6F5` background.
- A slim white status bar remains visible along the bottom.
- Primary navigation stays in the sidebar; infrequently used tools live under an `Advanced` expander near the bottom.
- Global project actions, garment selection, template selection, web editor, and Blender preview stay in the top toolbar.
- Each page begins with a compact 24 px title and one short muted description.
- Working pages usually use a control pane beside a large preview pane. Allow the preview to receive most of the available width.
- Use collapsible sections for long workflows instead of showing every control simultaneously.
- Keep right panes and control columns vertically scrollable in smaller windows.

## Typography

- Font family: `Segoe UI`.
- Default UI text: `13 px`.
- Page titles: `24 px`, semibold.
- Product title: `20 px`, semibold.
- Project name: `15 px`, semibold.
- Section and action labels: `13-15 px`.
- Field labels and status text: `10-11 px`, muted.
- Avoid oversized headings and decorative letter spacing.

## Controls

- Buttons are compact, rectangular, and use a `4 px` corner radius.
- Standard buttons are white with a `#CED7D5` border.
- Hover changes the border to teal.
- Primary buttons use `#168579`, white text, and semibold weight.
- Inputs use white backgrounds, subtle borders, and approximately `30 px` minimum height.
- Group boxes are white with a thin border, `10-12 px` internal padding, and minimal decoration.
- Use full-width primary bars for major transitions such as `Open Web Layer Editor`.
- Use checkboxes for binary options, dropdowns for garment/template modes, numeric fields for exact values, and sliders paired with numeric values for continuous adjustments.
- Keep corner radii at `4-6 px`; do not use pill-shaped controls.

## Navigation Behavior

- Navigation items span the full sidebar width.
- Use a teal `3 px` left marker for the selected page.
- Selected navigation uses a slightly lighter charcoal background and white semibold text.
- Hover uses a subtle charcoal lift rather than animation or glow.
- Keep the application icon, product name, and short workspace label at the top of the sidebar.

## Preview Surfaces

- Image and texture preview areas use near-black `#101518` backgrounds so transparency and light textures remain readable.
- Zoom state appears as a small dark overlay in the lower-right corner.
- Editing controls should not be drawn over the main desktop preview; direct manipulation belongs in the browser editor.
- Desktop previews are primarily for inspection, while browser previews are for selection and transformation.

## Visual Character

Use these principles when matching the app:

- Functional before decorative.
- Dense enough for repeated work, but never crowded.
- Thin borders instead of heavy shadows.
- White panels sit directly on the paper background; avoid nested cards.
- Teal communicates selection, progress, and primary actions.
- Dark surfaces are reserved for navigation and visual editing canvases.
- Keep copy short and task-oriented.
- Avoid gradients, oversized cards, ornamental backgrounds, and large empty hero areas.

## Copy-Ready Style Prompt

```text
Design this desktop utility to match NBA 2K Jersey Modder. Use a 226 px charcoal-green sidebar (#172329), a persistent 76 px white top toolbar, a soft gray workspace (#F4F6F5), white panels, dark ink text (#182329), muted text (#65757B), thin gray-green borders (#CED7D5), and restrained teal accents (#168579).

Use Segoe UI at 13 px by default, compact 24 px semibold page headings, 4-6 px control radii, thin borders, and minimal shadows. Navigation should use full-width rows with a teal 3 px selected marker, a #293C43 selected background, and white text. Keep project and mode controls persistent in the top toolbar. Put infrequent tools under an Advanced section.

Build a practical, dense creative-tool layout with scrollable control panes and large preview areas. Use collapsible workflow sections rather than displaying every control at once. Standard buttons are white with subtle borders; primary commands are teal with white text. Reserve near-black surfaces for image previews and browser-based canvas editors. Avoid marketing layouts, gradients, oversized cards, pills, and decorative whitespace.
```
