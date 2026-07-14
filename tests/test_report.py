"""Unit tests for jaime.report (Markdown report generator)."""

import os
import sys

import pytest

sys.path.insert(0, "src")

from jaime.report import generate_report

INCIDENT_ID = "550e8400-e29b-41d4-a716-446655440000"
FIRST_SEEN = "2026-07-14T09:37:54+00:00"

_FULL_CONTEXT = {
    "unit_logs": ["2026-07-14 10:00:00 ERROR some failure", "2026-07-14 10:01:00 INFO retry"],
    "systemd_failed": ["postgresql.service"],
    "disk_usage": ["Filesystem  Size  Used Avail Use% Mounted on", "/dev/sda1   20G   18G  2.0G  90% /"],
    "memory_summary": ["              total  used  free", "Mem:           7.7G  6.1G  1.6G"],
    "collected_at": "2026-07-14T10:05:00+00:00",
}

_EMPTY_CONTEXT = {
    "unit_logs": [],
    "systemd_failed": [],
    "disk_usage": [],
    "memory_summary": [],
    "collected_at": "2026-07-14T10:05:00+00:00",
}


class TestGenerateReport:
    def test_returns_path(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        assert isinstance(path, str)
        assert os.path.exists(path)

    def test_filename_is_incident_id(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        assert os.path.basename(path) == f"{INCIDENT_ID}.md"

    def test_report_contains_incident_id(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        content = open(path).read()
        assert INCIDENT_ID in content

    def test_report_contains_workload_status(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        content = open(path).read()
        assert "blocked" in content

    def test_report_contains_first_seen(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        content = open(path).read()
        assert FIRST_SEEN in content

    def test_report_contains_systemd_section(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        content = open(path).read()
        assert "postgresql.service" in content

    def test_report_contains_log_lines(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, str(tmp_path))
        content = open(path).read()
        assert "some failure" in content

    def test_empty_context_produces_valid_report(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _EMPTY_CONTEXT, str(tmp_path))
        content = open(path).read()
        assert "None detected" in content or "Not available" in content or "No recent logs" in content

    def test_creates_report_dir(self, tmp_path):
        report_dir = str(tmp_path / "sub" / "reports")
        generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, report_dir)
        assert os.path.isdir(report_dir)

    def test_uses_default_dir_when_empty(self, tmp_path, monkeypatch):
        import jaime.report as jreport
        monkeypatch.setattr(jreport, "_DEFAULT_REPORT_DIR", str(tmp_path))
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT, "")
        assert os.path.exists(path)
