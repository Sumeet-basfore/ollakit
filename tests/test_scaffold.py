import json

import pytest

from ollakit import config
from ollakit.client import parse_json


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    cfg = config.load()
    assert cfg["chat_model"] is None  # defaults present
    cfg["chat_model"] = "qwen3:4b"
    config.save(cfg)
    assert json.loads((tmp_path / "config.json").read_text())["chat_model"] == "qwen3:4b"
    assert config.load()["chat_model"] == "qwen3:4b"


def test_parse_json_tolerates_fences_and_prose():
    assert parse_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert parse_json('Here are findings: [{"a": 2}] hope that helps') == [{"a": 2}]
    assert parse_json('{"a": 3}') == {"a": 3}
    with pytest.raises(json.JSONDecodeError):
        parse_json("not json at all")
