# CLAUDE.md — SOP-to-BPMN Prototype

## Project

Build a prototype that transforms structured SOP documents (.docx) into BPMN 2.0 XML files that open in bpmn.io.

## Architecture

Three-layer pipeline with a central graph abstraction:

```
.docx → Reader → [RawStep list] → Parser → [ProcessGraph] → Generator → .bpmn
```

- **Reader**: extracts numbered steps from .docx (python-docx + regex fallback)
- **Parser**: state machine that detects conditionals/branches, builds ProcessGraph
- **Generator**: maps ProcessGraph to BPMN XML + minimal diagram coordinates

## Key Design Decisions

1. **ProcessGraph is the stable abstraction** — decouples parsing from generation. Parser doesn't know BPMN, Generator doesn't know .docx.
2. **State machine parser** — explicit states (NORMAL, AWAITING_BRANCH, IN_BRANCH) instead of look-ahead. Easier to explain and extend.
3. **Rule-based branch detection** — regex keywords, zero training data. Patterns centralized at top of parser module for easy modification.
4. **Implicit merge** — branch tails connect directly to next task (no converging gateway). Matches the example diagram, simpler XML.
5. **Naive grid layout** — X by topological level, Y by position. Enough for bpmn.io to render. Not pretty, but brief says perfect layout not required. Merge step (first non-branch node after a gateway) returns to Y=center and X advances past the branch column to avoid overlap with branch tasks.
6. **No formal interfaces** — manual composition in main.py. Less boilerplate for a 36-hour prototype. Extract ABC/Protocol when second implementation exists.

## Data Model

### RawStep (Reader output)

```python
@dataclass
class RawStep:
    level: int          # 0 = "1.", 1 = "a.", etc.
    text: str           # step text content
    original_number: str  # preserve "1.", "a)", etc.
```

### ProcessGraph (Parser output, Generator input)

```python
class NodeType(Enum):
    START = "start"
    END = "end"
    TASK = "task"
    EXCLUSIVE_GATEWAY = "exclusiveGateway"

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
    condition: Optional[str] = None   # "Yes", "No", etc.

@dataclass
class ProcessGraph:
    nodes: List[ProcessNode]
    flows: List[SequenceFlow]
```

## Parser State Machine

```python
class ParserState(Enum):
    NORMAL = "normal"
    AWAITING_BRANCH = "awaiting"
    IN_BRANCH = "in_branch"
```

Parser-instance fields (alongside `state: ParserState`):

```python
last_node_id: str                          # source for next sequence flow
pending_gateway: Optional[tuple[str, str]] # (gateway_name, source_node_id); set in AWAITING_BRANCH only
current_gateway_id: Optional[str]          # set when IN_BRANCH
current_branch_tails: list[str]            # branch task ids to merge at next non-branch step
```

State enum is the control variable; these fields are the data the transitions read and write.

Transitions:
- NORMAL → conditional → AWAITING_BRANCH (stash *pending* gateway: candidate name + source node id; **do not add to graph yet**)
- AWAITING_BRANCH → branch step → IN_BRANCH (commit pending gateway to graph, create branch task, connect gateway → branch)
- AWAITING_BRANCH → non-branch → NORMAL (discard pending gateway; treat the conditional step as a regular Task)
- IN_BRANCH → branch step → IN_BRANCH (create another branch task, connect from gateway)
- IN_BRANCH → non-branch → NORMAL (merge: connect all `current_branch_tails` to this step)

Pending gateway pattern avoids orphan nodes when a conditional has no following branches.

## File Structure

```
sop-to-bpmn/
├── README.md
├── requirements.txt
├── main.py              # assembly / CLI entry
├── models.py            # ProcessGraph, ProcessNode, SequenceFlow, RawStep
├── reader.py            # DocxReader
├── parser.py            # SimpleSOPParser (state machine)
├── generator.py         # BPMNGenerator + layout
├── tests/
│   ├── test_reader.py
│   ├── test_parser.py
│   ├── test_generator.py
│   └── test_integration.py
└── examples/
    ├── input_sop.docx
    └── output.bpmn
```

## Testing

1. Golden file test — example .docx → compare to hand-verified snapshot
2. Structural assertions — verify XML contains expected elements in order
3. Visual smoke test — open in bpmn.io, confirm renders

No XSD validation — too heavy for 36-hour build.

## Extension Points

| Extension | How |
|-----------|-----|
| New input format | New Reader, emit `List[RawStep]` |
| Better branch detection | Modify regex constants or rewrite parser module |
| New BPMN elements | Add `NodeType` variant + XML template |
| Better layout | Replace layout function, same signature |
| Multiple output formats | New Generator consuming `ProcessGraph` |

## Interview Narrative

> "I started with the stable abstraction: a directed graph of process nodes and edges. It decouples parsing from generation. For this SOP the graph is simple, but the structure doesn't change for nested branches or loops.
>
> I used a state machine parser because explicit control flow is easier to reason about and explain than nested look-ahead. The parser has three states: NORMAL, AWAITING_BRANCH, IN_BRANCH. Each step triggers a transition.
>
> Branch detection is rule-based — regex keywords — because it needs zero training data and is transparent. The patterns are centralized at the top of the parser module.
>
> The generator is a straight mapper from graph to BPMN XML. I included minimal diagram coordinates so it opens in bpmn.io immediately. The layout is naive by design — the brief said perfect layout wasn't required.
>
> Everything is composed manually. If this grew, I'd extract interfaces. For a prototype, explicit wiring is clearer."

## Assumptions About SOP Format

1. Steps are numbered in logical execution order (1, 2, 3... not 1, 3, 2)
2. Conditionals contain keywords: "if", "check if", "determine if", "whether"
3. Branch outcomes follow immediately: "If yes...", "If no...", "Otherwise..."
4. Branches rejoin implicitly — next non-branch step at parent level is the merge point
5. One logical start and one logical end per SOP
6. Branches are **single-step** (e.g. `"If yes, assign to Billing Queue."`). Multi-step branches (`"If yes, do X. Then do Y."`) and nested conditionals are out of prototype scope — the state machine would treat the second step as the merge point and misroute control flow.
7. No parallel execution (no "do X and Y simultaneously")
8. No loops (no "repeat until")
9. SOP numbering is **manually typed** in the paragraph text (e.g. `"1. Receive customer support email."`). Auto-numbered Word lists store the leading number in `pPr/numPr` formatting, not in `paragraph.text`, and require a separate extraction path. Verify on day 1 by inspecting `paragraph.text` and `paragraph._p.xml` of the provided `input_sop.docx`. If auto-numbered, either implement `numPr/ilvl` extraction or convert the file to manual numbering.

## Edge Cases and Handling

| Scenario | Handling |
|----------|----------|
| No numbering detected | Fallback: treat each paragraph as level-0 step |
| Auto-numbered Word list (no number in `paragraph.text`) | Detect via `paragraph._p.find('.//{...}numPr')`; if present, read `ilvl` for level. If `numPr` extraction not implemented, fall back to paragraph-per-step and log a warning. |
| Ambiguous conditional (has "if" but no clear branches) | Treat as normal Task (fail safe, don't hallucinate) |
| Branch without merge point (SOP ends mid-branch) | Connect open branch tails to End node |
| Empty .docx | Emit minimal process: Start → End |
| Missing "If yes/If no" after conditional | Pending gateway discarded; conditional step demoted to Task. No orphan nodes in graph. |
| Multiple conditionals in sequence | Each handled independently by state machine |

## Error Handling Strategy

- **Fail safe on ambiguity**: When unsure if something is a branch, treat it as a task
- **Never crash on malformed input**: Produce minimal valid BPMN (Start → End) as baseline
- **Preserve all text**: Even if we can't parse the structure, keep the text in task nodes
- **Log warnings**: Print to stderr when making assumptions (e.g., "Treating step 3 as task — no branch detected after conditional")

## Dependencies

```
python-docx==0.8.11   # .docx text extraction
```

No other dependencies. Standard library only for XML generation (xml.etree.ElementTree or string templating).

## Running the Prototype

```bash
uv pip install -r requirements.txt
python main.py examples/input_sop.docx examples/output.bpmn
```

## Output Validation

1. Open `output.bpmn` in https://demo.bpmn.io
2. Verify: start event → tasks → gateway with "Yes"/"No" labels → end event
3. Check that all 6 SOP steps are represented

## What to Test

1. **Unit: Reader** — given .docx with numbered list, returns correct `List[RawStep]`
2. **Unit: Parser** — given `List[RawStep]` with conditional, returns `ProcessGraph` with gateway + 2 branches
3. **Unit: Generator** — given `ProcessGraph` with 4 nodes + 3 flows, returns valid XML string
4. **Integration** — full pipeline: .docx → .bpmn, open in bpmn.io
5. **Golden file** — compare generated XML to hand-checked snapshot

## Code Quality Standards

- Type hints on all public functions
- Docstrings on classes and public methods
- Constants in UPPER_CASE at module level
- No global state — pass dependencies as arguments
- Functions under 30 lines where possible
- One module per component (reader.py, parser.py, generator.py, models.py)

## Interview Defense Cheat Sheet

**Q: Why a graph instead of direct XML?**
A: Stable abstraction. Parser doesn't know BPMN, generator doesn't know .docx. Testable: build graph by hand, test generator independently.

**Q: Why state machine instead of look-ahead?**
A: Explicit control flow. "Where are we?" is in the state variable. Easier to explain, extend, and debug.

**Q: Why rule-based instead of NLP?**
A: Zero training data, transparent, fast. Regex patterns are centralized for easy modification. NLP can be swapped in later without architectural changes.

**Q: Why implicit merge instead of converging gateway?**
A: Matches the example diagram they gave. Simpler XML. Valid BPMN — multiple sequence flows can enter the same activity.

**Q: Why no formal interfaces (ABC/Protocol)?**
A: Less boilerplate for a prototype. Manual composition is clearer. Extract interfaces when second implementation exists — 5-minute refactor.

**Q: What if the SOP has nested conditionals?**
A: State machine can be extended with a stack or recursive descent. Graph structure already supports it. Out of prototype scope but architecture handles it.

**Q: What if they give you a different SOP format?**
A: Swap the Reader. New Reader emits same `List[RawStep]`. Parser and generator unchanged.

**Q: How do you know the XML is valid?**
A: Visual smoke test in bpmn.io. Structural assertions in tests. No XSD validation — too heavy for 36 hours, but the XML follows BPMN 2.0 element structure.

## Future Improvements (for README)

1. **NLP branch detection**: spaCy dependency parsing for robust conditional/branch detection
2. **Proper layout**: Sugiyama layered graph drawing instead of naive grid
3. **Parallel gateways and loops**: detect "simultaneously" and "repeat until" patterns
4. **Nested conditionals**: stack-based state machine or recursive parser
5. **Configuration file**: external YAML for keyword patterns and layout parameters
6. **XSD validation**: validate output against BPMN 2.0 schema
7. **Additional output formats**: Camunda JSON, SVG export

## Deliverables Checklist

- [ ] README.md with approach, assumptions, architecture diagram, future improvements
- [ ] Source code: reader.py, parser.py, generator.py, models.py, main.py
- [ ] requirements.txt
- [ ] tests/ with unit + integration tests
- [ ] examples/input_sop.docx (provided or created)
- [ ] examples/output.bpmn (generated, checked into repo)
- [ ] Git repo with clean history
