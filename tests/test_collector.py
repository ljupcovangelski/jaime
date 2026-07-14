"""Unit tests for jaime.collector (context collection)."""

import datetime
import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, "src")

import jaime.collector as jcollector

from jaime.collector import (
    collect_context,
    collect_disk_usage,
    collect_memory_summary,
    collect_systemd_failed,
    collect_unit_logs,
    _tail_lines,
)


class TestTailLines:
    def test_returns_all_lines_when_under_limit(self):
        lines = ["a", "b", "c"]
        assert _tail_lines("\n".join(lines), 10) == lines

    def test_returns_last_n_lines_when_over_limit(self):
        lines = [str(i) for i in range(20)]
        result = _tail_lines("\n".join(lines), 5)
        assert result == lines[-5:]

    def test_empty_string_returns_empty(self):
        assert _tail_lines("", 10) == []


class TestCollectUnitLogs:
    def test_returns_list(self, tmp_path):
        log_file = tmp_path / "unit-postgresql-0.log"
        now = datetime.datetime.now(datetime.timezone.utc)
        log_file.write_text(
            f"{now.strftime('%Y-%m-%d %H:%M:%S')} ERROR some error\n"
            f"{now.strftime('%Y-%m-%d %H:%M:%S')} INFO recovered\n"
        )
        import jaime.collector as jcollector
        with mock.patch.object(jcollector, "_JUJU_LOG_DIR", str(tmp_path)):
            result = collect_unit_logs("postgresql/0", log_window_minutes=60)
        assert isinstance(result, list)
        assert any("some error" in l for l in result)

    def test_missing_log_returns_empty(self, tmp_path):
        import jaime.collector as jcollector
        with mock.patch.object(jcollector, "_JUJU_LOG_DIR", str(tmp_path)):
            result = collect_unit_logs("nonexistent/0")
        assert result == []

    def test_respects_max_lines(self, tmp_path):
        log_file = tmp_path / "unit-postgresql-0.log"
        now = datetime.datetime.now(datetime.timezone.utc)
        lines = "\n".join(
            f"{now.strftime('%Y-%m-%d %H:%M:%S')} INFO line {i}" for i in range(100)
        )
        log_file.write_text(lines + "\n")
        import jaime.collector as jcollector
        with mock.patch.object(jcollector, "_JUJU_LOG_DIR", str(tmp_path)):
            result = collect_unit_logs("postgresql/0", log_window_minutes=60, max_lines=10)
        assert len(result) <= 10

    def test_filters_old_lines(self, tmp_path):
        log_file = tmp_path / "unit-postgresql-0.log"
        old_ts = "2000-01-01 00:00:00"
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_ts = now.strftime("%Y-%m-%d %H:%M:%S")
        log_file.write_text(
            f"{old_ts} INFO old line\n"
            f"{recent_ts} INFO recent line\n"
        )
        import jaime.collector as jcollector
        with mock.patch.object(jcollector, "_JUJU_LOG_DIR", str(tmp_path)):
            result = collect_unit_logs("postgresql/0", log_window_minutes=60)
        assert not any("old line" in l for l in result)
        assert any("recent line" in l for l in result)


class TestCollectSystemdFailed:
    def test_returns_list(self):
        with mock.patch("jaime.collector._run", return_value="nginx.service\npostgresql.service\n"):
            result = collect_systemd_failed()
        assert result == ["nginx.service", "postgresql.service"]

    def test_returns_empty_when_no_failures(self):
        with mock.patch("jaime.collector._run", return_value=""):
            result = collect_systemd_failed()
        assert result == []


class TestCollectDiskUsage:
    def test_returns_lines(self):
        output = "Filesystem  Size  Used Avail Use% Mounted on\n/dev/sda1   20G  18G  2G   90% /\n"
        with mock.patch("jaime.collector._run", return_value=output):
            result = collect_disk_usage()
        assert len(result) == 2
        assert "Filesystem" in result[0]


class TestCollectMemorySummary:
    def test_returns_lines(self):
        output = "              total  used  free\nMem:           7.7G  6.1G  1.6G\n"
        with mock.patch("jaime.collector._run", return_value=output):
            result = collect_memory_summary()
        assert any("Mem" in l for l in result)


class TestCollectContext:
    def test_returns_all_sections(self):
        with mock.patch("jaime.collector.collect_unit_logs", return_value=["log line"]), \
             mock.patch("jaime.collector.collect_systemd_failed", return_value=[]), \
             mock.patch("jaime.collector.collect_disk_usage", return_value=["disk line"]), \
             mock.patch("jaime.collector.collect_memory_summary", return_value=["mem line"]):
            ctx = collect_context("postgresql/0")
        assert "unit_logs" in ctx
        assert "systemd_failed" in ctx
        assert "disk_usage" in ctx
        assert "memory_summary" in ctx
        assert "collected_at" in ctx

    def test_collected_at_is_utc_iso(self):
        with mock.patch("jaime.collector.collect_unit_logs", return_value=[]), \
             mock.patch("jaime.collector.collect_systemd_failed", return_value=[]), \
             mock.patch("jaime.collector.collect_disk_usage", return_value=[]), \
             mock.patch("jaime.collector.collect_memory_summary", return_value=[]):
            ctx = collect_context("postgresql/0")
        assert "+00:00" in ctx["collected_at"] or ctx["collected_at"].endswith("Z")


class TestCollectLogFiles:
    def test_available_file_returns_lines(self, tmp_path):
        log = tmp_path / "test.log"
        log.write_text("line1\nline2\nline3\n")
        plan_lf = [{"path": str(log), "priority": "high", "description": "test log"}]
        import jaime.collector as jcollector
        with mock.patch.object(jcollector, "_JUJU_LOG_DIR", str(tmp_path)):
            result = jcollector._collect_log_files(plan_lf, 100)
        assert len(result) == 1
        assert result[0]["status"] == "available"
        assert "line2" in result[0]["lines"]

    def test_not_found_file_returns_not_found(self):
        plan_lf = [{"path": "/nonexistent/path.log", "priority": "low", "description": ""}]
        result = jcollector._collect_log_files(plan_lf, 100)
        assert result[0]["status"] == "not_found"
        assert result[0]["lines"] == []

    def test_empty_plan_returns_empty(self):
        assert jcollector._collect_log_files([], 100) == []


class TestCollectProcesses:
    def test_process_running(self):
        with mock.patch("jaime.collector._run", return_value="12345\n"):
            result = jcollector._collect_processes([{"name": "nginx", "expected_min_count": 1, "expected_max_count": 2}])
        assert result[0]["status"] == "ok"
        assert result[0]["running_count"] == 1

    def test_too_few_processes(self):
        with mock.patch("jaime.collector._run", return_value=""):
            result = jcollector._collect_processes([{"name": "nginx", "expected_min_count": 1, "expected_max_count": 2}])
        assert result[0]["status"] == "too_few"
        assert result[0]["running_count"] == 0

    def test_too_many_processes(self):
        with mock.patch("jaime.collector._run", return_value="12345\n12346\n12347\n"):
            result = jcollector._collect_processes([{"name": "nginx", "expected_min_count": 1, "expected_max_count": 2}])
        assert result[0]["status"] == "too_many"
        assert result[0]["running_count"] == 3


class TestCollectNetworkPorts:
    def test_port_listening(self):
        with mock.patch("jaime.collector._run", return_value="tcp LISTEN 0 128 0.0.0.0:5432"):
            result = jcollector._collect_network_ports([{"port": 5432, "protocol": "tcp"}])
        assert result[0]["status"] == "listening"

    def test_port_not_listening(self):
        with mock.patch("jaime.collector._run", return_value="tcp LISTEN 0 128 0.0.0.0:80"):
            result = jcollector._collect_network_ports([{"port": 5432, "protocol": "tcp"}])
        assert result[0]["status"] == "not_listening"


class TestCollectEnvVariables:
    def test_var_set(self):
        result = jcollector._collect_env_variables(["PATH"])
        assert result[0]["status"] == "set"
        assert result[0]["value"] != ""

    def test_var_unset(self):
        result = jcollector._collect_env_variables(["SOME_UNDEFINED_VAR_XYZ"])
        assert result[0]["status"] == "unset"
        assert result[0]["value"] == ""


class TestCollectContextWithPlan:
    def test_plan_driven_collects_all_sections(self):
        plan = {
            "principal_name": "postgresql",
            "monitoring_plan": {
                "log_files": [{"path": "/var/log/postgresql.log", "priority": "high", "description": "main log"}],
                "processes": [{"name": "postgres", "expected_min_count": 1, "expected_max_count": 2}],
                "systemd_units": ["postgresql.service"],
                "env_variables": ["PGDATA"],
                "network": {"ports": [{"port": 5432, "protocol": "tcp"}]},
            },
        }
        mocks = {
            "collect_unit_logs": mock.MagicMock(return_value=[]),
            "collect_disk_usage": mock.MagicMock(return_value=[]),
            "collect_memory_summary": mock.MagicMock(return_value=[]),
            "collect_systemd_failed": mock.MagicMock(return_value=[]),
            "_collect_log_files": mock.MagicMock(return_value=[{"path": "/var/log/postgresql.log", "status": "available", "lines": ["log line"]}]),
            "_collect_processes": mock.MagicMock(return_value=[{"name": "postgres", "status": "ok"}]),
            "_collect_systemd_units": mock.MagicMock(return_value=[{"unit": "postgresql.service", "status": "active"}]),
            "_collect_network_ports": mock.MagicMock(return_value=[{"port": 5432, "protocol": "tcp", "status": "listening"}]),
            "_collect_env_variables": mock.MagicMock(return_value=[{"name": "PGDATA", "value": "/var/lib/pg", "status": "set"}]),
        }
        with mock.patch.multiple("jaime.collector", **mocks):
            ctx = collect_context("postgresql/0", diagnostics_plan=plan)
        pr = ctx["plan_results"]
        assert pr["log_files"]["type"] == "plan"
        assert pr["processes"]["type"] == "plan"
        assert pr["systemd_units"]["type"] == "plan"
        assert pr["network_ports"]["type"] == "plan"
        assert pr["env_variables"]["type"] == "plan"

    def test_plan_with_empty_processes_falls_back_to_broad(self):
        """When a plan section is empty, broad fallback is used instead."""
        plan = {
            "principal_name": "postgresql",
            "monitoring_plan": {
                "log_files": [],
                "processes": [],
                "systemd_units": [],
                "env_variables": [],
                "network": {},
            },
        }
        mocks = {
            "collect_unit_logs": mock.MagicMock(return_value=[]),
            "collect_disk_usage": mock.MagicMock(return_value=[]),
            "collect_memory_summary": mock.MagicMock(return_value=[]),
            "collect_systemd_failed": mock.MagicMock(return_value=["failed.service"]),
            "_collect_broad_processes": mock.MagicMock(return_value=["ps line 1", "ps line 2"]),
            "_collect_broad_ports": mock.MagicMock(return_value=["ss line 1"]),
        }
        with mock.patch.multiple("jaime.collector", **mocks):
            ctx = collect_context("postgresql/0", diagnostics_plan=plan)
        pr = ctx["plan_results"]
        assert pr["processes"]["type"] == "broad"
        assert pr["network_ports"]["type"] == "broad"
        assert pr["systemd_units"]["type"] == "broad"

    def test_no_plan_falls_back_to_broad(self):
        mocks = {
            "collect_unit_logs": mock.MagicMock(return_value=[]),
            "collect_disk_usage": mock.MagicMock(return_value=[]),
            "collect_memory_summary": mock.MagicMock(return_value=[]),
            "collect_systemd_failed": mock.MagicMock(return_value=["failed.service"]),
            "_collect_broad_processes": mock.MagicMock(return_value=["ps line"]),
            "_collect_broad_ports": mock.MagicMock(return_value=["ss line"]),
        }
        with mock.patch.multiple("jaime.collector", **mocks):
            ctx = collect_context("postgresql/0", diagnostics_plan=None)
        pr = ctx["plan_results"]
        assert pr["processes"]["type"] == "broad"
        assert pr["network_ports"]["type"] == "broad"
        assert "systemd_failed" in ctx
