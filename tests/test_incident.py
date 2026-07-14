"""Unit tests for the Incident model."""

import sys
import uuid

import pytest

sys.path.insert(0, "src")

from jaime.incident import Incident, Suggestion


class TestIncidentOpen:
    def test_open_returns_incident(self):
        inc = Incident.open()
        assert isinstance(inc, Incident)

    def test_id_is_valid_uuid(self):
        inc = Incident.open()
        uuid.UUID(inc.id)

    def test_each_open_has_unique_id(self):
        ids = {Incident.open().id for _ in range(10)}
        assert len(ids) == 10

    def test_opened_at_is_utc_iso(self):
        inc = Incident.open()
        assert "+00:00" in inc.opened_at or inc.opened_at.endswith("Z")

    def test_is_open_true_on_new_incident(self):
        assert Incident.open().is_open is True

    def test_closed_at_is_none_on_new_incident(self):
        assert Incident.open().closed_at is None

    def test_incident_is_immutable(self):
        inc = Incident.open()
        with pytest.raises((AttributeError, TypeError)):
            inc.id = "changed"


class TestIncidentClose:
    def test_close_returns_new_incident(self):
        inc = Incident.open()
        closed = inc.close()
        assert closed is not inc

    def test_close_preserves_id_and_opened_at(self):
        inc = Incident.open()
        closed = inc.close()
        assert closed.id == inc.id
        assert closed.opened_at == inc.opened_at

    def test_close_sets_closed_at(self):
        inc = Incident.open()
        closed = inc.close()
        assert closed.closed_at is not None
        assert "+00:00" in closed.closed_at or closed.closed_at.endswith("Z")

    def test_is_open_false_after_close(self):
        closed = Incident.open().close()
        assert closed.is_open is False

    def test_original_incident_unchanged_after_close(self):
        inc = Incident.open()
        inc.close()
        assert inc.is_open is True


class TestIncidentSerialisation:
    def test_to_dict_open_has_no_closed_at(self):
        inc = Incident.open()
        d = inc.to_dict()
        assert "id" in d
        assert "opened_at" in d
        assert "closed_at" not in d

    def test_to_dict_closed_includes_closed_at(self):
        closed = Incident.open().close()
        d = closed.to_dict()
        assert "closed_at" in d
        assert d["closed_at"] == closed.closed_at

    def test_from_dict_roundtrip_open(self):
        inc = Incident.open()
        restored = Incident.from_dict(inc.to_dict())
        assert restored.id == inc.id
        assert restored.opened_at == inc.opened_at
        assert restored.closed_at is None

    def test_from_dict_roundtrip_closed(self):
        closed = Incident.open().close()
        restored = Incident.from_dict(closed.to_dict())
        assert restored.id == closed.id
        assert restored.closed_at == closed.closed_at
        assert restored.is_open is False

    def test_from_dict_with_known_values(self):
        d = {"id": "550e8400-e29b-41d4-a716-446655440000", "opened_at": "2026-07-14T10:00:00+00:00"}
        inc = Incident.from_dict(d)
        assert inc.id == d["id"]
        assert inc.closed_at is None


class TestSuggestion:
    def test_from_llm_creates_suggestion(self):
        s = Suggestion.from_llm("The issue is X.", ["systemctl status", "journalctl -n 50"])
        assert s.description == "The issue is X."
        assert "systemctl status" in s.commands
        assert "journalctl -n 50" in s.commands
        assert "+00:00" in s.generated_at

    def test_commands_are_immutable_tuple(self):
        s = Suggestion.from_llm("desc", ["cmd1"])
        assert isinstance(s.commands, tuple)

    def test_to_dict_roundtrip(self):
        s = Suggestion.from_llm("desc", ["cmd1", "cmd2"])
        restored = Suggestion.from_dict(s.to_dict())
        assert restored.description == s.description
        assert restored.commands == s.commands
        assert restored.generated_at == s.generated_at

    def test_attach_suggestion_to_incident(self):
        inc = Incident.open()
        s = Suggestion.from_llm("diagnosis", ["df -h"])
        updated = inc.attach_suggestion(s)
        assert updated.suggestion is not None
        assert updated.suggestion.description == "diagnosis"
        assert inc.suggestion is None  # original unchanged

    def test_incident_with_suggestion_roundtrip(self):
        inc = Incident.open()
        s = Suggestion.from_llm("diagnosis", ["df -h"])
        updated = inc.attach_suggestion(s)
        restored = Incident.from_dict(updated.to_dict())
        assert restored.suggestion is not None
        assert restored.suggestion.description == "diagnosis"
        assert "df -h" in restored.suggestion.commands
