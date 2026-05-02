"""SOP RawSteps -> ProcessGraph via state machine with deferred-gateway pattern."""

import re
import sys
from enum import Enum
from typing import Dict, List, Optional, Tuple

from models import NodeType, ProcessGraph, ProcessNode, RawStep, SequenceFlow

# Anchored to start: a branch step ("If yes...", "If no...", "Otherwise...").
BRANCH_PATTERN = re.compile(r"^(if\s+yes|if\s+no|otherwise)\b", re.I)

# Branch label + body extraction.
BRANCH_LABELS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^if\s+yes\s*[,:.\-]?\s*(.*)", re.I), "Yes"),
    (re.compile(r"^if\s+no\s*[,:.\-]?\s*(.*)", re.I), "No"),
    (re.compile(r"^otherwise\s*[,:.\-]?\s*(.*)", re.I), "Otherwise"),
]

# Anywhere in step: a conditional trigger that creates a gateway.
CONDITIONAL_PATTERN = re.compile(r"\b(if|whether|determine|check)\b", re.I)

# Strip leading verbs to derive a clean gateway name.
CONDITION_STRIP = re.compile(
    r"^(check|determine|verify|see|find\s+out)\s+(if|whether)\s+", re.I
)


class ParserState(Enum):
    NORMAL = "normal"
    AWAITING_BRANCH = "awaiting"
    IN_BRANCH = "in_branch"


def _strip_period(text: str) -> str:
    text = text.strip()
    if text.endswith("."):
        text = text[:-1].rstrip()
    return text


def _capitalize(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _extract_gateway_name(text: str) -> str:
    body = CONDITION_STRIP.sub("", text).strip()
    body = _strip_period(body)
    body = _capitalize(body)
    if not body.endswith("?"):
        body += "?"
    return body


def _extract_branch(text: str) -> Optional[Tuple[str, str]]:
    for pattern, label in BRANCH_LABELS:
        m = pattern.match(text)
        if m:
            body = _strip_period(_capitalize(m.group(1).strip()))
            return label, body
    return None


def _is_branch(text: str) -> bool:
    return BRANCH_PATTERN.match(text) is not None


def _is_conditional(text: str) -> bool:
    return CONDITIONAL_PATTERN.search(text) is not None


class SimpleSOPParser:
    """RawSteps -> ProcessGraph via state machine with deferred-gateway pattern.

    The gateway is *stashed* (not added to the graph) when a conditional is
    detected, and only committed when the first branch step arrives. If no
    branch follows, the conditional is demoted to a regular task — no orphan
    gateway is left in the graph.
    """

    def parse(self, steps: List[RawStep]) -> ProcessGraph:
        self._reset()
        start_id = self._add_node("Start", NodeType.START)
        self.last_node_id = start_id
        for step in steps:
            self._handle_step(step)
        self._finalize()
        return self.graph

    def _reset(self) -> None:
        self.graph = ProcessGraph()
        self.state: ParserState = ParserState.NORMAL
        self.last_node_id: str = ""
        self.pending_gateway: Optional[Tuple[str, str]] = None
        self.current_gateway_id: Optional[str] = None
        self.current_branch_tails: List[str] = []
        self._counters: Dict[NodeType, int] = {nt: 0 for nt in NodeType}
        self._flow_counter: int = 0

    def _add_node(self, name: str, node_type: NodeType) -> str:
        self._counters[node_type] += 1
        prefix = {
            NodeType.START: "StartEvent",
            NodeType.END: "EndEvent",
            NodeType.TASK: "Task",
            NodeType.EXCLUSIVE_GATEWAY: "Gateway",
        }[node_type]
        node_id = f"{prefix}_{self._counters[node_type]}"
        self.graph.nodes.append(ProcessNode(id=node_id, name=name, node_type=node_type))
        return node_id

    def _add_flow(
        self, source_id: str, target_id: str, condition: Optional[str] = None
    ) -> None:
        self._flow_counter += 1
        flow_id = f"Flow_{self._flow_counter}"
        self.graph.flows.append(
            SequenceFlow(
                id=flow_id, source_id=source_id, target_id=target_id, condition=condition
            )
        )

    def _handle_step(self, step: RawStep) -> None:
        text = step.text
        is_branch = _is_branch(text)
        is_conditional = (not is_branch) and _is_conditional(text)

        if self.state == ParserState.NORMAL:
            if is_conditional:
                self.pending_gateway = (_extract_gateway_name(text), self.last_node_id)
                self.state = ParserState.AWAITING_BRANCH
            else:
                self._add_task_after(self.last_node_id, _strip_period(text))

        elif self.state == ParserState.AWAITING_BRANCH:
            branch = _extract_branch(text)
            if branch:
                self._commit_pending_gateway()
                label, body = branch
                task_id = self._add_node(body, NodeType.TASK)
                assert self.current_gateway_id is not None
                self._add_flow(self.current_gateway_id, task_id, condition=label)
                self.current_branch_tails = [task_id]
                self.last_node_id = task_id
                self.state = ParserState.IN_BRANCH
            else:
                self._discard_pending_gateway_as_task()
                self._handle_step(step)  # Re-enter handler in NORMAL state.

        elif self.state == ParserState.IN_BRANCH:
            branch = _extract_branch(text)
            if branch:
                label, body = branch
                task_id = self._add_node(body, NodeType.TASK)
                assert self.current_gateway_id is not None
                self._add_flow(self.current_gateway_id, task_id, condition=label)
                self.current_branch_tails.append(task_id)
            else:
                if is_conditional:
                    print(
                        f"  warning: conditional step {text!r} at merge point; "
                        "treating as task",
                        file=sys.stderr,
                    )
                self._merge_branches_into(_strip_period(text))

    def _add_task_after(self, source_id: str, name: str) -> None:
        task_id = self._add_node(name, NodeType.TASK)
        self._add_flow(source_id, task_id)
        self.last_node_id = task_id

    def _commit_pending_gateway(self) -> None:
        assert self.pending_gateway is not None
        gateway_name, source_id = self.pending_gateway
        gateway_id = self._add_node(gateway_name, NodeType.EXCLUSIVE_GATEWAY)
        self._add_flow(source_id, gateway_id)
        self.current_gateway_id = gateway_id
        self.pending_gateway = None

    def _discard_pending_gateway_as_task(self) -> None:
        assert self.pending_gateway is not None
        gateway_name, source_id = self.pending_gateway
        task_name = gateway_name.rstrip("?")
        self._add_task_after(source_id, task_name)
        self.pending_gateway = None
        self.state = ParserState.NORMAL
        print(
            f"  warning: conditional {gateway_name!r} had no following branches; "
            "demoted to task",
            file=sys.stderr,
        )

    def _merge_branches_into(self, name: str) -> None:
        task_id = self._add_node(name, NodeType.TASK)
        for tail in self.current_branch_tails:
            self._add_flow(tail, task_id)
        self.current_branch_tails = []
        self.current_gateway_id = None
        self.last_node_id = task_id
        self.state = ParserState.NORMAL

    def _finalize(self) -> None:
        if self.state == ParserState.AWAITING_BRANCH and self.pending_gateway is not None:
            self._discard_pending_gateway_as_task()

        end_id = self._add_node("End", NodeType.END)

        if self.state == ParserState.IN_BRANCH and self.current_branch_tails:
            for tail in self.current_branch_tails:
                self._add_flow(tail, end_id)
            self.current_branch_tails = []
            self.current_gateway_id = None
            self.state = ParserState.NORMAL
        else:
            self._add_flow(self.last_node_id, end_id)


def _example_steps() -> List[RawStep]:
    return [
        RawStep(level=0, text="Receive customer support email", original_number="1."),
        RawStep(level=0, text="Check if the issue is billing-related", original_number="2."),
        RawStep(level=0, text="If yes, assign to Billing Queue", original_number="3."),
        RawStep(level=0, text="If no, assign to General Support Queue", original_number="4."),
        RawStep(level=0, text="Send acknowledgment email to customer", original_number="5."),
        RawStep(level=0, text="Close the triage step", original_number="6."),
    ]


if __name__ == "__main__":
    steps = _example_steps()
    graph = SimpleSOPParser().parse(steps)

    print(f"Nodes ({len(graph.nodes)}):")
    for n in graph.nodes:
        print(f"  {n.id:<14} [{n.node_type.value}] {n.name!r}")
    print(f"\nFlows ({len(graph.flows)}):")
    for f in graph.flows:
        cond = f" [{f.condition}]" if f.condition else ""
        print(f"  {f.id:<8} {f.source_id} -> {f.target_id}{cond}")
