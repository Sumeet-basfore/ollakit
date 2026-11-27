import json
from pathlib import Path

import pytest

from ollakit import organize

TAXONOMY = ["Documents", "Images", "Videos", "Archives", "Code", "Music", "Other"]


@pytest.fixture
def messy(tmp_path):
    for name in ["report.pdf", "photo.jpg", "setup.exe", "song.mp3", ".hidden", "notes.txt"]:
        (tmp_path / name).write_text("x")
    return tmp_path


def fake_model(mapping):
    def run(files, model):
        out = []
        for f in files:
            if f["name"] in mapping:
                cat, name = mapping[f["name"]]
                out.append({"file": f["name"], "category": cat, "name": name})
        return out
    return run


def test_scan_skips_hidden_and_dirs(messy):
    entries = organize.scan(messy)
    names = [e["name"] for e in entries]
    assert "report.pdf" in names and ".hidden" not in names
    assert all(set(e) == {"name", "path", "size", "mtime"} for e in entries)


def test_classify_maps_files_and_coerces_bad_categories(messy, monkeypatch):
    monkeypatch.setattr(organize, "classify", fake_model({
        "report.pdf": ("Documents", "report"),
        "photo.jpg": ("Gallery", None),  # bad category -> Other
    }))
    plans = organize.plan_for(messy, "m")
    by_src = {p.src.name: p for p in plans}
    assert by_src["report.pdf"].dst.parent.name == "Documents"
    assert by_src["photo.jpg"].dst.parent.name == "Other"


def test_dry_run_changes_nothing(messy, monkeypatch):
    monkeypatch.setattr(organize, "classify", fake_model({
        "report.pdf": ("Documents", None),
    }))
    before = sorted(p.name for p in messy.iterdir())
    organize.run(organize.build_args([str(messy)]))
    after = sorted(p.name for p in messy.iterdir())
    assert before == after


def journal_from_output(capsys):
    out = capsys.readouterr().out
    return out.split("--undo ", 1)[1].split("\n", 1)[0]


def test_apply_moves_and_journals(messy, monkeypatch, capsys):
    monkeypatch.setattr(organize, "classify", fake_model({
        "report.pdf": ("Documents", None),
        "photo.jpg": ("Images", None),
    }))
    monkeypatch.setattr("builtins.input", lambda _: "y")
    code = organize.run(organize.build_args([str(messy), "--apply"]))
    assert code == 0
    assert (messy / "Documents" / "report.pdf").exists()
    assert (messy / "Images" / "photo.jpg").exists()
    assert not (messy / "report.pdf").exists()
    journal = json.loads(Path(journal_from_output(capsys)).read_text())
    assert {Path(m["src"]).name for m in journal} >= {"report.pdf", "photo.jpg"}


def test_undo_restores_layout(messy, monkeypatch, capsys):
    monkeypatch.setattr(organize, "classify", fake_model({
        "report.pdf": ("Documents", None),
    }))
    monkeypatch.setattr("builtins.input", lambda _: "y")
    organize.run(organize.build_args([str(messy), "--apply"]))
    journal = journal_from_output(capsys)
    assert not (messy / "report.pdf").exists()
    organize.undo(journal)
    assert (messy / "report.pdf").exists()
    assert not (messy / "Documents" / "report.pdf").exists()


def test_collision_gets_suffix(messy, monkeypatch, capsys):
    (messy / "Documents").mkdir()
    (messy / "Documents" / "report.pdf").write_text("existing")
    monkeypatch.setattr(organize, "classify", fake_model({
        "report.pdf": ("Documents", None),
    }))
    plans = organize.plan_for(messy, "m")
    by_src = {p.src.name: p for p in plans}
    assert by_src["report.pdf"].dst.name == "report (2).pdf"
    monkeypatch.setattr("builtins.input", lambda _: "y")
    organize.run(organize.build_args([str(messy), "--apply"]))
    journal = journal_from_output(capsys)
    organize.undo(journal)  # undo must restore through the suffix rename
    assert (messy / "report.pdf").exists()
    assert (messy / "Documents" / "report.pdf").read_text() == "existing"
