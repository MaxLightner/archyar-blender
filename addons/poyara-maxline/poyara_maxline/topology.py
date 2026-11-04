"""Pure spline topology operations, independent of Blender for repeatable tests.

Each point can be an arbitrary object (the add-on uses dictionaries containing
coordinates, handle locations and point attributes). Every result is a list of
``(points, cyclic)`` pairs. Paths with fewer than two knots are discarded.
"""


def _runs(ordered_indices, cut_vertices, points):
    result = []
    current = []
    for index in ordered_indices:
        if index in cut_vertices:
            if len(current) >= 2:
                result.append((current, False))
            current = []
        else:
            current.append(points[index])
    if len(current) >= 2:
        result.append((current, False))
    return result


def break_vertices(points, indices, cyclic=False):
    """Delete knots *and their incident edges*, splitting the remaining path.

    Unlike dissolve, an interior deleted knot never connects its neighbors.
    """
    count = len(points)
    cut = {i for i in indices if 0 <= i < count}
    if not cut:
        return [(list(points), bool(cyclic))] if count >= 2 else []
    if cyclic:
        first_cut = min(cut)
        start = (first_cut + 1) % count
        order = [(start + offset) % count for offset in range(count)]
        return _runs(order, cut, points)
    return _runs(range(count), cut, points)


def dissolve_vertices(points, indices, cyclic=False):
    """Remove knots and connect remaining adjacent knots with new edges."""
    cut = set(indices)
    kept = [point for i, point in enumerate(points) if i not in cut]
    if len(kept) < 2:
        return []
    return [(kept, bool(cyclic and len(kept) >= 3))]


def delete_segments(points, indices, cyclic=False):
    """Delete edges; separate disjoint stretches into independent splines."""
    count = len(points)
    if count < 2:
        return []
    max_edge = count if cyclic else count - 1
    cut = {i for i in indices if 0 <= i < max_edge}
    if not cut:
        return [(list(points), bool(cyclic))]

    if cyclic:
        # Start just after a missing edge. This makes the closed ring a path.
        start = (min(cut) + 1) % count
        ordered = [(start + offset) % count for offset in range(count)]
        result = []
        current = [points[ordered[0]]]
        for j in range(count - 1):
            edge = ordered[j]
            if edge in cut:
                if len(current) >= 2:
                    result.append((current, False))
                current = [points[ordered[j + 1]]]
            else:
                current.append(points[ordered[j + 1]])
        if len(current) >= 2:
            result.append((current, False))
        return result

    result = []
    current = [points[0]]
    for edge in range(count - 1):
        if edge in cut:
            if len(current) >= 2:
                result.append((current, False))
            current = [points[edge + 1]]
        else:
            current.append(points[edge + 1])
    if len(current) >= 2:
        result.append((current, False))
    return result
