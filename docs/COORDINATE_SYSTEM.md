# Archyar shared coordinate system

This document is normative for the v1 shared project contract. The machine-readable project and object formats live in [contracts/v1](../contracts/v1/README.md).

## Canonical project frame

- **Units:** metres. One coordinate unit is one real metre.
- **Handedness:** right-handed.
- **Up axis:** +Y.
- **Ground plane:** X/Z.
- **Origin:** (0, 0, 0) is the reference point on the origin floor that the user confirms when establishing the project.
- **Heading:** +X is the direction established by the floor-confirmation/reference-heading step. +Z completes the right-handed horizontal frame.
- **Floor elevation:** a floor's `elevation` is its Y coordinate in the project frame. Geometry remains in metric project coordinates when AR display scale or Maquette scale changes.

The project frame is an engineering frame, not the raw tracking frame of one device. The Android app must transform ARCore session poses through its calibrated floor/reference frame before publishing a camera pose. Recreating or resetting an ARCore session must not silently redefine project geometry.

## Adapter mappings

### Android / ARCore

The current Android model already stores horizontal coordinates as X/Z and height as Y. Use the calibrated `ReferenceFrame` to convert between ARCore world metres and project coordinates. Do not store screen pixels, raw session-local camera coordinates, or display scale as engineering dimensions.

### Blender

Blender's standard scene is Z-up, with X/Y as the ground plane. Convert at the adapter boundary using this position mapping:

```text
blender = (projectX, -projectZ, projectY)
project  = (blenderX, blenderZ, -blenderY)
```

The sign change preserves a right-handed frame. Do not simply swap Y and Z without the sign change. For rotations, convert through a rotation matrix using the same basis transform; do not swap quaternion components by inspection. Blender's local mesh generation and UI may remain Z-up.

### Web viewer

Use the canonical project frame directly with a Y-up renderer. The viewer's virtual camera position is expressed in project metres, not CSS pixels. The camera quaternion is ordered `[x, y, z, w]`; each renderer adapter must also account for its camera-local forward-axis convention.

## Floor confirmation and camera streaming

1. The user confirms the floor/reference point and heading in Archyar.
2. The app retains the transform between the current ARCore session and the canonical project frame.
3. Camera poses are converted into project coordinates before being published.
4. The website renders the same scene from that pose. It does not need the physical camera background.
5. A floor switch requires the app to use the appropriate floor calibration; it does not change the shared coordinate system or rescale stored objects.

The contract's `originFloorId` identifies the project floor whose reference point defines the origin. Other floor elevations and all objects are expressed in the same project frame.

## Object semantics and identity

- Project, floor, object, host and session IDs are UUIDs.
- A semantic wall is identified by its object ID and metric parameters, not by its generated mesh.
- An opening's `hostId` identifies its wall; `hostT` is the fraction along that wall from its start (0 to 1).
- Wall `parameters.start` and `parameters.end` are horizontal `[X, Z]` pairs; `baseElevation` is the wall base along +Y.
- Custom geometry can reference a GLB/GLTF asset with a URI and SHA-256 checksum. Geometry assets may be transferred on initial load or when the geometry changes; camera updates do not retransmit the entire model.

## Realtime event rules

- `sequence` increases monotonically within a sender session.
- `timestampMs` on a camera pose is monotonic within that session; it is not a wall-clock time.
- `baseRevision` identifies the project revision a change was based on. A stale revision must be surfaced as a conflict; clients must not silently overwrite newer changes.
- The event transport is not fixed by this contract. WebSocket is a candidate for low-volume live events; HTTP can carry initial snapshots and geometry assets.
- Viewer/Editor/Owner authorization is enforced by the service. Client-supplied role labels are not proof of permission.

This contract defines the data and coordinate rules only. It does not yet implement project transport, Blender import/export, web editing, or live camera streaming.
