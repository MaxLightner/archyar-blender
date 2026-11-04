# POYARA MaxLine — Edit Spline / Edit Poly for Blender

An early, installable Blender add-on for **Blender 4.3+** (designed for 4.4/4.5)
with familiar 3ds Max-style tool groupings in the **POYARA** sidebar.

**This is a functional first beta, not a complete 3ds Max modifier-stack or
Smart Extrude replacement.** Native Blender operators are used where possible.

## Install

1. Download `POYARA-MaxLine-v0.1.0.zip`.
2. Blender → **Edit > Preferences > Add-ons** → dropdown **Install from Disk**.
3. Select the ZIP; enable **POYARA MaxLine | Edit Spline + Edit Poly**.
4. In a 3D View press **N**, then open the **POYARA** tab.

The ZIP contains a single `poyara_maxline/` Python package. No other packages
or network access are required.

## Top-level tabs

| Tab | Tools |
|---|---|
| **Edit Poly** | Mesh sub-object selection; Connect (Segments, Pinch, Slide); numeric Extrude; chamfer/fillet; native inset, bridge, weld, etc. |
| **Edit Line** | Create Line; Max-like point/segment/spline editor; native spline operations; spline fillet/chamfer; vertex XYZ dialog. |
| **Extras** | Three-click Box; non-destructive Boolean controls; Array with copy/instance and rotation; object Align; Box dimensions. |

## Create Line (Max-style)

- In **Object Mode** use **Edit Line > Create Line**.
- **Left Click** adds a point; **Backspace** removes the last new point.
- **C** closes the spline. **Enter** or **Right Click** finishes an open spline.
- **Esc** cancels the current creation.
- Hold **Ctrl** to snap to the grid increment specified in Edit Line.
- Draw with an existing Curve selected to **add another spline to that object**.
- The points are actual Blender **Bezier spline** knots, initially with vector
  handles so the line is straight. Native Blender Curve Edit Mode remains usable.

## Edit Spline (Max-style)

Select a supported Curve and click **Edit Spline | Select + Move**. It temporarily
uses Object Mode to provide consistent hit testing. Use:

- **1** Vertex, **2** Segment, **3** Spline selection levels.
- Click to select; **Shift+Click** multi-select; **drag** a selected item to move.
- **X** deletes at the current level. In Vertex mode, **the incident segments
  are removed and the line breaks**. In Segment mode, the selected edge is
  removed, splitting paths. In Spline mode the selected whole spline is removed.
- **Shift+X** in Vertex mode *dissolves*: deletes knot(s) but connects neighbors.
- **S** changes selected Bezier knots to Smooth (Auto handles).
- **H** changes selected Bezier knots to hard Corner (Vector handles).
- **Enter** or **Right Click** saves; **Esc** discards that edit session.
- To type exact world coordinates after picking a knot, exit the tool and use
  **Vertex XYZ...**. This also works in the normal properties dialog.

For general Ctrl/Alt navigation, Blender's original navigation is preserved.
Curve tools such as Refine, Detach, Reverse and native editable handles are
also available when entering **Native Edit (Tab)**.

## Connect (two opposite edges)

In **Edit Poly**, select exactly **two opposite edges of one quad** in native
Mesh Edit Mode. Press **Connect...** and set:

- **Segments**: 1–30 equally ordered cuts.
- **Pinch**: changes separation between those cuts.
- **Slide**: slides the group along the two chosen edges.

The operator works with selected quad edge pairs; this early version does **not
yet** walk arbitrary edge loops across a whole mesh.

## Three-click Box

In **Object Mode**, open **Extras > Box | 3 Clicks**:

1. Left-click the first corner of the base (world XY plane at the 3D cursor Z).
2. Left-click the diagonally opposite base corner.
3. Move the cursor to set vertical height and left-click again.

Hold Ctrl for snapping. A near-top view uses cursor vertical screen movement
for height. Select a created box and use **Box Parameters** to type dimensions.

## Other tools

- **Boolean**: select exactly two meshes. The **active** mesh is the target;
  the second mesh is the cutter. Difference / Union / Intersect creates a
  real, *non-destructive* Blender Boolean modifier. It can be configured or
  applied right in **Extras**; applying **keeps the cutter**.
- **Array**: specify X/Y/Z counts and local-axis offsets; set incremental
  X/Y/Z rotation. Choose linked instances or independent copies. Maximum
  300 objects per operation. Copy-based for this beta; not a live Array modifier.
- **Align**: select two objects with the **active object as target**, then
  choose axes and min/center/max source and target bounds. Rotation match optional.
- **Extrude**: numeric height and outline in region or individual-face mode.
  **Extrude Manifold** also calls Blender's native tool, but automatic boolean
  cutting like the latest 3ds Max Smart Extrude is **not fully replicated**.
- **Mesh Fillet / Chamfer**: Blender's real bevel operator with segmented or
  single-segment controls.
- **Spline Fillet / Chamfer**: select *Bezier control knots in native Curve Edit
  Mode*, then run these tools. Curve corners use sampled quadratic rounding
  in the beta rather than exact circular arc geometry.

## Status and limitations

- The main goal is **Max-like UX while preserving native Blender geometry**.
- This build has **automated pure-Python topology tests** and syntax validation.
- Runtime GUI interaction in Blender has not yet been manually tested on a
  local Blender executable; please report issues with Blender version and steps.
- Mesh Connect currently supports one quad pair; the native Line creator uses
  a view-oriented plane rather than full Max construction-plane controls.
- Doors, windows, stairs and railings are reserved for a future Extras version.

## Developer checks

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q poyara_maxline
```

The code is self-contained: `poyara_maxline/__init__.py` contains the interface
and Line editor; `extras.py` contains other operators; `topology.py` contains
tested, Blender-independent path splitting/dissolving logic.
