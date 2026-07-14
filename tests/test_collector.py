"""Unit tests for jaime.collector (context collection)."""

import datetime
import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, "src")

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
