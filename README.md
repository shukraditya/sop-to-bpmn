# SOP-to-BPMN

Convert structured SOP documents (`.docx`) into BPMN 2.0 XML files that open in [bpmn.io](https://demo.bpmn.io).

```
.docx ── reader ──> [RawStep] ── parser ──> ProcessGraph ── generator ──> .bpmn
```

## Quickstart

```bash
uv venv
uv pip install -r requirements.txt
.venv/bin/python main.py examples/input_sop.docx examples/output.bpmn
```

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
| `models.py` | Shared dataclasses: `RawStep`, `ProcessNode`, `SequenceFlow`, `ProcessGraph`, `NodeType`. |
| `reader.py` | `python-docx` + regex. Pulls numbered steps from paragraph text. Falls back to paragraph-per-step. |
| `parser.py` | State machine (`NORMAL`, `AWAITING_BRANCH`, `IN_BRANCH`) with deferred-gateway pattern. |
| `generator.py` | Maps graph to BPMN XML + naive grid layout (X by topological level, Y for branch siblings). |
| `main.py` | CLI that wires the three together. |

## How the parser works

**Detection rules** are pure regex, centralized at the top of `parser.py`:
- **Branch step**: line starts with `if yes`, `if no`, `otherwise`
- **Conditional**: line contains `if`, `whether`, `determine`, `check`

**Deferred-gateway pattern**: when a conditional is detected, the gateway is *stashed*, not added to the graph. It only commits when the first branch step arrives. If no branch follows, the conditional is demoted to a regular task — no orphan gateways.

**Implicit merge**: branch tails connect directly to the next non-branch step (multiple incoming flows on a task is valid BPMN). No converging gateway. Matches the example diagram, simpler XML.

## Assumptions

1. Steps are numbered in execution order.
2. Manual numbering in paragraph text (`"1. Receive email"`), not Word's auto-numbering (`numPr`). Reader has a `_inspect()` diagnostic to detect this on day one.
3. Conditionals contain `if | whether | determine | check`.
4. Branches start with `If yes` / `If no` / `Otherwise`.
5. Branches are single-step. The next non-branch line is the merge point.
6. One Start, one End, no nested conditionals, no loops, no parallel execution.

## Known limitations

| Case | Behavior |
|------|----------|
| Multi-step branches (`"If yes, do X. Then do Y."`) | Misroutes — second step treated as merge point. |
| Nested conditionals | State machine has no stack; not handled. |
| Loops, parallel gateways | Not detected. |
| Mid-sentence `if` (`"Notify if available"`) | Triggers a candidate gateway; demoted to task with stderr warning. |
| Auto-numbered Word lists | Reader falls back to paragraph-per-step. |
| Empty `.docx` | Pipeline emits minimal `Start → End` graph. |

The error strategy is **fail safe**: ambiguous input becomes a plain task, malformed input still produces a valid (if minimal) BPMN. Warnings go to stderr.

## Project structure

```
sop-bpmn/
├── README.md
├── requirements.txt
├── main.py                # CLI entry
├── models.py              # dataclasses
├── reader.py              # DocxReader
├── parser.py              # SimpleSOPParser (state machine)
├── generator.py           # BPMNGenerator + layout
├── tests/
│   ├── conftest.py
│   ├── test_reader.py
│   ├── test_parser.py
│   ├── test_generator.py
│   └── test_integration.py
├── examples/
│   ├── input_sop.docx
│   └── output.bpmn
└── viewer/
    └── index.html         # local bpmn-js viewer
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

16 tests across the four modules: numbered/fallback extraction, state-machine transitions (linear, branching, orphan, open-tails), XML structure (element counts, condition expressions, escaping), and full-pipeline integration.

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
3. **Nested conditionals** — stack-based state machine or recursive descent.
4. **Parallel gateways and loops** — detect `simultaneously` and `repeat until`.
5. **`numPr` extraction** — handle auto-numbered Word lists.
6. **External config** — YAML for keyword patterns and layout parameters.
7. **XSD validation** — validate output against the BPMN 2.0 schema.
8. **Additional outputs** — Camunda JSON, SVG export.

## Dependencies

```
python-docx==0.8.11
pytest==8.3.3
```

No other external deps. XML generation uses string templating only.
