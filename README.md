# SOP-to-BPMN

Convert structured SOP documents (`.docx`) into BPMN 2.0 XML files that open in [bpmn.io](https://demo.bpmn.io).

```
.docx ── reader ──> [RawStep] ── parser ──> ProcessGraph ── generator ──> .bpmn
```

## Quickstart

```bash
uv venv
uv pip install -e ".[dev]"
.venv/bin/sop-bpmn examples/input_sop.docx examples/output.bpmn
```

`-e .` installs the `sop_bpmn` package editable and registers the `sop-bpmn` console script. `[dev]` adds pytest.

Open `examples/output.bpmn` in [demo.bpmn.io](https://demo.bpmn.io), or use the local viewer:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/viewer/
```

## Architecture

Three layers, one stable abstraction (`ProcessGraph`) in the middle. Reader doesn't know BPMN exists; generator doesn't know `.docx` exists. Swap any layer, the others don't change.

```
┌──────────┐  List[RawStep]  ┌──────────┐  ProcessGraph  ┌──────────┐
│  Reader  │ ──────────────> │  Parser  │ ─────────────> │ Generator│
│ (.docx)  │                 │  (FSM)   │                │  (XML)   │
└──────────┘                 └──────────┘                └──────────┘
```

| Module | Responsibility |
|--------|----------------|
| `sop_bpmn/models.py` | Shared dataclasses: `RawStep`, `ProcessNode`, `SequenceFlow`, `ProcessGraph`, `NodeType`. |
| `sop_bpmn/reader.py` | `python-docx` + regex for manual numbering, `numPr/ilvl` for Word auto-numbered lists, paragraph-per-step fallback. |
| `sop_bpmn/parser/` | State machine (`NORMAL`, `AWAITING_BRANCH`, `IN_BRANCH`) with deferred-gateway pattern. Stack-based for nested conditionals. Split into `patterns.py` (regex), `state.py` (enum + helpers), `core.py` (the FSM class). |
| `sop_bpmn/generator/` | Maps graph to BPMN XML + naive grid layout. Split into `layout.py` (positions), `xml_emit.py` (tag tables, escaping), `core.py` (the orchestrator). |
| `sop_bpmn/cli.py` | CLI that wires the three together; entry point for the `sop-bpmn` console script. |

## How the parser works

**Detection rules** are pure regex, centralized in `sop_bpmn/parser/patterns.py`:
- **Branch step**: line starts with `if yes`, `if no`, `otherwise`
- **Conditional**: line contains `if`, `whether`, `determine`, `check`

**Deferred-gateway pattern**: when a conditional is detected, the gateway is *stashed*, not added to the graph. It only commits when the first branch step arrives. If no branch follows, the conditional is demoted to a regular task — no orphan gateways.

**Implicit merge**: branch tails connect directly to the next non-branch step (multiple incoming flows on a task is valid BPMN). No converging gateway. Matches the example diagram, simpler XML.

**Nested conditionals**: a conditional inside a branch pushes a new frame onto a `gateway_stack` / `branch_tails_stack` pair. Top of stack is always the innermost active gateway. The inner merge pops the frame, and the merge task continues filling the outer branch. See `examples/input_sop_rich.docx` for a worked example.

## Assumptions

1. Steps are numbered in execution order.
2. Numbering can be manual in paragraph text (`"1. Receive email"`) or Word auto-numbering (`numPr/ilvl`). Reader handles both, and falls back to paragraph-per-step when neither is detected.
3. Conditionals contain `if | whether | determine | check`.
4. Branches start with `If yes` / `If no` / `Otherwise`.
5. The next non-branch step at the parent level is the branch merge point. Multi-step branches are extended via continuation lines (`Then…`, `Next…`) or indented sub-steps on separate paragraphs.
6. One Start, one End. Nested conditionals supported. Loops and parallel execution out of scope.

## Known limitations

| Case | Behavior |
|------|----------|
| Multi-step branches in one paragraph (`"If yes, do X. Then do Y."`) | Misroutes — second sentence treated as merge point. Indented sub-steps and continuation lines (`Then…`, `Next…`) on separate paragraphs do chain onto the active branch. |
| Loops, parallel gateways | Not detected. |
| Mid-sentence `if` (`"Notify if available"`) | Triggers a candidate gateway; demoted to task with stderr warning. |
| Empty `.docx` | Pipeline emits minimal `Start → End` graph. |

The error strategy is **fail safe**: ambiguous input becomes a plain task, malformed input still produces a valid (if minimal) BPMN. Warnings go to stderr.

## Project structure

```
sop-bpmn/
├── README.md
├── pyproject.toml              # project metadata, deps, console_script
├── requirements.txt            # legacy mirror of runtime deps; pyproject is source of truth
├── sop_bpmn/                   # the package
│   ├── __init__.py             # re-exports the public surface
│   ├── models.py               # RawStep, ProcessGraph, ProcessNode, SequenceFlow, NodeType
│   ├── reader.py               # DocxReader
│   ├── parser/
│   │   ├── __init__.py         # re-exports SimpleSOPParser, ParserState
│   │   ├── patterns.py         # regex constants
│   │   ├── state.py            # ParserState enum + pure helpers
│   │   └── core.py             # SimpleSOPParser (state machine)
│   ├── generator/
│   │   ├── __init__.py         # re-exports BPMNGenerator, naive_grid_layout
│   │   ├── layout.py           # naive_grid_layout + layout constants
│   │   ├── xml_emit.py         # esc(), NODE_TAGS, SHAPE_SIZES
│   │   └── core.py             # BPMNGenerator (orchestrates layout + XML emit)
│   └── cli.py                  # argparse entry; runs reader → parser → generator
├── tests/
│   ├── test_reader.py
│   ├── test_parser.py
│   ├── test_generator.py
│   └── test_integration.py
├── examples/
│   ├── input_sop.docx          # the brief's 6-step example
│   ├── input_sop_rich.docx     # nested-conditional stress example
│   ├── output.bpmn             # checked-in BPMN for input_sop.docx
│   └── build_sop.py            # regenerates the example .docx files
└── viewer/
    └── index.html              # local bpmn-js viewer
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

27 tests across the four modules: numbered/fallback/`numPr`-nested extraction, state-machine transitions (linear, branching, orphan, nested, open-tails), XML structure (element counts, condition expressions, escaping), and full-pipeline integration.

## Design decisions

| Decision | Why |
|----------|-----|
| `ProcessGraph` as the middle abstraction | Decouples parsing from generation. Either side testable in isolation. |
| State machine over look-ahead | Explicit control flow. "Where am I?" is in one variable. Easier to extend. |
| Rule-based branch detection | Zero training data, transparent, fast. Patterns at top of file — swap freely. |
| Implicit merge (no converging gateway) | Matches example diagram, simpler XML, valid BPMN. |
| Naive grid layout | Brief said perfect layout not required. Enough for bpmn.io to render. |
| No formal interfaces (ABC/Protocol) | Less boilerplate for a prototype. Extract interfaces when a second implementation exists. |

## Future improvements

1. **NLP branch detection** — spaCy dependency parsing for robust conditional/branch detection.
2. **Proper layout** — Sugiyama layered drawing instead of grid.
3. **Parallel gateways and loops** — detect `simultaneously` and `repeat until`.
4. **External config** — YAML for keyword patterns and layout parameters.
5. **XSD validation** — validate output against the BPMN 2.0 schema.
6. **Additional outputs** — Camunda JSON, SVG export.

## Dependencies

```
python-docx==0.8.11
pytest==8.3.3
```

No other external deps. XML generation uses string templating only.
