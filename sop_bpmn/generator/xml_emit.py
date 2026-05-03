"""XML escape helper, BPMN node tag map, and shape size table."""

from typing import Dict, Tuple

from ..models import NodeType

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


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
