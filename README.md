# Archyar Blender — 0.5.0

The first installable Archyar modeling add-on for Blender 4.3+ (designed around Blender 4.5). The goal of this stage is **modeling and browsing the shared catalog**. Archyar project import/export is deliberately not included yet.

## Install once

1. Open this repo's **Actions → Archyar Blender add-on package → latest successful run**.
2. Download `archyar-blender-install`, unzip the downloaded *GitHub artifact* once, and keep the inner `archyar-blender-v0.5.0.zip` intact.
3. In Blender: **Edit → Preferences → Add-ons → Install from Disk**, select the inner ZIP, then enable **Archyar — Architectural Modeling**.
4. In any 3D viewport press **N → Archyar**.

For a local build, run `python scripts/build_zip.py` and install `dist/archyar-blender-v0.5.0.zip`. The standard-library test is `python -m unittest discover -s tests -v`.

## Selection and editing: architectural controllers

- **Walls are now semantic Empty controllers**, with a generated mesh child containing the visible wall surface and Boolean modifiers. Doors, windows, stairs and furniture already have semantic Empty roots. Blender still needs mesh data internally to render all of these objects; the generated pieces are implementation details, not user-facing edit targets.
- Selecting the wall surface, a glass pane, jamb, stair tread or furniture part promotes selection to its nearest Archyar controller in Object Mode. Generated mesh transforms are locked. The entire door/window is therefore edited through one Archyar inspector, rather than the individual panes.
- Selecting a wall shows **two blue endpoint gizmos and an orange centre gizmo, all at the wall base**. Drag them in 3D or from above, without picking a point at camera/eye height. Selecting an opening shows five handles: left/right width, offset along host wall, top height and sill.
- **Open 2D Plan Window** duplicates the viewport into a **separate Blender window** and sets that window to top orthographic; the original 3D viewport never rotates. Both show live edits to the same scene. Use **Close 2D Plan Window** to dismiss the separate view.
- Selecting an Archyar element can show a contextual properties popup (toggle **Auto Properties Popup**). Doors/windows expose exact width, height, sill, offset and a live **Open Amount** slider. Use **Insert Open Keyframe** to animate that slider with Blender's normal timeline.
- Existing walls from 0.3 are upgraded to controller roots when the add-on registers or when an older `.blend` is opened. The original wall mesh, its modifiers, its opening objects and its element ID are retained. Save a copy of important `.blend` projects before updating while this migration awaits live Blender tests.

## Modeling

| Group | Current behavior |
| --- | --- |
| Build | Choose 10, 15, or 20 cm wall preset, override thickness and height, then click start/end points on the **active level**. A 3D wall-outline preview follows the cursor. Continue chaining walls; Enter finishes. Wall lengths are always drawn above walls. |
| Openings | Choose fixed/sliding/hinged/arched window or hinged/sliding door; select a wall and see a wireframe model following the intended opening before clicking. Default doors are 0.90 × 2.10 m (as on Android), unless you override the dimensions. A non-destructive Boolean cuts the wall. Select the placed opening to edit width, height, sill, distance from wall start, type, arch rise and opening amount. |
| Furniture | Nine category groups contain the **same 22 catalog items, IDs, and exact dimensions** as the Android app. Every furniture asset follows the cursor as a 3D wire preview before placement. Wall art attaches to a selected Archyar wall. |
| Other elements | Floor, ceiling, column and railing primitives have wire previews. Straight stairs have live-editable run, width, total rise and step count, with a **Filled Underside** checkbox (unchecked initially). |
| Services | Visible as a future category, but actual MEP route drawing is not yet implemented. |

To edit an element later, select its Archyar controller, use the selection popup or expand **Archyar → Selected Archyar Element** and change its properties. For an existing wall use **Set Exact Length** or the native endpoint/base handles. Coincident wall endpoints on the same elevation follow these edits; changes which violate a hosted opening's clearance are rejected. For existing openings saved by v0.1, press **Load Selected Values** before editing. The Build panel has a separate construction grid with a configurable step (10 cm default) and independent **Grid Snap**, **Wall Snap** and **Angle Snap** controls (15° default), plus an **Active Level (Z)** field for storeys. All dimensions are in metres, and **Scene → Units → Unit Scale must be 1.0**.

Door/window, furniture, and structure modes remain active for repeated placement until Esc, with in-viewport preview. The active tool is displayed in the Archyar sidebar. Doors/windows cannot detach from the host wall by moving a mesh; resize/position edits validate bounds and adjacent openings. Changes to width, height, sill and offset use **Apply Opening Changes**, while **Open Amount** animates the generated leaf without rebuilding the wall. Blender's asset picker still uses icon/text lists; richer rendered thumbnail cards are future work.

Blender's visible asset names and UI controls are in English. Stable catalog IDs, geometry dimensions and opening-type codes remain identical to the Android implementation. See [the cross-app model contract](docs/MODEL_CONTRACT.md).

## Updates without reinstalling

Open **N → Archyar → Updates**, and press **Update Archyar from GitHub**. The button checks `MaxLightner/archyar-blender` `main`, downloads new package source, installs only the `archyar_blender` folder and tells you to **restart Blender**. Changes to an already-running Python add-on cannot be safely hot-reloaded.

The source repository is **public**, so no GitHub Access Token is required. Leave any token field in older installed versions empty. The updater checks GitHub only when you press the button; it does not install anything automatically in the background.

The update installs code locally; it neither uploads scenes nor edits the Android app. Its network calls go to the GitHub API. A failed update attempts to roll back the modified files. The initial ZIP generated by GitHub Actions includes its installed commit so an unchanged main branch is recognized.

## Source compatibility and honest limits

- The 22 item IDs, names, categories and width/height/depth are copied from [the private Archyar Android catalog](https://github.com/MaxLightner/archyar/blob/main/apps/android/app/src/main/java/ir/archiyar/domain/FurnitureCatalog.java), based on the Chido procedural geometry. **No GLB model collection exists in that source.** Meshes in Blender are procedural low-poly analogues, not pixel-exact replicas, textures or authored furniture assets.
- Wall presets and the six opening variants correspond to `ToolCatalog.java`. The wall uses editable semantic properties and stable IDs. Archyar-side bidirectional project conversion and topology splitting are future integration tasks, not silently claimed as ready here.
- The Blender vertical axis is Z, while the current Android model uses Y for height; mapping is deferred to the import/export layer.
- Generated mesh children remain present in the Outliner and remain selectable long enough for Blender to detect a click; the selection handler then switches to their controller. This avoids giving users raw mesh modeling tools as the primary editing workflow, but it is **not a security boundary** against deliberate edits in Blender or external scripts.
- The UI is a first prototype; automatic selection promotion, native Gizmo callbacks, old `.blend` migration, Boolean evaluation, and Windows installation still require a real Blender 4.5 viewport test. Pure-Python checks do not prove Blender compatibility. Undo behavior of the new Gizmos also needs a live test; Legacy Drag Mode remains the proven code path for an atomic revert.
