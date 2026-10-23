# Archyar modeling contract — v0.2.0

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

Stair-filled state is represented in Android's existing `WorkspaceModel.Item.style` string, already saved by `ProjectSnapshotCodec` version 1. No snapshot schema migration is needed. Blender stores the equivalent as `archyar_stair_style`. The apps do not yet exchange objects; this documents their matching logic for future import/export.

Current intentional differences: Android retains Persian RTL UI; Blender uses English UI because built-in Blender fonts are unsuitable for Persian. Preview rendering detail and furniture low-poly mesh construction are platform-specific. The 3D visual correctness of both still needs in-app device testing.
