"""Tests for BPMNGenerator: XML structure + condition expressions."""

import xml.etree.ElementTree as ET

from generator import BPMNGenerator
from models import NodeType, ProcessGraph, ProcessNode, SequenceFlow

NS = {
    "b": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "di": "http://www.omg.org/spec/BPMN/20100524/DI",
}


def _minimal_graph() -> ProcessGraph:
    return ProcessGraph(
        nodes=[
            ProcessNode("StartEvent_1", "Start", NodeType.START),
            ProcessNode("Task_1", "Do work", NodeType.TASK),
            ProcessNode("EndEvent_1", "End", NodeType.END),
        ],
        flows=[
            SequenceFlow("Flow_1", "StartEvent_1", "Task_1"),
            SequenceFlow("Flow_2", "Task_1", "EndEvent_1"),
        ],
    )


def _branching_graph() -> ProcessGraph:
    return ProcessGraph(
        nodes=[
            ProcessNode("StartEvent_1", "Start", NodeType.START),
            ProcessNode("Gateway_1", "Yes?", NodeType.EXCLUSIVE_GATEWAY),
            ProcessNode("Task_1", "Yes path", NodeType.TASK),
            ProcessNode("Task_2", "No path", NodeType.TASK),
            ProcessNode("EndEvent_1", "End", NodeType.END),
        ],
        flows=[
            SequenceFlow("Flow_1", "StartEvent_1", "Gateway_1"),
            SequenceFlow("Flow_2", "Gateway_1", "Task_1", condition="Yes"),
            SequenceFlow("Flow_3", "Gateway_1", "Task_2", condition="No"),
            SequenceFlow("Flow_4", "Task_1", "EndEvent_1"),
            SequenceFlow("Flow_5", "Task_2", "EndEvent_1"),
        ],
    )


def test_generates_parseable_xml():
    xml = BPMNGenerator().generate(_minimal_graph())
    root = ET.fromstring(xml)
    assert root.tag.endswith("definitions")


def test_minimal_graph_element_counts():
    xml = BPMNGenerator().generate(_minimal_graph())
    root = ET.fromstring(xml)
    assert len(root.findall(".//b:startEvent", NS)) == 1
    assert len(root.findall(".//b:task", NS)) == 1
    assert len(root.findall(".//b:endEvent", NS)) == 1
    assert len(root.findall(".//b:sequenceFlow", NS)) == 2


def test_condition_expression_emitted_for_conditional_flows():
    xml = BPMNGenerator().generate(_branching_graph())
    root = ET.fromstring(xml)
    flows = root.findall(".//b:sequenceFlow", NS)
    with_cond = [f for f in flows if f.find("b:conditionExpression", NS) is not None]
    assert len(with_cond) == 2
    labels = sorted(f.find("b:conditionExpression", NS).text for f in with_cond)
    assert labels == ["No", "Yes"]


def test_diagram_has_shape_per_node_and_edge_per_flow():
    graph = _branching_graph()
    xml = BPMNGenerator().generate(graph)
    root = ET.fromstring(xml)
    shapes = root.findall(".//{http://www.omg.org/spec/BPMN/20100524/DI}BPMNShape")
    edges = root.findall(".//{http://www.omg.org/spec/BPMN/20100524/DI}BPMNEdge")
    assert len(shapes) == len(graph.nodes)
    assert len(edges) == len(graph.flows)


def test_xml_escapes_special_chars_in_names():
    graph = ProcessGraph(
        nodes=[
            ProcessNode("StartEvent_1", "Start", NodeType.START),
            ProcessNode("Task_1", "A & B < C", NodeType.TASK),
            ProcessNode("EndEvent_1", "End", NodeType.END),
        ],
        flows=[
            SequenceFlow("Flow_1", "StartEvent_1", "Task_1"),
            SequenceFlow("Flow_2", "Task_1", "EndEvent_1"),
        ],
    )
    xml = BPMNGenerator().generate(graph)
    root = ET.fromstring(xml)  # crashes if escaping is wrong
    task = root.find(".//b:task", NS)
    assert task.attrib["name"] == "A & B < C"
