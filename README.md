# NBA 2K Jersey Modder

First-pass desktop GUI for opening NBA 2K jersey `.iff` mod files and inspecting embedded texture resources.

## Run

Double-click `run.bat`, or run:

```powershell
python main.py
```

If Windows opens the Microsoft Store instead of Python, install Python 3 or keep using `run.bat` from this Codex workspace. The launcher can fall back to the bundled runtime available here.

## Current Features

- Import a jersey mod `.iff` file.
- Read ZIP-style NBA 2K `.iff` archives directly.
- Explore detected resource references in a file explorer tab.
- Scan for embedded DDS headers.
- Scan for filename-style `.dds` and `.txtr` references.
- Show a flat texture list with corresponding `.dds` and `.txtr` files side by side, without repeated filename references.
- Double-click the `.dds` side or `.txtr` side of a texture row to open that file.
- Extract internal archive entries to a temp working folder before opening them.
- Match named `.dds` references to embedded DDS headers by file order so those rows can be exported/opened.
- Open DDS files in Photoshop when Photoshop is installed, falling back to the default Windows app.
- Open TXTR sidecar files in Notepad.
- Ask you to locate a DDS/TXTR manually if the `.iff` only contains a filename reference and the app cannot extract the packed file yet.
- Stage replacement DDS files and save a modified `.iff` copy when the DDS has a confirmed embedded range.
- Detect `.rdat` references from imported `.iff` files.
- Open, edit, and save `.rdat` files in a text editor tab.
- Load a Photoshop-exported PNG template and draw color-coded placement zones in the Template Editor.
- Fit/zoom the template view while preserving original 2048 x 2048 zone coordinates.
- Save/load placement zones as JSON for later auto-generation.
- Generate a first-draft `jersey_color` PNG from front/back colors, side panel colors or images, and a front wordmark image.
- Show raw offsets so later export/replace features can target the right binary regions.

## Photoshop Template Setup

Use Photoshop to create a clean UV guide image for the jersey texture. Export it as PNG, then load it in the Template Editor tab.

Recommended layer style:

- `base_uv`: the actual jersey texture or UV guide.
- `guides`: seams, collar, side panels, shorts boundaries.
- `zones_reference`: optional color-coded blocks for visual planning.

In the app, draw and save named zones such as:

- `front_wordmark`
- `front_number`
- `back_name`
- `back_number`
- `front_chest_logo`
- `shorts_logo`
- `side_stripe_left`
- `side_stripe_right`

For `mastertemplatev1.png`, the Template Editor can detect these color-coded zones automatically:

- blue: `left_side_panel`
- red: `right_side_panel`
- black: `front_wordmark`
- orange/yellow: `collar_background`
- teal: `left_arm_hole_trim`
- green: `right_arm_hole_trim`
- purple: `collar_trim`

The built-in **Load Master Template** uses `mastertemplate2.png`, which includes optional side panel overlays. For `mastertemplate2.png` or `mastertemplate3.png`, use **Detect V3 Colors**:

- bright green: `front_jersey_base`
- sky blue: `back_jersey_base_left` and `back_jersey_base_right`
- blue: `left_side_panel`
- red: `right_side_panel`
- black: `front_wordmark`
- orange/yellow: `collar_background`
- teal: `left_arm_hole_trim`
- green trim: `right_arm_hole_trim`
- purple: `collar_trim`

Template zones also include a `layer` value. Base jersey zones are layer `0`; side panels or stripes are layer `20`; trims are layer `30`; wordmarks, numbers, and logos sit higher. This matches the flat UV wrap: the app paints front/back jersey islands first, then side panels over the top where present.

## Notes

This version reads ZIP-style NBA 2K `.iff` archives directly and falls back to a cautious binary scanner for other variants. It detects DDS/TXTR/RDAT entries, exports internal files to a temp working folder for editing, and can write DDS replacements into a modified `.iff` copy.

Next likely steps:

- Decode packed `.txtr` byte ranges for direct TXTR replacement.
- Decode the exact `.iff` resource table for the target NBA 2K version.
- Add DDS preview thumbnails.
