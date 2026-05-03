"""SimpleSOPParser: state machine that builds a ProcessGraph from RawSteps."""

import sys
from typing import Dict, List, Optional, Tuple

from ..models import NodeType, ProcessGraph, ProcessNode, RawStep, SequenceFlow
from .state import (
    ParserState,
    extract_branch,
    extract_gateway_name,
    is_branch,
    is_conditional,
    strip_continuation,
    strip_period,
)


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
        # Stacks: gateway_stack[i] is the gateway whose branches we're filling at depth i.
        # branch_tails_stack[i] holds the open branch tails for that gateway.
        # Top of stack == innermost (currently active) gateway.
        self.gateway_stack: List[str] = []
        self.branch_tails_stack: List[List[str]] = []
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
        branch_step = is_branch(text)
        conditional_step = (not branch_step) and is_conditional(text)

        if self.state == ParserState.NORMAL:
            if conditional_step:
                self.pending_gateway = (extract_gateway_name(text), self.last_node_id)
                self.state = ParserState.AWAITING_BRANCH
            else:
                self._add_task_after(self.last_node_id, strip_period(text))

        elif self.state == ParserState.AWAITING_BRANCH:
            branch = extract_branch(text)
            if branch:
                self._commit_pending_gateway()
                label, body = branch
                task_id = self._add_node(body, NodeType.TASK)
                self._add_flow(self.gateway_stack[-1], task_id, condition=label)
                self.branch_tails_stack[-1].append(task_id)
                self.last_node_id = task_id
                self.state = ParserState.IN_BRANCH
            else:
                self._discard_pending_gateway_as_task()
                self._handle_step(step)  # Re-enter handler in NORMAL or IN_BRANCH state.

        elif self.state == ParserState.IN_BRANCH:
            branch = extract_branch(text)
            if branch:
                label, body = branch
                task_id = self._add_node(body, NodeType.TASK)
                self._add_flow(self.gateway_stack[-1], task_id, condition=label)
                self.branch_tails_stack[-1].append(task_id)
                self.last_node_id = task_id
            elif conditional_step:
                # Nested: the current branch tail becomes the source of an inner gateway.
                # Remove it from outer tails — it's no longer "open" once inner attaches.
                top_tails = self.branch_tails_stack[-1]
                source = top_tails.pop() if top_tails else self.gateway_stack[-1]
                self.pending_gateway = (extract_gateway_name(text), source)
                self.state = ParserState.AWAITING_BRANCH
            else:
                cont_body, is_continuation = strip_continuation(text)
                if (is_continuation or step.level > 0) and self.branch_tails_stack[-1]:
                    self._chain_to_last_branch_tail(strip_period(cont_body))
                    return
                self._merge_branches_into(strip_period(text))

    def _add_task_after(self, source_id: str, name: str) -> None:
        task_id = self._add_node(name, NodeType.TASK)
        self._add_flow(source_id, task_id)
        self.last_node_id = task_id

    def _commit_pending_gateway(self) -> None:
        assert self.pending_gateway is not None
        gateway_name, source_id = self.pending_gateway
        gateway_id = self._add_node(gateway_name, NodeType.EXCLUSIVE_GATEWAY)
        self._add_flow(source_id, gateway_id)
        self.gateway_stack.append(gateway_id)
        self.branch_tails_stack.append([])
        self.pending_gateway = None

    def _discard_pending_gateway_as_task(self) -> None:
        assert self.pending_gateway is not None
        gateway_name, source_id = self.pending_gateway
        task_name = gateway_name.rstrip("?")
        self._add_task_after(source_id, task_name)
        self.pending_gateway = None
        if self.gateway_stack:
            # Demoted task lives inside an outer branch — re-attach as branch tail.
            self.branch_tails_stack[-1].append(self.last_node_id)
            self.state = ParserState.IN_BRANCH
        else:
            self.state = ParserState.NORMAL
        print(
            f"  warning: conditional {gateway_name!r} had no following branches; "
            "demoted to task",
            file=sys.stderr,
        )

    def _merge_branches_into(self, name: str) -> None:
        task_id = self._add_node(name, NodeType.TASK)
        inner_tails = self.branch_tails_stack.pop()
        self.gateway_stack.pop()
        for tail in inner_tails:
            self._add_flow(tail, task_id)
        self.last_node_id = task_id
        if self.gateway_stack:
            # Inner merge inside outer branch — task continues outer's current branch.
            self.branch_tails_stack[-1].append(task_id)
            self.state = ParserState.IN_BRANCH
        else:
            self.state = ParserState.NORMAL

    def _chain_to_last_branch_tail(self, name: str) -> None:
        """Extend the most recently added branch with another task. Tail moves to it."""
        task_id = self._add_node(name, NodeType.TASK)
        top_tails = self.branch_tails_stack[-1]
        tail = top_tails[-1]
        self._add_flow(tail, task_id)
        top_tails[-1] = task_id
        self.last_node_id = task_id

    def _finalize(self) -> None:
        if self.state == ParserState.AWAITING_BRANCH and self.pending_gateway is not None:
            self._discard_pending_gateway_as_task()

        end_id = self._add_node("End", NodeType.END)

        if self.gateway_stack:
            # Mid-branch (any depth) at EOF — drain every open tail across the stack to End.
            for tails in self.branch_tails_stack:
                for tail in tails:
                    self._add_flow(tail, end_id)
            self.gateway_stack.clear()
            self.branch_tails_stack.clear()
            self.state = ParserState.NORMAL
        else:
            self._add_flow(self.last_node_id, end_id)
