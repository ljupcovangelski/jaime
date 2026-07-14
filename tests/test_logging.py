"""Unit tests for jaime.logging (audit event writer)."""

import json
import os
import sys

import pytest

sys.path.insert(0, "src")

from jaime.logging import write_event


class TestWriteEvent:
    def test_writes_json_line(self, tmp_path):
        path = str(tmp_path / "events.jsonl")
        write_event({"event": "test", "unit": "postgresql/0"}, path)
        with open(path) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["event"] == "test"
        assert data["unit"] == "postgresql/0"

    def test_appends_multiple_events(self, tmp_path):
        path = str(tmp_path / "events.jsonl")
        write_event({"event": "first"}, path)
        write_event({"event": "second"}, path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"

    def test_creates_parent_directories(self, tmp_path):
        path = str(tmp_path / "sub" / "dir" / "events.jsonl")
        write_event({"event": "test"}, path)
        assert os.path.exists(path)

    def test_does_not_raise_on_unwritable_path(self):
        # Should log a warning and not raise
        write_event({"event": "test"}, "/proc/nonexistent/events.jsonl")

    def test_uses_default_path_when_empty(self, tmp_path, monkeypatch):
        import jaime.logging as jlog
        default = str(tmp_path / "events.jsonl")
        monkeypatch.setattr(jlog, "_DEFAULT_AUDIT_LOG_PATH", default)
        write_event({"event": "default-path-test"}, "")
        assert os.path.exists(default)
