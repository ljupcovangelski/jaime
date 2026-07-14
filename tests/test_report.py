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

    def test_ai_suggestions_appended(self, tmp_path):
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT,
                               str(tmp_path), ai_suggestions="## Suggested checks\n\n- Check config")
        content = open(path).read()
        assert "AI Diagnosis" in content
        assert "Suggested checks" in content

    def test_act_results_appended(self, tmp_path):
        act_results = [{"command": "systemctl restart postgresql", "returncode": 0, "stdout": "done", "stderr": ""}]
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, _FULL_CONTEXT,
                               str(tmp_path), act_results=act_results)
        content = open(path).read()
        assert "Act mode" in content
        assert "systemctl restart postgresql" in content
        assert "exit 0" in content


_PLAN_RESULTS_LOG_FILES = {
    "plan_results": {
        "log_files": {
            "type": "plan",
            "items": [
                {"path": "/var/log/postgresql.log", "priority": "high", "description": "Main log",
                 "status": "available", "lines": ["ERROR: connection refused"]},
            ],
        },
    },
}

_PLAN_RESULTS_PROCESSES = {
    "plan_results": {
        "processes": {
            "type": "plan",
            "items": [
                {"name": "postgres", "expected_min_count": 1, "expected_max_count": 2,
                 "running_count": 0, "status": "too_few"},
            ],
        },
    },
}

_PLAN_RESULTS_SYSTEMD = {
    "plan_results": {
        "systemd_units": {
            "type": "plan",
            "items": [
                {"unit": "postgresql.service", "status": "active"},
                {"unit": "postgresql-exporter.service", "status": "failed"},
            ],
        },
    },
}

_PLAN_RESULTS_PORTS = {
    "plan_results": {
        "network_ports": {
            "type": "plan",
            "items": [
                {"port": 5432, "protocol": "tcp", "status": "listening"},
                {"port": 8080, "protocol": "tcp", "status": "not_listening"},
            ],
        },
    },
}

_PLAN_RESULTS_ENV = {
    "plan_results": {
        "env_variables": {
            "type": "plan",
            "items": [
                {"name": "PGDATA", "value": "/var/lib/pg", "status": "set"},
                {"name": "PGPORT", "value": "", "status": "unset"},
            ],
        },
    },
}

_BROAD_PROCESSES = {
    "plan_results": {
        "processes": {
            "type": "broad",
            "lines": ["USER PID ...", "postgres  1234 ..."],
        },
    },
}


class TestReportPlanResults:
    def test_log_files_section(self, tmp_path):
        ctx = {**_FULL_CONTEXT, **_PLAN_RESULTS_LOG_FILES}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Log files" in content
        assert "/var/log/postgresql.log" in content
        assert "connection refused" in content
        assert "✓" in content

    def test_log_files_not_found(self, tmp_path):
        ctx = {
            **_FULL_CONTEXT,
            "plan_results": {
                "log_files": {
                    "type": "plan",
                    "items": [
                        {"path": "/var/log/missing.log", "priority": "low", "description": "",
                         "status": "not_found", "lines": []},
                    ],
                },
            },
        }
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "missing.log" in content
        assert "✗" in content

    def test_processes_section(self, tmp_path):
        ctx = {**_FULL_CONTEXT, **_PLAN_RESULTS_PROCESSES}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Processes" in content
        assert "postgres" in content
        assert "too_few" in content or "✗" in content

    def test_systemd_units_section(self, tmp_path):
        ctx = {**_FULL_CONTEXT, **_PLAN_RESULTS_SYSTEMD}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Systemd units" in content
        assert "postgresql.service" in content
        assert "active" in content
        assert "failed" in content

    def test_network_ports_section(self, tmp_path):
        ctx = {**_FULL_CONTEXT, **_PLAN_RESULTS_PORTS}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Network ports" in content
        assert "5432" in content
        assert "8080" in content

    def test_env_variables_section(self, tmp_path):
        ctx = {**_FULL_CONTEXT, **_PLAN_RESULTS_ENV}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Environment variables" in content
        assert "PGDATA" in content
        assert "PGPORT" in content

    def test_broad_processes_section(self, tmp_path):
        ctx = {**_FULL_CONTEXT, **_BROAD_PROCESSES}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Processes" in content
        assert "postgres" in content

    def test_no_plan_results_omits_extra_sections(self, tmp_path):
        ctx = {**_EMPTY_CONTEXT}
        path = generate_report(INCIDENT_ID, "postgresql/0", "blocked", FIRST_SEEN, ctx, str(tmp_path))
        content = open(path).read()
        assert "Log files" not in content
        assert "Network ports" not in content
        assert "Environment variables" not in content
