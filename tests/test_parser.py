"""Tests for SimpleSOPParser: state machine + deferred-gateway pattern."""

from models import NodeType, RawStep
from parser import SimpleSOPParser


def _step(text: str) -> RawStep:
    return RawStep(level=0, text=text, original_number="")


def _types(graph) -> list[str]:
    return [n.node_type.value for n in graph.nodes]


def test_linear_sequence_no_gateways():
    steps = [_step("Do A"), _step("Do B"), _step("Do C")]
    g = SimpleSOPParser().parse(steps)
    assert _types(g) == ["start", "task", "task", "task", "end"]
    assert all(f.condition is None for f in g.flows)


def test_conditional_with_two_branches_and_implicit_merge():
    steps = [
        _step("Receive request"),
        _step("Check if the issue is billing-related"),
        _step("If yes, assign to Billing"),
        _step("If no, assign to General"),
        _step("Send acknowledgment"),
    ]
    g = SimpleSOPParser().parse(steps)
    gateways = [n for n in g.nodes if n.node_type == NodeType.EXCLUSIVE_GATEWAY]
    assert len(gateways) == 1
    assert gateways[0].name.endswith("?")

    conditions = sorted(f.condition for f in g.flows if f.condition)
    assert conditions == ["No", "Yes"]

    ack = next(n for n in g.nodes if n.name.startswith("Send acknowledgment"))
    incoming = [f for f in g.flows if f.target_id == ack.id]
    assert len(incoming) == 2  # both branches merge here


def test_orphan_conditional_demoted_to_task():
    steps = [
        _step("Check if it is urgent"),
        _step("Send response"),
    ]
    g = SimpleSOPParser().parse(steps)
    assert NodeType.EXCLUSIVE_GATEWAY not in {n.node_type for n in g.nodes}
    task_names = [n.name for n in g.nodes if n.node_type == NodeType.TASK]
    assert any("urgent" in n.lower() for n in task_names)


def test_open_branches_at_end_connect_to_end():
    steps = [
        _step("Check if it is billing"),
        _step("If yes, route to Billing"),
        _step("If no, route to General"),
    ]
    g = SimpleSOPParser().parse(steps)
    end = next(n for n in g.nodes if n.node_type == NodeType.END)
    incoming_to_end = [f for f in g.flows if f.target_id == end.id]
    assert len(incoming_to_end) == 2  # both open tails


def test_gateway_name_strips_check_prefix():
    steps = [
        _step("Check if the issue is billing-related"),
        _step("If yes, do A"),
        _step("If no, do B"),
        _step("Continue"),
    ]
    g = SimpleSOPParser().parse(steps)
    gateway = next(n for n in g.nodes if n.node_type == NodeType.EXCLUSIVE_GATEWAY)
    assert gateway.name == "The issue is billing-related?"
