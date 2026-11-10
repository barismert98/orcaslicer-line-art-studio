"""Joins points into one line that never crosses itself and never runs into its own width."""
from __future__ import annotations

import math

from .stipple import Stop, never

NEIGHBORS = 8
CLEAN_ROUNDS = 40
_HILBERT_CELLS = 65536


class TourError(ValueError):
    """The line could not be made clean."""


def _hilbert_index(x: int, y: int) -> int:
    index = 0
    step = _HILBERT_CELLS // 2
    while step > 0:
        rx = 1 if x & step else 0
        ry = 1 if y & step else 0
        index += step * step * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = _HILBERT_CELLS - 1 - x, _HILBERT_CELLS - 1 - y
            x, y = y, x
        step //= 2
    return index


def _nearest(points: list, side: float) -> list:
    """For each point, its NEIGHBORS closest points, closest first."""
    count = len(points)
    wanted = min(NEIGHBORS, count - 1)
    cell = side / max(1, int(math.sqrt(count / 3)))
    cells: dict = {}
    for index, (x, y) in enumerate(points):
        cells.setdefault((int(x / cell), int(y / cell)), []).append(index)
    result = []
    for index, (x, y) in enumerate(points):
        cx, cy = int(x / cell), int(y / cell)
        ring = 1
        while True:
            found = sorted(
                ((points[j][0] - x) ** 2 + (points[j][1] - y) ** 2, j)
                for a in range(cx - ring, cx + ring + 1)
                for b in range(cy - ring, cy + ring + 1)
                for j in cells.get((a, b), ())
                if j != index
            )
            reach = (ring * cell) ** 2
            if ring * cell > side * 1.5 or (len(found) >= wanted and found[wanted - 1][0] <= reach):
                result.append([j for _, j in found[:wanted]])
                break
            ring += 1
    return result


def _two_opt(points: list, side: float, stop: Stop) -> list:
    """A closed tour started from a Hilbert ordering and improved by 2-opt over near neighbors."""
    count = len(points)
    top = _HILBERT_CELLS - 1
    tour = sorted(range(count), key=lambda i: _hilbert_index(int(points[i][0] / side * top), int(points[i][1] / side * top)))
    place = [0] * count
    for position, city in enumerate(tour):
        place[city] = position
    nearby = _nearest(points, side)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    def dist(a: int, b: int) -> float:
        return math.hypot(xs[a] - xs[b], ys[a] - ys[b])

    def reverse(i: int, j: int) -> None:
        inner = (j - i + 1) % count
        if inner * 2 > count:
            i, j = (j + 1) % count, (i - 1) % count
            inner = count - inner
        for _ in range(inner // 2):
            a, b = tour[i], tour[j]
            tour[i], tour[j] = b, a
            place[b], place[a] = i, j
            i = (i + 1) % count
            j = (j - 1) % count

    queue = list(tour)
    queued = [True] * count
    done = 0
    while queue:
        done += 1
        if done % 2048 == 0:
            stop()
        a = queue.pop()
        queued[a] = False
        changed = True
        while changed:
            changed = False
            for forward in (True, False):
                step = 1 if forward else -1
                b = tour[(place[a] + step) % count]
                ab = dist(a, b)
                for c in nearby[a]:
                    ac = dist(a, c)
                    if ac >= ab:
                        break
                    d = tour[(place[c] + step) % count]
                    if c == b or d == a:
                        continue
                    if ab + dist(c, d) - ac - dist(b, d) > 1e-9:
                        if forward:
                            reverse(place[b], place[c])
                        else:
                            reverse(place[c], place[b])
                        for city in (b, c, d):
                            if not queued[city]:
                                queued[city] = True
                                queue.append(city)
                        changed = True
                        break
                if changed:
                    break
    return tour


def _open_at_longest_edge(points: list, tour: list) -> list:
    count = len(tour)
    longest = max(range(count), key=lambda i: math.dist(points[tour[i]], points[tour[(i + 1) % count]]))
    return [points[i] for i in tour[longest + 1 :] + tour[: longest + 1]]


def _pairs(path: list, reach: float) -> set:
    """Pairs of non-neighboring segments that may be within `reach` of each other."""
    cell = max(reach * 4, 0.5)
    cells: dict = {}
    for index, ((ax, ay), (bx, by)) in enumerate(zip(path, path[1:])):
        for i in range(int((min(ax, bx) - reach) // cell), int((max(ax, bx) + reach) // cell) + 1):
            for j in range(int((min(ay, by) - reach) // cell), int((max(ay, by) + reach) // cell) + 1):
                cells.setdefault((i, j), []).append(index)
    pairs = set()
    for members in cells.values():
        for u, s in enumerate(members):
            for t in members[u + 1 :]:
                if abs(s - t) >= 2:
                    pairs.add((min(s, t), max(s, t)))
    return pairs


def _orient(p, q, r) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _crosses(a, b, c, d) -> bool:
    return _orient(a, b, c) * _orient(a, b, d) < 0 and _orient(c, d, a) * _orient(c, d, b) < 0


def _point_gap(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else min(1.0, max(0.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def crossings(path: list, reach: float = 1.0) -> list:
    """Every (s, t) where segment s crosses segment t, s < t, sorted."""
    return sorted(
        (s, t) for s, t in _pairs(path, reach) if _crosses(path[s], path[s + 1], path[t], path[t + 1])
    )


def crowded(path: list, width: float) -> set:
    """Indices of points that sit closer than a line width to a segment they do not belong to."""
    found = set()
    for s, t in _pairs(path, width):
        for point, a, b in (
            (s, t, t + 1), (s + 1, t, t + 1), (t, s, s + 1), (t + 1, s, s + 1),
        ):
            if point in (a, b) or abs(point - a) < 2 or abs(point - b) < 2:
                continue
            if _point_gap(path[point], path[a], path[b]) < width:
                found.add(point)
    return found


def clean(path: list, width: float, stop: Stop = never) -> list:
    """Uncrosses the line, then removes points that would put two strands on top of each other."""
    path = list(path)
    for _ in range(CLEAN_ROUNDS):
        stop()
        crossed = crossings(path)
        if crossed:
            end = -1
            for s, t in crossed:
                if s > end:  # reversals over separate stretches do not disturb each other
                    path[s + 1 : t + 1] = path[s + 1 : t + 1][::-1]
                    end = t
            continue
        close = crowded(path, width)
        if not close:
            return path
        path = [p for i, p in enumerate(path) if i not in close]
        if len(path) < 2:
            break
    raise TourError("The line could not be cleaned up. Change the size or the detail spacing slightly.")


def route(points: list, side: float, width: float, stop: Stop = never) -> list:
    """One open line through the points; they are in 0..side on both axes."""
    if len(points) < 4:
        return list(points)
    return clean(_open_at_longest_edge(points, _two_opt(points, side, stop)), width, stop)
