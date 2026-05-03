"""Regex patterns for SOP step classification."""

import re
from typing import List, Tuple

# Anchored to start: a branch step ("If yes...", "If no...", "Otherwise...").
BRANCH_PATTERN = re.compile(r"^(if\s+yes|if\s+no|otherwise)\b", re.I)

# Branch label + body extraction.
BRANCH_LABELS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"^if\s+yes\s*[,:.\-]?\s*(.*)", re.I), "Yes"),
    (re.compile(r"^if\s+no\s*[,:.\-]?\s*(.*)", re.I), "No"),
    (re.compile(r"^otherwise\s*[,:.\-]?\s*(.*)", re.I), "Otherwise"),
]

# Anchored to start: a step that introduces a conditional via verb prefix.
CONDITIONAL_HEAD_PATTERN = re.compile(
    r"^(check|determine|verify|see|find\s+out)\s+(if|whether)\b", re.I
)

# Anchored to start: a step beginning with "whether..." (no leading verb).
WHETHER_HEAD_PATTERN = re.compile(r"^whether\b", re.I)

# Strip leading verbs to derive a clean gateway name.
CONDITION_STRIP = re.compile(
    r"^(check|determine|verify|see|find\s+out)\s+(if|whether)\s+", re.I
)

# Continuation cue + body: "Then send email" -> body="send email".
CONTINUATION_PATTERN = re.compile(
    r"^(?:then|next|after\s+that|followed\s+by|finally)\s*[,:.\-]?\s*(.*)", re.I
)
