"""Metric geometry rules mirrored from Archyar's Java domain layer.

Any change here must be checked against WorkspaceModel.Floor before release.
"""

import math


STAIR_OPEN = "stair-open"
STAIR_FILLED = "stair-filled"
STAIR_TREAD_THICKNESS = .05


def stair_valid(run, width, rise, count):
    return (all(math.isfinite(v) for v in (run, width, rise))
            and run >= .5 and .5 <= width <= 5 and .15 <= rise <= 9
            and isinstance(count, int) and 1 <= count <= 50
            and .10 <= rise / count <= .22 and run / count >= .20)


def require_stair(run, width, rise, count):
    if not stair_valid(run, width, rise, count):
        raise ValueError("Stair run, width, total rise or step count is out of Archyar bounds")


def opening_position(wall_length, wall_height, width, height, sill, style,
                     rise, fraction, siblings=()):
    """Validate and return a clamped host fraction; siblings are (t,width) pairs."""
    vals = (wall_length, wall_height, width, height, sill, rise, fraction)
    if not all(math.isfinite(v) for v in vals):
        raise ValueError("Opening has non-finite dimensions")
    if (width < .3 or height < .3 or sill < 0 or width > wall_length - .20
            or sill + height > wall_height):
        raise ValueError("Opening does not fit the host wall")
    if style in ("door", "sliding-door") and sill > .01:
        raise ValueError("Doors must have zero sill height")
    if style == "arched" and not .05 <= rise <= height * .65:
        raise ValueError("Arched windows require a valid arch rise")
    if style != "arched" and rise != 0:
        raise ValueError("Only arched windows can have arch rise")
    if not 0 <= fraction <= 1:
        raise ValueError("Opening position is out of wall range")
    margin = (width / 2 + .1) / wall_length
    t = max(margin, min(1 - margin, fraction))
    for other_t, other_width in siblings:
        if abs((t - other_t) * wall_length) < (width + other_width) / 2 + .05:
            raise ValueError("Openings cannot overlap")
    return t
