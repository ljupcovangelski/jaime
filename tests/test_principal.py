"""Unit tests for StatusTracker in jaime.principal."""

import json
import os

import pytest

from jaime.principal import StatusTracker

SINCE_A = "2026-07-13T10:00:00+00:00"
SINCE_B = "2026-07-13T11:00:00+00:00"
TS_1 = "2026-07-13T10:05:00+00:00"
TS_2 = "2026-07-13T10:35:00+00:00"


@pytest.fixture
def tracker(tmp_path):
    return StatusTracker(state_path=str(tmp_path / "status-state.json"))


class TestObserve:
    def test_first_observation_returns_increment_one(self, tracker):
        assert tracker.observe("postgresql/0", "blocked", SINCE_A) == 1

    def test_same_status_and_since_increments(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        assert tracker.observe("postgresql/0", "blocked", SINCE_A) == 3

    def test_status_change_resets_increment(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        assert tracker.observe("postgresql/0", "active", SINCE_B) == 1

    def test_same_status_new_since_resets_increment(self, tracker):
        """A new 'since' means a new episode even if status string is the same."""
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        assert tracker.observe("postgresql/0", "blocked", SINCE_B) == 1

    def test_same_status_new_since_clears_last_reported(self, tracker):
        """last_reported must be cleared on a new episode."""
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.record_reported("postgresql/0", TS_1)
        assert tracker.last_reported("postgresql/0") == TS_1

        tracker.observe("postgresql/0", "blocked", SINCE_B)
        assert tracker.last_reported("postgresql/0") is None

    def test_status_change_clears_last_reported(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.record_reported("postgresql/0", TS_1)
        tracker.observe("postgresql/0", "active", SINCE_B)
        assert tracker.last_reported("postgresql/0") is None

    def test_multiple_units_are_independent(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.observe("mysql/0", "blocked", SINCE_A)
        assert tracker.observe("postgresql/0", "blocked", SINCE_A) == 3
        assert tracker.observe("mysql/0", "blocked", SINCE_A) == 2


class TestRecordReported:
    def test_sets_last_reported(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.record_reported("postgresql/0", TS_1)
        assert tracker.last_reported("postgresql/0") == TS_1

    def test_overwrites_last_reported(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.record_reported("postgresql/0", TS_1)
        tracker.record_reported("postgresql/0", TS_2)
        assert tracker.last_reported("postgresql/0") == TS_2

    def test_no_op_for_unknown_unit(self, tracker):
        tracker.record_reported("unknown/0", TS_1)
        assert tracker.last_reported("unknown/0") is None

    def test_does_not_affect_increment(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        tracker.record_reported("postgresql/0", TS_1)
        assert tracker.observe("postgresql/0", "blocked", SINCE_A) == 3


class TestLastReported:
    def test_returns_none_for_unknown_unit(self, tracker):
        assert tracker.last_reported("unknown/0") is None

    def test_returns_none_before_any_report(self, tracker):
        tracker.observe("postgresql/0", "blocked", SINCE_A)
        assert tracker.last_reported("postgresql/0") is None


class TestPersistence:
    def test_state_is_saved_to_disk(self, tmp_path):
        path = str(tmp_path / "state.json")
        t = StatusTracker(state_path=path)
        t.observe("postgresql/0", "blocked", SINCE_A)
        assert os.path.exists(path)
        with open(path) as f:
            state = json.load(f)
        assert state["postgresql/0"]["status"] == "blocked"
        assert state["postgresql/0"]["increment"] == 1

    def test_state_is_loaded_from_disk(self, tmp_path):
        path = str(tmp_path / "state.json")
        t1 = StatusTracker(state_path=path)
        t1.observe("postgresql/0", "blocked", SINCE_A)
        t1.observe("postgresql/0", "blocked", SINCE_A)
        t1.record_reported("postgresql/0", TS_1)

        # New instance reads the same file
        t2 = StatusTracker(state_path=path)
        assert t2.observe("postgresql/0", "blocked", SINCE_A) == 3
        assert t2.last_reported("postgresql/0") == TS_1

    def test_missing_file_starts_empty(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        t = StatusTracker(state_path=path)
        assert t.observe("postgresql/0", "blocked", SINCE_A) == 1

    def test_corrupt_file_starts_empty(self, tmp_path):
        path = str(tmp_path / "state.json")
        with open(path, "w") as f:
            f.write("not valid json{{{")
        t = StatusTracker(state_path=path)
        assert t.observe("postgresql/0", "blocked", SINCE_A) == 1
