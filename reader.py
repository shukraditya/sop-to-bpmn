"""Read .docx and emit a List[RawStep] for the parser."""

import re
from typing import List, Optional, Tuple

from docx import Document

from models import RawStep

# Manually-typed numbering patterns, in order of specificity.
# Each pattern: (regex, level). Group(1) = original_number, group(2) = body text.
NUMBER_PATTERNS: List[Tuple[re.Pattern, int]] = [
    (re.compile(r"^(\d+\.)\s+(.*)"), 0),         # "1. text"
    (re.compile(r"^(\(\d+\))\s+(.*)"), 1),       # "(1) text"
    (re.compile(r"^([a-z]\))\s+(.*)", re.I), 1), # "a) text"
]

NUMPR_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _parse_numbering(text: str) -> Optional[Tuple[int, str, str]]:
    for pattern, level in NUMBER_PATTERNS:
        m = pattern.match(text)
        if m:
            return level, m.group(1), m.group(2).strip()
    return None


def _has_numpr(paragraph) -> bool:
    return paragraph._p.find(f".//{NUMPR_NS}numPr") is not None


class DocxReader:
    """Extract numbered steps from a .docx file.

    Strategy: regex match on `paragraph.text` for manual numbering. If any
    paragraph matches, only matched paragraphs become RawSteps. If none match,
    every non-empty paragraph becomes a level-0 step (fallback).

    Auto-numbered Word lists (where the number lives in `pPr/numPr`, not in
    `paragraph.text`) are not handled; the caller should inspect for `numPr`
    on day 1 and either add an extraction path or convert the file.
    """

    def extract_steps(self, path: str) -> List[RawStep]:
        doc = Document(path)
        all_text = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        numbered: List[RawStep] = []
        for text in all_text:
            parsed = _parse_numbering(text)
            if parsed:
                level, orig, body = parsed
                numbered.append(RawStep(level=level, text=body, original_number=orig))

        if numbered:
            return numbered
        return [RawStep(level=0, text=t, original_number="") for t in all_text]


def _inspect(path: str) -> None:
    """Print a day-1 diagnostic on the .docx — paragraph text + numPr presence."""
    doc = Document(path)
    print(f"=== Inspecting {path} ===")
    print(f"Total paragraphs: {len(doc.paragraphs)}")
    auto_count = 0
    for i, p in enumerate(doc.paragraphs):
        text = p.text
        numpr = _has_numpr(p)
        if numpr:
            auto_count += 1
        print(f"  [{i:2}] numPr={numpr} text={text!r}")
    if auto_count:
        print(
            f"\nWARNING: {auto_count} paragraph(s) have numPr (auto-numbered). "
            "If text has no leading number, the regex reader will treat them as unnumbered."
        )


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "examples/input_sop.docx"

    _inspect(path)

    print()
    reader = DocxReader()
    steps = reader.extract_steps(path)
    print(f"Extracted {len(steps)} step(s):")
    for i, s in enumerate(steps):
        print(f"  [{i:2}] level={s.level} num={s.original_number!r} text={s.text!r}")
