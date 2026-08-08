"""Tests for filesystem-based co-located unit discovery."""

import json
import os
import tempfile
import unittest.mock as mock

from jaime.discovery import discover_colocated_units, read_unit_workload_status


class TestDiscoverColocatedUnits:
    def test_returns_unit_names(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        for d in ("unit-postgresql-0", "unit-jaime-0", "machine-0"):
            (agents / d).mkdir()

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            units = discover_colocated_units(skip_unit="jaime/0")

        assert "postgresql/0" in units
        assert "jaime/0" not in units
        assert "machine-0" not in units  # not a unit

    def test_skip_jaime_itself(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        for d in ("unit-postgresql-0", "unit-jaime-0"):
            (agents / d).mkdir()

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            units = discover_colocated_units(skip_unit="jaime/0")

        assert "postgresql/0" in units
        assert "jaime/0" not in units

    def test_empty_when_directory_missing(self, tmp_path):
        missing = tmp_path / "nonexistent"
        with mock.patch("jaime.discovery._AGENTS_DIR", str(missing)):
            units = discover_colocated_units()
        assert units == []

    def test_empty_when_no_units(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        (agents / "machine-0").mkdir()

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            units = discover_colocated_units()
        assert units == []

    def test_sorted_order(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        for d in ("unit-zzz-0", "unit-aaa-0"):
            (agents / d).mkdir()

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            units = discover_colocated_units()

        assert units == ["aaa/0", "zzz/0"]


class TestReadUnitWorkloadStatus:
    def test_returns_status_from_state_file(self, tmp_path):
        state = {
            "workload-status": {
                "current": "blocked",
                "message": "database unavailable",
                "since": "2026-07-15T10:00:00Z",
            }
        }
        agents = tmp_path / "agents"
        agents.mkdir()
        state_dir = agents / "unit-postgresql-0"
        state_dir.mkdir()
        (state_dir / "state").write_text(json.dumps(state))

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            result = read_unit_workload_status("postgresql/0")

        assert result is not None
        assert result["current"] == "blocked"
        assert result["message"] == "database unavailable"
        assert result["since"] == "2026-07-15T10:00:00Z"

    def test_returns_none_when_file_missing(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            result = read_unit_workload_status("postgresql/0")
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        agents = tmp_path / "agents"
        agents.mkdir()
        state_dir = agents / "unit-postgresql-0"
        state_dir.mkdir()
        (state_dir / "state").write_text("not json")

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            result = read_unit_workload_status("postgresql/0")
        assert result is None

    def test_returns_none_when_no_workload_status_key(self, tmp_path):
        state = {"some-other-key": "value"}
        agents = tmp_path / "agents"
        agents.mkdir()
        state_dir = agents / "unit-postgresql-0"
        state_dir.mkdir()
        (state_dir / "state").write_text(json.dumps(state))

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            result = read_unit_workload_status("postgresql/0")
        assert result is None

    def test_active_status(self, tmp_path):
        state = {
            "workload-status": {
                "current": "active",
                "message": "",
                "since": "2026-07-15T10:00:00Z",
            }
        }
        agents = tmp_path / "agents"
        agents.mkdir()
        state_dir = agents / "unit-postgresql-0"
        state_dir.mkdir()
        (state_dir / "state").write_text(json.dumps(state))

        with mock.patch("jaime.discovery._AGENTS_DIR", str(agents)):
            result = read_unit_workload_status("postgresql/0")

        assert result["current"] == "active"
