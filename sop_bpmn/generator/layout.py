"""Naive grid layout: assigns (x, y) coordinates to ProcessGraph nodes."""

from collections import defaultdict
from typing import Callable, Dict, List, Tuple

from ..models import NodeType, ProcessGraph

X_START = 150
X_STEP = 200
Y_CENTER = 200
Y_OFFSET = 100

LayoutFn = Callable[[ProcessGraph], Dict[str, Tuple[int, int]]]


def naive_grid_layout(graph: ProcessGraph) -> Dict[str, Tuple[int, int]]:
    """Compute (center_x, center_y) for each node.

    X = level * X_STEP + X_START, where level = longest path from Start.
    Y = Y_CENTER by default. Sibling branches off the same gateway are offset
    around Y_CENTER. Merge nodes (multiple incoming flows) return to Y_CENTER.
    """
    out_edges: Dict[str, List[str]] = defaultdict(list)
    in_edges: Dict[str, List[str]] = defaultdict(list)
    for flow in graph.flows:
        out_edges[flow.source_id].append(flow.target_id)
        in_edges[flow.target_id].append(flow.source_id)

    nodes_by_id = {n.id: n for n in graph.nodes}
    start = next((n for n in graph.nodes if n.node_type == NodeType.START), None)
    if start is None:
        return {n.id: (X_START, Y_CENTER) for n in graph.nodes}

    levels: Dict[str, int] = {start.id: 0}
    changed = True
    while changed:
        changed = False
        for node_id, targets in list(out_edges.items()):
            if node_id not in levels:
                continue
            for target in targets:
                new_level = levels[node_id] + 1
                if levels.get(target, -1) < new_level:
                    levels[target] = new_level
                    changed = True

    for node in graph.nodes:
        levels.setdefault(node.id, 0)

    positions: Dict[str, Tuple[int, int]] = {}
    for node in graph.nodes:
        x = X_START + levels[node.id] * X_STEP
        y = Y_CENTER
        sources = in_edges.get(node.id, [])
        if len(sources) == 1:
            src = nodes_by_id.get(sources[0])
            if src and src.node_type == NodeType.EXCLUSIVE_GATEWAY:
                siblings = out_edges[src.id]
                if len(siblings) > 1:
                    idx = siblings.index(node.id)
                    n = len(siblings)
                    if n == 2:
                        y = Y_CENTER + (Y_OFFSET if idx == 0 else -Y_OFFSET)
                    else:
                        offset = (idx - (n - 1) / 2) * Y_OFFSET
                        y = int(Y_CENTER + offset)
        positions[node.id] = (x, y)

    return positions
