import json
from pathlib import Path

import pytest

from ollakit import ask


# deterministic pseudo-embeddings: vector keyed on a keyword in the text
def fake_embed(model, texts):
    out = []
    for t in texts:
        v = [0.0] * 4
        for kw, idx in [("cat", 0), ("dog", 1), ("rust", 2), ("garden", 3)]:
            if kw in t.lower():
                v[idx] = 1.0
        out.append(v or [0.1, 0.1, 0.1, 0.1])
    return out


@pytest.fixture
def notes(tmp_path):
    (tmp_path / "pets.md").write_text("# Pets\nMy cat is called Miso and she is orange.\n")
    (tmp_path / "code.md").write_text("# Code\nI write rust on weekends.\n")
    (tmp_path / ".hidden").write_text("secret")
    return tmp_path


def test_chunker_splits_and_overlaps():
    text = "\n".join(f"line {i}" for i in range(200))
    chunks = ask.chunk_text(text, size=800, overlap=100)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 900  # size + tolerance
    assert chunks[0] != chunks[1]


def test_text_file_filter(notes):
    files = ask.collect_files(notes)
    names = [f.name for f in files]
    assert "pets.md" in names and "code.md" in names
    assert ".hidden" not in names


def test_index_builds_and_persists(notes, tmp_path, monkeypatch):
    monkeypatch.setattr(ask.client, "embed", fake_embed)
    index_path = tmp_path / "index.json"
    ask.build_index(notes, "fake-embed", index_path)
    data = json.loads(index_path.read_text())
    assert data["model"] == "fake-embed"
    paths = [c["path"] for c in data["chunks"]]
    assert any("pets.md" in p for p in paths)


def test_index_incremental_skips_unchanged(notes, tmp_path, monkeypatch):
    monkeypatch.setattr(ask.client, "embed", fake_embed)
    index_path = tmp_path / "index.json"
    ask.build_index(notes, "fake-embed", index_path)
    calls = {"n": 0}

    def counting_embed(model, texts):
        calls["n"] += len(texts)
        return fake_embed(model, texts)

    monkeypatch.setattr(ask.client, "embed", counting_embed)
    ask.build_index(notes, "fake-embed", index_path)
    assert calls["n"] == 0  # nothing re-embedded

    (notes / "pets.md").write_text("# Pets\nThe cat now has a garden.\n")
    ask.build_index(notes, "fake-embed", index_path)
    assert calls["n"] == 1  # only the changed file


def test_retrieve_ranks_by_similarity(notes, tmp_path, monkeypatch):
    monkeypatch.setattr(ask.client, "embed", fake_embed)
    index_path = tmp_path / "index.json"
    index = ask.build_index(notes, "fake-embed", index_path)
    query = fake_embed("fake-embed", ["tell me about my cat"])[0]
    top = ask.retrieve("what about the cat?", index, "fake-embed", k=1, _qv=query)
    assert "pets.md" in top[0]["path"]


def test_build_prompt_contains_context_and_question(notes, tmp_path, monkeypatch):
    monkeypatch.setattr(ask.client, "embed", fake_embed)
    index = ask.build_index(notes, "fake-embed", tmp_path / "index.json")
    chunks = ask.retrieve("cat", index, "fake-embed", k=2,
                          _qv=fake_embed("fake-embed", ["cat"])[0])
    prompt = ask.build_prompt("what is my cat called?", chunks)
    assert "what is my cat called?" in prompt
    assert "Miso" in prompt


def test_format_answer_with_citations(capsys):
    ask.print_answer("Miso.", [("pets.md", 1)])
    out = capsys.readouterr().out
    assert "Miso." in out and "pets.md" in out
