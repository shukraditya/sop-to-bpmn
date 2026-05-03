"""Parser state enum and pure text-classification helpers."""

from enum import Enum
from typing import Optional, Tuple

from .patterns import (
    BRANCH_LABELS,
    BRANCH_PATTERN,
    CONDITION_STRIP,
    CONDITIONAL_HEAD_PATTERN,
    CONTINUATION_PATTERN,
    WHETHER_HEAD_PATTERN,
)


class ParserState(Enum):
    NORMAL = "normal"
    AWAITING_BRANCH = "awaiting"
    IN_BRANCH = "in_branch"


def strip_period(text: str) -> str:
    text = text.strip()
    if text.endswith("."):
        text = text[:-1].rstrip()
    return text


def capitalize(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def extract_gateway_name(text: str) -> str:
    body = CONDITION_STRIP.sub("", text).strip()
    body = strip_period(body)
    body = capitalize(body)
    if not body.endswith("?"):
        body += "?"
    return body


def extract_branch(text: str) -> Optional[Tuple[str, str]]:
    for pattern, label in BRANCH_LABELS:
        m = pattern.match(text)
        if m:
            body = strip_period(capitalize(m.group(1).strip()))
            return label, body
    return None


def strip_continuation(text: str) -> Tuple[str, bool]:
    """If text starts with a continuation cue, return (cue-stripped body, True).
    Otherwise return (text, False). Empty body counts as no match (fall through)."""
    m = CONTINUATION_PATTERN.match(text)
    if m:
        body = capitalize(m.group(1).strip())
        if body:
            return body, True
    return text, False


def is_branch(text: str) -> bool:
    return BRANCH_PATTERN.match(text) is not None


def is_conditional(text: str) -> bool:
    text = text.strip()
    if CONDITIONAL_HEAD_PATTERN.match(text) or WHETHER_HEAD_PATTERN.match(text):
        return True
    return text.rstrip(".").endswith("?")
