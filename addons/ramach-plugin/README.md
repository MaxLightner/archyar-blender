# Ramach Plugin v0.1.0 — Blender 4.3+

Small, isolated starting point for the unified Ramach Blender plugin. It does **not** replace or modify POYARA MaxLine or Archyar tools.

## Install

1. Download `ramach-plugin-v0.1.0.zip` and **do not unzip it**.
2. Blender → Edit → Preferences → Add-ons → **Install from Disk** → select the ZIP → enable **Ramach Plugin**.
3. Open any 3D Viewport → press **N** → **Ramach** tab → **Layout**.

## Import

- Use **Import / Drop Model**, or drag a `.glb`, `.gltf`, `.fbx` or `.obj` into the **3D Viewport**. Blender's own file-drop handlers can compete for the same extension; the sidebar Import button is the reliable fallback.
- **Merge by Distance** runs by default per imported mesh, with an editable initial threshold of `0.0001` Blender units (0.1 mm for meter-scale scenes). It does not merge separate objects or erase intentional gaps. Models must have sane scale for this distance to be meaningful.
- **Try Recover Quads** is disabled by default. OBJ and FBX can retain quadrangles when the original source has them; GLB/glTF mesh triangles do not encode the original quad topology. This optional step attempts to combine pairs of triangles; it cannot perfectly reconstruct a quad retopology.
- **Bottom-Center Pivot + Z=0** creates a non-rendering Empty as the asset root at the bottom-center of the combined imported geometry. All imported pieces are parented with world positions preserved, and the assembled model sits on ground level. Existing pieces/materials remain separate. Select the `RM_..._ROOT` Empty to move the whole asset.
- In **Model Dimensions**, width/depth/height fields edit the selected model root. With **Lock Proportions** on (default), changing any field scales all 3 dimensions together. Turn it off for non-uniform scaling.
- The panel reports the final triangle/quad polygon counts and number of welded vertices. Blender can display triangulated GLB geometry even if upstream Tripo retopology was quads.

## Update

Open **Ramach → Updates → Update from GitHub**. The updater checks only source commits under `addons/ramach-plugin/ramach_plugin` on `MaxLightner/archyar-blender`, downloads the public repository archive, extracts only this add-on's `.py`/`.json`/`.txt` files, validates paths/size, stages the update and keeps a `ramach-plugin-previous.zip` backup in the add-ons directory. It does not touch Archyar or MaxLine. Blender must be restarted to use the updated code.

## Build / test

From this directory:

```bash
python3 build_zip.py
blender --background --factory-startup --python tests/smoke.py
```

The automatic import and FileHandler are exercised by the smoke script; operating-system drag events still need interactive Blender testing.
