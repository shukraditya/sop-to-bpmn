"""Cross-module data types for the SOP-to-BPMN pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class NodeType(Enum):
    START = "start"
    END = "end"
    TASK = "task"
    EXCLUSIVE_GATEWAY = "exclusiveGateway"


@dataclass
class RawStep:
    level: int
    text: str
    original_number: str


@dataclass
class ProcessNode:
    id: str
    name: str
    node_type: NodeType


@dataclass
class SequenceFlow:
    id: str
    source_id: str
    target_id: str
    condition: Optional[str] = None


@dataclass
class ProcessGraph:
    nodes: List[ProcessNode] = field(default_factory=list)
    flows: List[SequenceFlow] = field(default_factory=list)
