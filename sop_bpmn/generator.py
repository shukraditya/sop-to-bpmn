"""ProcessGraph -> BPMN 2.0 XML with naive grid layout."""

from collections import defaultdict
from typing import Callable, Dict, List, Tuple

from .models import NodeType, ProcessGraph

X_START = 150
X_STEP = 200
Y_CENTER = 200
Y_OFFSET = 100

SHAPE_SIZES: Dict[NodeType, Tuple[int, int]] = {
    NodeType.START: (36, 36),
    NodeType.END: (36, 36),
    NodeType.TASK: (100, 80),
    NodeType.EXCLUSIVE_GATEWAY: (50, 50),
}

NODE_TAGS: Dict[NodeType, str] = {
    NodeType.START: "bpmn:startEvent",
    NodeType.END: "bpmn:endEvent",
    NodeType.TASK: "bpmn:task",
    NodeType.EXCLUSIVE_GATEWAY: "bpmn:exclusiveGateway",
}


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


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


LayoutFn = Callable[[ProcessGraph], Dict[str, Tuple[int, int]]]


class BPMNGenerator:
    """ProcessGraph -> BPMN 2.0 XML string."""

    def __init__(self, layout: LayoutFn = naive_grid_layout):
        self.layout = layout

    def generate(self, graph: ProcessGraph) -> str:
        positions = self.layout(graph)
        process = self._build_process(graph)
        diagram = self._build_diagram(graph, positions)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<bpmn:definitions '
            'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
            'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
            'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
            'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">\n'
            f"{process}{diagram}"
            "</bpmn:definitions>\n"
        )

    def _build_process(self, graph: ProcessGraph) -> str:
        lines: List[str] = ['  <bpmn:process id="Process_1" isExecutable="false">']
        for node in graph.nodes:
            tag = NODE_TAGS[node.node_type]
            lines.append(f'    <{tag} id="{node.id}" name="{_esc(node.name)}"/>')
        for flow in graph.flows:
            attrs = (
                f'id="{flow.id}" '
                f'sourceRef="{flow.source_id}" '
                f'targetRef="{flow.target_id}"'
            )
            if flow.condition:
                attrs += f' name="{_esc(flow.condition)}"'
                lines.append(f"    <bpmn:sequenceFlow {attrs}>")
                lines.append(
                    f'      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
                    f"{_esc(flow.condition)}</bpmn:conditionExpression>"
                )
                lines.append("    </bpmn:sequenceFlow>")
            else:
                lines.append(f"    <bpmn:sequenceFlow {attrs}/>")
        lines.append("  </bpmn:process>\n")
        return "\n".join(lines)

    def _build_diagram(
        self, graph: ProcessGraph, positions: Dict[str, Tuple[int, int]]
    ) -> str:
        lines: List[str] = [
            '  <bpmndi:BPMNDiagram id="BPMNDiagram_1">',
            '    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">',
        ]
        nodes_by_id = {n.id: n for n in graph.nodes}
        for node in graph.nodes:
            cx, cy = positions[node.id]
            w, h = SHAPE_SIZES[node.node_type]
            x = cx - w // 2
            y = cy - h // 2
            lines.append(
                f'      <bpmndi:BPMNShape id="{node.id}_di" bpmnElement="{node.id}">'
            )
            lines.append(f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}"/>')
            lines.append("      </bpmndi:BPMNShape>")
        for flow in graph.flows:
            sx, sy = positions[flow.source_id]
            tx, ty = positions[flow.target_id]
            sw, _ = SHAPE_SIZES[nodes_by_id[flow.source_id].node_type]
            tw, _ = SHAPE_SIZES[nodes_by_id[flow.target_id].node_type]
            x1 = sx + sw // 2
            x2 = tx - tw // 2
            lines.append(
                f'      <bpmndi:BPMNEdge id="{flow.id}_di" bpmnElement="{flow.id}">'
            )
            lines.append(f'        <di:waypoint x="{x1}" y="{sy}"/>')
            lines.append(f'        <di:waypoint x="{x2}" y="{ty}"/>')
            lines.append("      </bpmndi:BPMNEdge>")
        lines.append("    </bpmndi:BPMNPlane>")
        lines.append("  </bpmndi:BPMNDiagram>\n")
        return "\n".join(lines)
