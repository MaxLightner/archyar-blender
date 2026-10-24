# Archyar shared project contract — v1.0.0

This directory defines the versioned, transport-independent data contract for sharing one Archyar project between:

- the native Android app (Java / ARCore),
- the Archyar Blender add-on (Python),
- the Archyar web viewer and lightweight web editor.

**Blender v0.8.0 now implements file-based JSON import/export for the supported object kinds listed in the add-on README. This does not yet implement live transport, Android import/export, or browser live viewing.**

## Canonical files

- `project.schema.json`: complete project document and floor metadata.
- `object.schema.json`: stable semantic object identity, parameters and optional custom geometry reference.
- `camera-pose.schema.json`: camera pose in canonical project coordinates.
- `event.schema.json`: transport-independent envelope for snapshots, object changes and camera updates.
- `examples/`: representative project, camera and object-change messages.
- [Coordinate system and adapter rules](../../docs/COORDINATE_SYSTEM.md).

## Core rules

1. Lengths and coordinates are metres.
2. Canonical project axes are right-handed: X/Z are horizontal, +Y is vertical.
3. The project origin is the confirmed reference point on the origin floor. The X direction is the heading established during floor confirmation.
4. Raw ARCore session coordinates are not project coordinates. The Android adapter transforms camera poses into the canonical project frame.
5. Blender's local Z-up frame is converted at the adapter boundary; stored semantic dimensions are not changed to compensate for rendering or AR calibration.
6. Objects and floors have stable UUIDs. Hosted openings refer to their host wall by `hostId`.
7. The semantic parameters are authoritative for editable architectural elements. Generated meshes are presentation geometry, not the source of engineering dimensions.
8. The live preview sends camera poses and scene changes; it does not require continuous video. Initial geometry and changed custom geometry may be transferred as assets, for example GLB.
9. Project revision numbers support conflict detection. Clients must not silently resolve conflicts using device timestamps.

## Message semantics

- `project.snapshot`: `payload.project` contains a complete project document.
- `object.upsert`: `payload.object` contains one complete semantic object.
- `object.delete`: `payload.objectId` and `payload.floorId` identify the deleted object.
- `camera.pose`: `payload` follows `camera-pose.schema.json`.
- `session.joined` / `session.left`: session membership events. Role enforcement belongs to the service, not to a client-supplied field.

The event envelope is deliberately transport-independent. WebSocket, HTTP snapshot transfer or another transport can carry these messages without changing their meaning.

## Versioning

- `schemaVersion: 1` identifies this major wire-contract generation.
- Compatible additions should be optional and covered by tests.
- Removing or changing the meaning of a field, changing axis semantics, or changing units is a breaking change and requires a new major schema version plus a migration plan.
- Every consumer must validate the example fixtures and maintain adapter tests before changing its implementation.

## Validation

From this repository:

```sh
python -m pip install -r requirements-contracts.txt
python -m unittest discover -s tests -v
```

The schemas define the interchange contract; Android's existing binary offline snapshot codec is a separate local backup format and must not be mistaken for this JSON wire format.
