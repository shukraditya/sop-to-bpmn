"""BPMNGenerator: ProcessGraph -> BPMN 2.0 XML string."""

from typing import Dict, List, Tuple

from ..models import ProcessGraph
from .layout import LayoutFn, naive_grid_layout
from .xml_emit import NODE_TAGS, SHAPE_SIZES, esc


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
            lines.append(f'    <{tag} id="{node.id}" name="{esc(node.name)}"/>')
        for flow in graph.flows:
            attrs = (
                f'id="{flow.id}" '
                f'sourceRef="{flow.source_id}" '
                f'targetRef="{flow.target_id}"'
            )
            if flow.condition:
                attrs += f' name="{esc(flow.condition)}"'
                lines.append(f"    <bpmn:sequenceFlow {attrs}>")
                lines.append(
                    f'      <bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">'
                    f"{esc(flow.condition)}</bpmn:conditionExpression>"
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
