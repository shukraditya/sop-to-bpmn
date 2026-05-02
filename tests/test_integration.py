"""Integration test: .docx -> .bpmn full pipeline."""

import xml.etree.ElementTree as ET
from pathlib import Path

from main import run

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "input_sop.docx"

NS = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL"}


def test_pipeline_produces_expected_shape(tmp_path: Path):
    out = tmp_path / "out.bpmn"
    rc = run(EXAMPLE, out)
    assert rc == 0
    assert out.exists()

    root = ET.fromstring(out.read_text())
    assert len(root.findall(".//b:startEvent", NS)) == 1
    assert len(root.findall(".//b:endEvent", NS)) == 1
    assert len(root.findall(".//b:task", NS)) == 5
    assert len(root.findall(".//b:exclusiveGateway", NS)) == 1
    assert len(root.findall(".//b:sequenceFlow", NS)) == 8


def test_pipeline_preserves_task_names(tmp_path: Path):
    out = tmp_path / "out.bpmn"
    run(EXAMPLE, out)
    root = ET.fromstring(out.read_text())
    task_names = {t.attrib["name"] for t in root.findall(".//b:task", NS)}
    assert "Receive customer support email" in task_names
    assert "Assign to Billing Queue" in task_names
    assert "Assign to General Support Queue" in task_names


def test_pipeline_returns_error_on_missing_input(tmp_path: Path):
    rc = run(tmp_path / "does_not_exist.docx", tmp_path / "out.bpmn")
    assert rc == 1
