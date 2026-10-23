# Archyar modeling contract — v0.5.0

This contract applies to both `MaxLightner/archyar-blender` and `MaxLightner/archyar`.
Any behavioral change to an opening, wall, stair or catalog asset must be reviewed in **both** repositories, even before model import/export is enabled.

| Feature | Shared semantic rule |
| --- | --- |
| Units | One model unit is one metre. Blender draws on XY and uses Z for height; Android uses X/Z and Y for height. |
| Furniture | `chido-0` through `chido-21`: same category, dimensions (width, height, depth), and semantic index. Mesh algorithms may differ. |
| Windows | `fixed`, `sliding`, `hinged`, `arched`. |
| Doors | `door`, `sliding-door`; sill must be 0–1 cm. |
| Opening position | Wall-relative fraction from 0 to 1; leave 10 cm clearance at each end and 5 cm between openings. Width ≥30 cm; opening height ≥30 cm; sill ≥0; opening must fit wall height. |
| Arch rise | Only `arched` accepts a positive rise, 5 cm to 65% of opening height. |
| Stair geometry | Straight run along the base plane, width perpendicular, positive rise, `count` treads. Each tread occupies `run/count`, at height `(index+1)*rise/count`. |
| Stair bounds | Run ≥0.5 m, width 0.5–5 m, rise 0.15–9 m, count 1–50, step rise 0.10–0.22 m, tread depth ≥0.20 m. |
| Underside | `stair-open` (default for newly created stairs): each tread is 5 cm thick and underside is open. `stair-filled`: every step extends to ground. |
| Legacy stair | Missing/`plain` stair style in an older Android project remains **filled**. Existing stored projects must never change shape silently. |
| Live preview | Cursor/reticle shows the actual footprint, wall-hosted opening width, or visible 3D ghost before confirmation; confirmation is a separate action. |
| Wall handles | Move a wall's start/end or whole segment using on-canvas handles. Coincident connected endpoints at the same level move together. Validate wall length (≥10 cm), hosted opening clearances and existing locks **before** committing; one gesture is one Undo step. |
| Wall numeric length | Post-drawing numeric length edit must allow a fixed start or end. The other connected joint follows; never require a numeric length before drawing. |
| Floor grid | A metric reference plane independent of calibration and project coordinates, with a separately configurable snap behavior. Blender uses a configurable default 10 cm interval; Android's plan and AR overlay use 25 cm subdivisions and 1 m major lines. Floor/storey elevation selects the current editing plane. |
| AR plane visualization | Only the centered circular floor marker and an unbounded, thin metric grid: no ARCore detected-plane polygon and no circular fading mask. Camera hit-test tracking may still rely on ARCore plane polygons internally. |
| Semantic selection | A wall, door, window or furniture item is selected as one Archyar element with stable ID and parameter metadata, regardless of the number of generated render mesh pieces. Geometry must not become the authoritative source of dimensions. |
| 2D plan | Blender top orthographic is a distinct view of the same X/Y semantic model, with architectural wall outlines and opening markers. It must not duplicate or recalculate model coordinates and must coexist with the 3D view. |
| Independent plan viewport | Blender opens the orthographic plan in a separate window without changing the 3D viewport. Both show the same live scene/controller data, rather than duplicating building geometry. |
| Angular drawing snap | Wall endpoints first snap to nearby valid wall nodes, otherwise optional grid snap and quantized heading (default 15°) are used. The two editors offer their own toggle and step controls. |
| Hosted opening edits | Every door/window retains its original wall ID. Width and centre-offset changes are validated together against wall ends and adjacent openings; moving/resizing a wall cannot strand an opening. Deleting a wall also deletes dependent openings. |
| Opening manipulation | Selected openings expose left/right width endpoints and a centre-position handle. Blender additionally exposes sill and top-height handles. A selected wall's endpoint/translation controls remain at ground level, never at eye-height. |
| Open/close behavior | Blender offers a keyed open-fraction slider (native animation F-curves) and never auto-opens by user distance. Android AR can animate hinged/sliding doors/windows when the camera approaches, then close when leaving, without mutating persisted openFraction or creating history entries. |
| Context editing | Selecting a semantic wall/opening exposes its metric inspector in both Android plan and AR; Blender exposes a contextual properties popup. The parent host and model validations remain authoritative. |

Stair-filled state is represented in Android's existing `WorkspaceModel.Item.style` string, already saved by `ProjectSnapshotCodec` version 1. No snapshot schema migration is needed. Blender stores the equivalent as `archyar_stair_style`. The apps do not yet exchange objects; this documents their matching logic for future import/export.

Current intentional differences: Android retains Persian RTL UI; Blender uses English UI because built-in Blender fonts are unsuitable for Persian. Preview rendering detail and furniture low-poly mesh construction are platform-specific. Blender's wall joints are currently inferred by equal XY endpoints at the same Z elevation; Android persists stable node IDs and automatically splits at junctions. Both reject invalid connected edits. Blender catalog cards use its existing icon picker, and Android uses the same visual palette in plan and AR. The AR drag gesture now maps touched ground-level markers through a calibrated floor-plane ray and validates the edit on release; its usability and proximity tuning require real device verification. The 3D visual correctness of both still needs in-app device testing.
