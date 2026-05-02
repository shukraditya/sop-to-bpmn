# System Design — SOP-to-BPMN Prototype

## 1. Requirements

### Functional
- Read a structured SOP from `.docx`
- Detect tasks, conditionals, and branches
- Emit a valid BPMN 2.0 XML file
- Include minimal diagram info so it opens in bpmn.io

### Non-Functional
- 36-hour build — minimal scope, no external services
- Single-process, local execution
- Readable, testable code
- Designed for extension (parser, layout, reader swappable)

### Constraints
- Python preferred
- No UI, no ML model training, no cloud dependencies
- One example SOP provided; code must handle it correctly

### Scope Assumptions
- **Single-step branches only**: each `If yes/If no` branch is one step (e.g. `"If yes, assign to Billing Queue."`). Multi-step branches and nested conditionals are out of prototype scope — the state machine would treat the second step as the merge point and misroute control flow.
- **Manually-typed numbering** in source `.docx`: numbering must appear in `paragraph.text`, not in Word auto-numbering metadata. See §4.1 for verification.

---

## 2. High-Level Design

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────────┐
│  .docx      │────▶│   Reader     │────▶│   Parser    │────▶│   Generator     │
│  (input)    │     │  (extract)   │     │  (build)    │     │  (serialize)    │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────────┘
                           │                    │                      │
                           ▼                    ▼                      ▼
                    List[RawStep]        ProcessGraph            .bpmn (output)
```

### Component Responsibilities

| Component | Input | Output | Responsibility |
|-----------|-------|--------|----------------|
| **Reader** | `.docx` file path | `List[RawStep]` | Extract text, detect numbering/levels |
| **Parser** | `List[RawStep]` | `ProcessGraph` | Detect branches, build node/edge graph |
| **Generator** | `ProcessGraph` | BPMN XML string | Map graph to BPMN elements + DI coordinates |

---

## 3. Data Model

### RawStep (Reader output)
```python
@dataclass
class RawStep:
    level: int          # 0 = "1.", 1 = "a.", etc.
    text: str
    original_number: str
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
    condition: Optional[str] = None

@dataclass
class ProcessGraph:
    nodes: List[ProcessNode]
    flows: List[SequenceFlow]
```

**Why a graph?**
- Decouples parsing from generation
- Natural fit for branches that rejoin
- Easy to test: build a graph by hand, feed to generator
- Extensible: new node types (parallel gateway, loop) just add enum variants

---

## 4. Component Deep Dive

### 4.1 Reader

**Approach:** python-docx paragraph iteration + regex fallback.

**Numbering detection:**
1. Try python-docx paragraph style (`numPr`, `ilvl`) for structured lists
2. Fallback: regex on paragraph text — `^\d+\.`, `^[a-z]\)`, `^\(\d+\)`

**Failure mode:** No numbering detected → treat each paragraph as level-0 step.

**Auto-numbering pitfall:** Word auto-numbered lists store the leading number in `pPr/numPr` formatting, not in `paragraph.text`. The regex fallback never fires for such files — every paragraph looks unnumbered. **Day-1 verification:** inspect `paragraph.text` and `paragraph._p.xml` of the provided `input_sop.docx`. If auto-numbered, either implement `numPr/ilvl` extraction (read `ilvl` for `level`, derive `original_number` from list counters) or convert the file to manual numbering before continuing.

**Extension point:** Replace `DocxReader` with `MarkdownReader` that emits same `List[RawStep]`.

### 4.2 Parser

**Core challenge:** Detect conditionals and their branches from flat text.

**State machine parser:**

Explicit states track what the parser is doing at each step:

```python
class ParserState(Enum):
    NORMAL = "normal"              # building tasks in sequence
    AWAITING_BRANCH = "awaiting"   # just saw conditional, expect branch next
    IN_BRANCH = "in_branch"        # consuming "If yes", "If no", etc.
```

**Auxiliary parser-instance state** (alongside `state: ParserState`):

```python
last_node_id: str                          # source for next sequence flow
pending_gateway: Optional[tuple[str, str]] # (gateway_name, source_node_id); set in AWAITING_BRANCH only
current_gateway_id: Optional[str]          # set when IN_BRANCH
current_branch_tails: list[str]            # branch task ids to merge at next non-branch step
```

State enum is the control variable; these fields are the data the transitions read and write.

**Transitions:**
- **NORMAL** → sees conditional → **AWAITING_BRANCH** (stash *pending* gateway: candidate name + source node id; **do not add to graph yet**)
- **AWAITING_BRANCH** → sees branch step → **IN_BRANCH** (commit pending gateway to graph, create branch task, connect gateway → branch)
- **AWAITING_BRANCH** → sees non-branch → **NORMAL** (discard pending gateway; treat the conditional step as a regular Task)
- **IN_BRANCH** → sees branch step → stay **IN_BRANCH** (create another branch task, connect from gateway)
- **IN_BRANCH** → sees non-branch → **NORMAL** (merge: connect all `current_branch_tails` to this step)

Pending gateway pattern avoids orphan nodes when a conditional has no following branches.

**Heuristic rules (inline constants):**
- Conditional trigger: step text contains "if", "check if", "determine if", "whether"
- Branch trigger: step starts with "If yes", "If no", "Otherwise"
- Condition extraction: strip leading verbs ("Check if", "Determine whether"), use remainder as gateway name
- Branch label extraction: "Yes" / "No" / "Otherwise" from step text

**Why state machine?**
- Single loop, no index juggling or nested look-ahead
- "Where are we?" is explicit in the state variable
- Easier to explain under interview pressure
- Adding new behavior means adding states, not modifying nested loop logic

**Why rule-based?**
- Zero training data
- Transparent — every decision is inspectable
- Regex patterns are centralized at top of parser module for easy modification

### 4.3 Generator

**Two-phase generation:**
1. Build `<process>` element with nodes and sequence flows
2. Build `<bpmndi:BPMNDiagram>` with coordinates

**Node → BPMN mapping:**
| NodeType | BPMN Element |
|----------|-------------|
| START | `<startEvent>` |
| END | `<endEvent>` |
| TASK | `<task>` |
| EXCLUSIVE_GATEWAY | `<exclusiveGateway>` |

**Flow → BPMN mapping:**
- Unconditional: `<sequenceFlow id="..." sourceRef="..." targetRef="..."/>`
- Conditional: add `<conditionExpression xsi:type="tFormalExpression">Yes</conditionExpression>`

**Layout (naive grid):**
- `X = level * 200 + 150`, where `level` = topological depth from Start
- `Y = Y_CENTER` (e.g., 150) by default
- Sibling branches off the same gateway: Y offsets distributed evenly around `Y_CENTER` (`+100`, `-100` for two; extendable for more)
- Merge node (first node with multiple incoming flows from a gateway's branches): `Y = Y_CENTER`, X advances past the branches' X column to avoid horizontal overlap with branch tasks
- Enough for bpmn.io to render without overlaps

**Why naive layout?**
- Brief explicitly says "you do not need to solve automatic layout perfectly"
- Complex layout algorithms (Sugiyama, force-directed) are out of scope for 36 hours
- Coordinates are isolated in a single function — replace later

---

## 5. Error Handling

| Scenario | Strategy |
|----------|----------|
| No numbering in .docx | Fallback: paragraph-per-step |
| Ambiguous conditional | Treat as Task (fail safe) |
| Branch without merge point | Connect open tails to End node |
| Empty .docx | Emit minimal process: Start → End |

---

## 6. Testing Strategy

| Test Type | Purpose |
|-----------|---------|
| **Golden file** | Example .docx → compare XML to hand-verified snapshot |
| **Structural assertions** | Verify XML contains expected elements in correct order |
| **Visual smoke test** | Open in bpmn.io, confirm renders without errors |

No XSD validation — too heavy for 36-hour prototype.

---

## 7. Extension Points

| Extension | How |
|-----------|-----|
| New input format (Markdown, PDF) | Implement new Reader, emit `List[RawStep]` |
| Better branch detection | Replace `BranchDetector` with NLP-based class |
| New BPMN elements (parallel gateway, loop) | Add `NodeType` variant, add XML template in Generator |
| Better layout | Replace layout function, same `ProcessGraph -> Dict[id, (x,y)]` signature |
| Multiple output formats | New Generator that consumes `ProcessGraph` |

---

## 8. Trade-offs

| Decision | Pros | Cons |
|----------|------|------|
| Rule-based parser | Zero data, transparent, fast | Brittle on edge cases |
| State machine parser | Explicit control flow, easy to explain | More code than look-ahead |
| ProcessGraph abstraction | Clean separation, testable | Small overhead for simple SOPs |
| Naive grid layout | Works immediately, simple | Ugly diagrams |
| Implicit merge (no converging gateway) | Simpler XML, matches example | Less strict BPMN |
| No formal interfaces (ABC/Protocol) | Less boilerplate | Less explicit contract |

---

## 9. Future Improvements (README)

1. **NLP branch detection**: spaCy dependency parsing for robust conditional detection
2. **Proper layout**: Sugiyama layered graph drawing
3. **Parallel gateways / loops**: detect "simultaneously" and "repeat until" patterns

---

## 10. File Structure

```
sop-to-bpmn/
├── README.md
├── requirements.txt
├── main.py                 # assembly / CLI entry point
├── reader.py               # DocxReader
├── parser.py               # SimpleSOPParser + BranchDetector
├── generator.py            # BPMNGenerator + layout
├── models.py             # ProcessGraph, ProcessNode, SequenceFlow, RawStep
├── tests/
│   ├── test_reader.py
│   ├── test_parser.py
│   ├── test_generator.py
│   └── test_integration.py
└── examples/
    ├── input_sop.docx
    └── output.bpmn
```
