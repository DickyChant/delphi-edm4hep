#!/usr/bin/env python3
"""Render the collection map as a single self-contained HTML page.

Nodes are collections, one per angular slot on a ring, grouped into a sector
per domain and coloured by it. The ring radius follows from the number of
nodes, so labels cannot collide however many collections there are. Edges are
the links between them; a parallel array sits beside the collection it
parallels, tied to it.

The page shell, style and script live in assets/ and are inlined here, so the
result is one file with no external requests.

Usage:
    render.py --map map.json [--out page.html] [--publish DIR]
"""
import argparse
import json
import math
import shutil
from pathlib import Path

LINE = 16.0                  # arc reserved per label, in SVG units
MIN_R = 300.0                # ring radius floor, for looks at small N
CHAR = 6.3                   # label character width at the label font size
ORBIT = 0.45                 # inner-hub radius, as a fraction of the ring
PARALLEL = 1.07              # parallel-array radius, as a fraction of the ring
STACK = 16.0                 # line spacing for a hub's parallel-array list

# Physics subgroups within a domain, matched against the readable part of the
# name. Keywords rather than collection names, so a new collection joins the
# right group without an edit here. Anything unmatched keeps the domain order.
SUBGROUPS = (
    ("Muon",        ("Muon",)),
    ("Electron",    ("Electron",)),
    ("Photon/Pi0",  ("PhotonID", "Pi0ID")),
    ("dE/dx",       ("Dedx", "dEdx")),
    ("RICH",        ("Rich",)),
)

# The two collections everything else hangs off. Named rather than derived:
# the structure is stable, and a rule to pick them out is more machinery than
# the fact deserves. Matched on bank and readable name, so the prefix is free
# to change.
CENTRE_OF = ("MAIN", "Particles")
ORBIT_OF = (("TRAC", "Tracks"),)

# The frame parameters are not a collection; they get one node of their own.
FRAME_NODE = "podio::Frame"

PALETTE = {
    "Tracking":    "#3b7dd8",
    "Calorimeter": "#e2703a",
    "Pid":         "#2f9e6e",
    "Vertex":      "#9b59b6",
    "Truth":       "#c0392b",
    "Btag":        "#b58900",
    "Event":       "#607d8b",
}

ASSETS = Path(__file__).resolve().parent / "assets"


def nodes_of(m):
    """Every node on the page: the collections, plus one for the parameters."""
    nodes = {name: {"domain": c["domain"], "frame": False,
                    "companion_of": c["companion_of"], "flavour": c["prefix"]}
             for name, c in m["collections"].items()}
    nodes[FRAME_NODE] = {"domain": "Event", "frame": True,
                         "companion_of": None, "flavour": "none"}
    return nodes


def _named(m, wanted):
    """Resolve (bank, readable) pairs to the collection names in this file."""
    return [name for name, c in m["collections"].items()
            if (c["bank"], c["readable"]) in wanted]


def degrees(m, nodes):
    """Links touching each node, in either direction."""
    degree = {name: 0 for name in nodes}
    for link in m["links"]:
        for end in (link["from"], link["to"]):
            if end in degree:
                degree[end] += 1
    return degree


def _polar(angle, radius):
    rad = math.radians(angle)
    return radius * math.cos(rad), radius * math.sin(rad), angle


def _grouped(members, m):
    """A domain's ring members, split into labelled physics subgroups.

    Returns [(label, [names])]; the unmatched remainder comes last, unlabelled.
    """
    left, groups = list(members), []
    for label, keywords in SUBGROUPS:
        hit = [n for n in left
               if any(k in m["collections"].get(n, {}).get("readable", "")
                      for k in keywords)]
        if hit:
            groups.append((label, sorted(hit)))
            left = [n for n in left if n not in hit]
    if left:
        groups.append(("", sorted(left)))
    return groups


def _hub_stack(hx, hy, count, drop):
    """Where a hub's parallel arrays go: listed under the hub's own label, on
    the side away from the centre."""
    side = 1 if hx >= 0 else -1
    return [(hx + side * 10, hy + drop + i * STACK, side) for i in range(count)]


def layout(m, nodes, degree):
    """Slots on a ring, sized so labels cannot collide.

    Each ring node claims one unit of arc and each subgroup a gap, so the
    sectors follow their real content. A parallel array sits beside the
    collection it parallels: in the next slot, just outside the ring, or in a
    short list beside a hub.
    """
    centre = next(iter(_named(m, {CENTRE_OF})), None)
    inner = [n for n in _named(m, set(ORBIT_OF)) if n != centre]
    pinned = set(inner) | {centre}

    children = {}
    for name, node in nodes.items():
        if node["companion_of"]:
            children.setdefault(node["companion_of"], []).append(name)
    ring = [n for n in nodes if n not in pinned and not nodes[n]["companion_of"]]

    by_domain = {}
    for name in ring:
        by_domain.setdefault(nodes[name]["domain"], []).append(name)

    plan, units = {}, 0.0
    for domain, members in by_domain.items():
        groups = _grouped(members, m)
        slots = sum(1 + len(children.get(n, [])) for n in members)
        plan[domain] = (groups, slots + len(groups) - 1)
        units += slots + len(groups) - 1
    radius = max(MIN_R, LINE * len(ring) / (2 * math.pi))
    step = 360.0 / units

    positions = {centre: (0.0, 0.0, 0.0)} if centre else {}
    sectors, arcs, stacked, start = {}, [], {}, -90.0
    for domain in sorted(plan):
        groups, weight = plan[domain]
        sectors[domain] = (start, start + weight * step)

        cursor = 0.0
        for label, members in groups:
            first = start + (cursor + 0.5) * step
            for name in members:
                positions[name] = _polar(start + (cursor + 0.5) * step, radius)
                cursor += 1
                for child in sorted(children.get(name, [])):
                    positions[child] = _polar(start + (cursor + 0.5) * step,
                                              PARALLEL * radius)
                    cursor += 1
            if label:
                arcs.append((label, domain, first, start + (cursor - 0.5) * step))
            cursor += 1                       # gap between subgroups
        start += weight * step

    for name in inner:
        a0, a1 = sectors.get(nodes[name]["domain"], (0.0, 360.0))
        positions[name] = _polar((a0 + a1) / 2, ORBIT * radius)

    for hub in [centre, *inner]:
        kids = sorted(children.get(hub, []))
        if not kids:
            continue
        hx, hy, _ = positions[hub]
        drop = (14 if hub == centre else 10) + 34      # clear of the hub label
        for name, (x, y, side) in zip(kids, _hub_stack(hx, hy, len(kids), drop)):
            positions[name] = (x, y, 0.0)
            stacked[name] = side

    return positions, sectors, arcs, stacked, centre, inner, radius


def _wedge(a0, a1, inner, outer):
    """SVG path for a sector band."""
    (x0, y0, _), (x1, y1, _) = _polar(a0, outer), _polar(a1, outer)
    (x2, y2, _), (x3, y3, _) = _polar(a1, inner), _polar(a0, inner)
    big = 1 if a1 - a0 > 180 else 0
    return (f"M{x0:.1f},{y0:.1f} A{outer:.1f},{outer:.1f} 0 {big} 1 {x1:.1f},{y1:.1f} "
            f"L{x2:.1f},{y2:.1f} A{inner:.1f},{inner:.1f} 0 {big} 0 {x3:.1f},{y3:.1f} Z")


def _curve(p, q, pull=0.45):
    """A link, bowed toward the centre so long chords stay clear of the ring."""
    cx, cy = (p[0] + q[0]) / 2 * pull, (p[1] + q[1]) / 2 * pull
    return f"M{p[0]:.1f},{p[1]:.1f} Q{cx:.1f},{cy:.1f} {q[0]:.1f},{q[1]:.1f}"


def _short(name, parent):
    """A parallel array's distinguishing suffix; the tie says whose it is."""
    return (name[len(parent) + 1:] if name.startswith(parent + "_")
            else name.split("_")[-1])


def _label_text(name, m):
    """Prefix and bank plain, the collection name in bold: that is what is
    being looked for, the rest are lookup keys."""
    if name not in m["collections"]:
        return f'<tspan class="strong">{name}</tspan>'
    readable = m["collections"][name]["readable"]
    return (f'<tspan class="dim">{name[:-len(readable)]}</tspan>'
            f'<tspan class="strong">{readable}</tspan>')


def _blocks(nodes, positions, stacked, centre, inner):
    """What a sector label has to keep out of: the hubs, their own labels, and
    their parallel-array lists."""
    boxes = []
    for name, side in stacked.items():
        x, y, _ = positions[name]
        width = CHAR * 0.9 * len(_short(name, nodes[name]["companion_of"])) + 14
        boxes.append((min(x, x + side * width), max(x, x + side * width),
                      y - 9, y + 9))
    for hub in [centre, *inner]:
        if hub not in positions:
            continue
        x, y, _ = positions[hub]
        size = 14 if hub == centre else 10
        half = CHAR * 1.15 * len(hub) / 2
        boxes.append((x - half, x + half, y - size - 6, y + size + 26))
    return boxes


def _clear(x, y, boxes):
    return not any(x0 <= x <= x1 and y0 <= y <= y1 for x0, x1, y0, y1 in boxes)


def svg(m, nodes, positions, sectors, arcs, stacked, centre, inner, radius):
    """Sector bands, subgroup arcs, links, ties, and one group per node."""
    boxes = _blocks(nodes, positions, stacked, centre, inner)
    extent = radius + CHAR * max(len(n) for n in nodes) + 40
    box = f"{-extent:.0f} {-extent:.0f} {2 * extent:.0f} {2 * extent:.0f}"
    out = [f'<svg id="graph" viewBox="{box}">', '<g id="sectors">']

    for domain, (a0, a1) in sectors.items():
        colour = PALETTE[domain]
        out.append(f'<path class="wedge" data-domain="{domain}" fill="{colour}" '
                   f'd="{_wedge(a0, a1, 0.30 * radius, 1.04 * radius)}"/>')
        # Mid-angle, stepping along and then further out if a hub is there.
        for reach in (0.62, 0.76):
            for fraction in (0.50, 0.28, 0.72, 0.15, 0.85):
                x, y, _ = _polar(a0 + fraction * (a1 - a0), reach * radius)
                if _clear(x, y, boxes):
                    break
            if _clear(x, y, boxes):
                break
        out.append(f'<text class="sector" x="{x:.1f}" y="{y:.1f}" '
                   f'fill="{colour}">{domain}</text>')
    out.append('</g><g id="arcs">')

    for label, domain, a0, a1 in arcs:
        colour = PALETTE[domain]
        (x0, y0, _), (x1, y1, _) = (_polar(a0, 0.93 * radius),
                                    _polar(a1, 0.93 * radius))
        big = 1 if a1 - a0 > 180 else 0
        out.append(f'<path class="arc" stroke="{colour}" fill="none" '
                   f'd="M{x0:.1f},{y0:.1f} A{0.93 * radius:.1f},'
                   f'{0.93 * radius:.1f} 0 {big} 1 {x1:.1f},{y1:.1f}"/>')
        mid = (a0 + a1) / 2
        x, y, _ = _polar(mid, 0.88 * radius)
        spin = mid + 90
        if 90 < spin % 360 < 270:
            spin += 180
        out.append(f'<text class="arclabel" x="{x:.1f}" y="{y:.1f}" '
                   f'fill="{colour}" transform="rotate({spin:.1f} '
                   f'{x:.1f} {y:.1f})">{label}</text>')
    out.append('</g><g id="links">')

    for link in m["links"]:
        a, b = link["from"], link["to"]
        if a not in positions or b not in positions or a == b:
            continue
        out.append(f'<path class="link" data-from="{a}" data-to="{b}" '
                   f'd="{_curve(positions[a], positions[b])}"/>')
    out.append('</g><g id="ties">')

    for name, node in nodes.items():
        parent = node["companion_of"]
        if parent and parent in positions and name in positions:
            (x, y, _), (px, py, _) = positions[name], positions[parent]
            out.append(f'<line class="tie" data-name="{name}" data-parent="{parent}" '
                       f'x1="{x:.1f}" y1="{y:.1f}" x2="{px:.1f}" y2="{py:.1f}" '
                       f'stroke="{PALETTE[node["domain"]]}"/>')
    out.append('</g><g id="nodes">')

    for name, node in nodes.items():
        x, y, angle = positions[name]
        colour = PALETTE[node["domain"]]
        parent = node["companion_of"]
        size = 14 if name == centre else (10 if name in inner
                                          else (3.5 if parent else 6))
        turn = 90 < (angle % 360) < 270
        classes = "node" + (" companion" if parent else "")
        if node["frame"]:
            text = (f'<tspan class="strong">{FRAME_NODE}</tspan>'
                    f'<tspan class="dim"> ({len(m["parameters"])} parameters)'
                    f'</tspan>')
        elif parent:
            text = _short(name, parent)
        else:
            text = _label_text(name, m)

        provenance = m["collections"].get(name, {}).get("provenance", "")
        out.append(f'<g class="{classes}" data-name="{name}" '
                   f'data-domain="{node["domain"]}" '
                   f'data-provenance="{provenance}" '
                   f'data-flavour="{node["flavour"]}">')
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size}" '
                   f'fill="{colour}" stroke="{colour}"/>')
        if name == centre or name in inner:
            out.append(f'<text class="label pinned" x="{x:.1f}" '
                       f'y="{y + size + 16:.1f}">{text}</text>')
        elif name in stacked:
            side = stacked[name]
            out.append(f'<text class="label" '
                       f'text-anchor="{"start" if side > 0 else "end"}" '
                       f'x="{x + side * 7:.1f}" y="{y + 4:.1f}">{text}</text>')
        else:
            # Ring labels point outward, parallel-array labels inward, so the
            # two never run into each other.
            anchor = "end" if turn else "start"
            offset = -(size + 6) if turn else (size + 6)
            out.append(f'<text class="label" text-anchor="{anchor}" '
                       f'x="{offset:.1f}" y="3" '
                       f'transform="translate({x:.1f},{y:.1f}) '
                       f'rotate({angle + (180 if turn else 0):.1f})">{text}</text>')
        out.append('</g>')
    out.append('</g></svg>')
    return "\n".join(out)


def page(m, nodes, positions, sectors, arcs, stacked, centre, inner, radius):
    samples = ", ".join(f'{s["label"]} ({s["events"]})' for s in m["samples"])
    intro = (f"<p>{len(nodes)} nodes, {len(m['links'])} links, "
             f"{len(m['collections'])} collections.</p>"
             f"<p>Measured on: {samples}.</p>"
             "<p>Click a node for its links; click the background to clear.</p>")
    legend = "".join(
        f'<div class="key" data-domain="{d}"><span style="background:'
        f'{PALETTE[d]}"></span>{d}</div>' for d in m["domains"])
    return (ASSETS / "page.html").read_text().format(
        style=(ASSETS / "page.css").read_text(),
        script=(ASSETS / "page.js").read_text(),
        svg=svg(m, nodes, positions, sectors, arcs, stacked, centre, inner, radius),
        legend=legend,
        intro=intro,
        intro_json=json.dumps(intro),
        data=json.dumps(m),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--map", required=True)
    parser.add_argument("--out", default="collection_map.html")
    parser.add_argument("--publish", help="directory to copy the page into")
    args = parser.parse_args()

    m = json.loads(Path(args.map).read_text())
    nodes = nodes_of(m)
    degree = degrees(m, nodes)
    (positions, sectors, arcs, stacked,
     centre, inner, radius) = layout(m, nodes, degree)
    Path(args.out).write_text(
        page(m, nodes, positions, sectors, arcs, stacked, centre, inner, radius))
    if args.publish:
        shutil.copy(args.out, Path(args.publish) / Path(args.out).name)
    print(f"{args.out}: {len(nodes)} nodes, {len(m['links'])} links, "
          f"ring radius {radius:.0f}")


if __name__ == "__main__":
    main()
