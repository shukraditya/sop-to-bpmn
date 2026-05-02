"""Tests for DocxReader: numbered extraction + fallback."""

from pathlib import Path

from docx import Document

from reader import DocxReader


EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "input_sop.docx"


def test_extracts_numbered_steps_from_example():
    steps = DocxReader().extract_steps(str(EXAMPLE))
    assert len(steps) == 6
    assert steps[0].original_number == "1."
    assert steps[0].text.startswith("Receive customer support")
    assert all(s.level == 0 for s in steps)


def test_fallback_when_no_numbering(tmp_path: Path):
    doc = Document()
    doc.add_paragraph("Just some prose.")
    doc.add_paragraph("No leading numbers anywhere.")
    p = tmp_path / "unnumbered.docx"
    doc.save(str(p))

    steps = DocxReader().extract_steps(str(p))
    assert len(steps) == 2
    assert all(s.original_number == "" for s in steps)
    assert steps[0].text == "Just some prose."


def test_skips_empty_paragraphs(tmp_path: Path):
    doc = Document()
    doc.add_paragraph("1. first")
    doc.add_paragraph("")
    doc.add_paragraph("2. second")
    p = tmp_path / "with_blanks.docx"
    doc.save(str(p))

    steps = DocxReader().extract_steps(str(p))
    assert len(steps) == 2
    assert [s.text for s in steps] == ["first", "second"]
