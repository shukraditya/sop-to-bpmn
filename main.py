"""CLI: .docx -> BPMN XML via reader -> parser -> generator."""

import argparse
import sys
from pathlib import Path

from generator import BPMNGenerator
from parser import SimpleSOPParser
from reader import DocxReader


def run(input_path: Path, output_path: Path) -> int:
    if not input_path.exists():
        print(f"error: input not found: {input_path}", file=sys.stderr)
        return 1

    steps = DocxReader().extract_steps(str(input_path))
    if not steps:
        print(f"error: no steps extracted from {input_path}", file=sys.stderr)
        return 1

    graph = SimpleSOPParser().parse(steps)
    xml = BPMNGenerator().generate(graph)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml, encoding="utf-8")

    print(
        f"{input_path} -> {output_path}\n"
        f"  steps: {len(steps)}  nodes: {len(graph.nodes)}  flows: {len(graph.flows)}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert SOP .docx to BPMN XML.")
    ap.add_argument("input", type=Path, help="path to .docx SOP")
    ap.add_argument("output", type=Path, help="path to write .bpmn XML")
    args = ap.parse_args()
    return run(args.input, args.output)


if __name__ == "__main__":
    sys.exit(main())
