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


def test_mid_sentence_if_treated_as_task():
    """Steps with `if` mid-sentence should be plain tasks, not stashed gateways."""
    steps = [
        _step("Notify the manager if available"),
        _step("Send response"),
    ]
    g = SimpleSOPParser().parse(steps)
    assert NodeType.EXCLUSIVE_GATEWAY not in {n.node_type for n in g.nodes}
    task_names = [n.name for n in g.nodes if n.node_type == NodeType.TASK]
    assert "Notify the manager if available" in task_names
    assert "Send response" in task_names


def test_question_mark_step_is_conditional():
    """A step ending with '?' should trigger a gateway."""
    steps = [
        _step("Receive request"),
        _step("Is the request urgent?"),
        _step("If yes, escalate"),
        _step("If no, queue"),
        _step("Send acknowledgment"),
    ]
    g = SimpleSOPParser().parse(steps)
    gateways = [n for n in g.nodes if n.node_type == NodeType.EXCLUSIVE_GATEWAY]
    assert len(gateways) == 1
    assert gateways[0].name == "Is the request urgent?"


def test_continuation_cue_chains_to_last_branch_tail():
    """`Then ...` after a branch step should chain to that branch's tail, not be the merge."""
    steps = [
        _step("Determine whether to refund"),
        _step("If yes, process the refund"),
        _step("Then send confirmation email"),
        _step("If no, archive the request"),
        _step("Close the case"),
    ]
    g = SimpleSOPParser().parse(steps)

    refund = next(n for n in g.nodes if n.name == "Process the refund")
    confirm = next(n for n in g.nodes if n.name == "Send confirmation email")
    archive = next(n for n in g.nodes if n.name == "Archive the request")
    close = next(n for n in g.nodes if n.name == "Close the case")

    flows_to_confirm = [f for f in g.flows if f.target_id == confirm.id]
    assert len(flows_to_confirm) == 1
    assert flows_to_confirm[0].source_id == refund.id
    assert flows_to_confirm[0].condition is None

    flows_to_close = [f for f in g.flows if f.target_id == close.id]
    assert {f.source_id for f in flows_to_close} == {confirm.id, archive.id}


def test_indent_chains_to_last_branch_tail():
    """A step with level > 0 after a branch should chain to that branch's tail."""
    steps = [
        _step("Determine whether to refund"),
        _step("If yes, process the refund"),
        RawStep(level=1, text="Send confirmation email", original_number="a."),
        _step("If no, archive"),
        _step("Close"),
    ]
    g = SimpleSOPParser().parse(steps)

    refund = next(n for n in g.nodes if n.name == "Process the refund")
    confirm = next(n for n in g.nodes if n.name == "Send confirmation email")

    flows_to_confirm = [f for f in g.flows if f.target_id == confirm.id]
    assert len(flows_to_confirm) == 1
    assert flows_to_confirm[0].source_id == refund.id


def test_multiple_continuations_stack_within_branch():
    """Two consecutive `Then ...` lines should chain X -> Y -> Z within the same branch."""
    steps = [
        _step("Check if escalated"),
        _step("If yes, do X"),
        _step("Then do Y"),
        _step("Then do Z"),
        _step("If no, do W"),
        _step("Close"),
    ]
    g = SimpleSOPParser().parse(steps)

    x = next(n for n in g.nodes if n.name == "Do X")
    y = next(n for n in g.nodes if n.name == "Do Y")
    z = next(n for n in g.nodes if n.name == "Do Z")
    close = next(n for n in g.nodes if n.name == "Close")

    assert next(f for f in g.flows if f.target_id == y.id).source_id == x.id
    assert next(f for f in g.flows if f.target_id == z.id).source_id == y.id
    sources_to_close = {f.source_id for f in g.flows if f.target_id == close.id}
    assert z.id in sources_to_close  # Z (not Y) is the Yes-branch tail at merge
