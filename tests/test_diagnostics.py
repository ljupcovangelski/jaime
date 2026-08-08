import datetime
import json
import os
import tempfile

from jaime.diagnostics import (
    MONITORING_PLAN_SCHEMA,
    validate_monitoring_plan,
    build_prompt,
    make_empty_plan,
    write_diagnostics_file,
    read_diagnostics_file,
    read_plan_for_app,
    ensure_plan_for_app,
)


class TestValidateMonitoringPlan:
    def test_valid_full_plan_returns_empty_errors(self):
        mp = {
            "log_files": [
                {"path": "/var/log/test.log", "priority": "high", "description": "test log"}
            ],
            "processes": [
                {"name": "testd", "expected_min_count": 1, "expected_max_count": 2}
            ],
            "env_variables": ["TEST_VAR"],
            "network": {"ports": [{"port": 8080, "protocol": "tcp"}]},
            "systemd_units": ["testd.service"],
            "health_commands": [{"command": "systemctl is-active testd", "timeout_seconds": 5}],
        }
        errors = validate_monitoring_plan(mp)
        assert errors == []

    def test_not_a_dict_returns_error(self):
        errors = validate_monitoring_plan("not a dict")
        assert errors == ["monitoring plan must be a JSON object"]

    def test_empty_dict_returns_no_errors(self):
        errors = validate_monitoring_plan({})
        assert errors == []

    def test_log_files_bad_type(self):
        mp = {
            "log_files": "not a list",
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("log_files' must be a list" in e for e in errors)

    def test_log_file_missing_fields(self):
        mp = {
            "log_files": [{"path": "/var/log/test.log"}],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("missing 'priority'" in e for e in errors)
        assert any("missing 'description'" in e for e in errors)

    def test_log_file_invalid_priority(self):
        mp = {
            "log_files": [
                {"path": "/var/log/test.log", "priority": "urgent", "description": "test"}
            ],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("priority" in e and "must be" in e for e in errors)

    def test_process_missing_name(self):
        mp = {
            "log_files": [],
            "processes": [{"expected_min_count": 1}],
            "env_variables": [],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("missing 'name'" in e for e in errors)

    def test_processes_bad_type(self):
        mp = {
            "log_files": [],
            "processes": "not a list",
            "env_variables": [],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("processes' must be a list" in e for e in errors)

    def test_env_variables_bad_type(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": "not a list",
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("env_variables' must be a list" in e for e in errors)

    def test_env_variables_non_string(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [123],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert any("must be a string" in e for e in errors)

    def test_network_bad_type(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": "not an object",
        }
        errors = validate_monitoring_plan(mp)
        assert any("network' must be an object" in e for e in errors)

    def test_network_ports_bad_type(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": "not a list"},
        }
        errors = validate_monitoring_plan(mp)
        assert any("ports' must be a list" in e for e in errors)

    def test_network_port_missing_fields(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": [{"port": 8080}]},
        }
        errors = validate_monitoring_plan(mp)
        assert any("missing 'protocol'" in e for e in errors)

    def test_systemd_units_bad_type(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
            "systemd_units": "not a list",
        }
        errors = validate_monitoring_plan(mp)
        assert any("systemd_units' must be a list" in e for e in errors)

    def test_systemd_units_non_string(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
            "systemd_units": [123],
        }
        errors = validate_monitoring_plan(mp)
        assert any("must be a string" in e for e in errors)

    def test_health_commands_bad_type(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
            "health_commands": "not a list",
        }
        errors = validate_monitoring_plan(mp)
        assert any("health_commands' must be a list" in e for e in errors)

    def test_health_command_missing_command(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
            "health_commands": [{"timeout_seconds": 5}],
        }
        errors = validate_monitoring_plan(mp)
        assert any("missing 'command'" in e for e in errors)

    def test_optional_fields_omitted_are_valid(self):
        mp = {
            "log_files": [],
            "processes": [],
            "env_variables": [],
            "network": {"ports": []},
        }
        errors = validate_monitoring_plan(mp)
        assert errors == []


class TestDiagnosticsSchema:
    def test_schema_is_dict(self):
        assert isinstance(MONITORING_PLAN_SCHEMA, dict)
        assert MONITORING_PLAN_SCHEMA["type"] == "object"
        assert "log_files" in MONITORING_PLAN_SCHEMA["properties"]
        assert "monitoring_plan" not in MONITORING_PLAN_SCHEMA
        assert "principal_name" not in MONITORING_PLAN_SCHEMA


class TestBuildPrompt:
    def test_contains_app_name(self):
        prompt = build_prompt("postgresql")
        assert "postgresql" in prompt
        assert "monitoring plan" in prompt.lower()

    def test_contains_schema_json(self):
        prompt = build_prompt("test-app")
        assert "log_files" in prompt
        assert "systemd_units" in prompt
        assert "health_commands" in prompt


class TestMakeEmptyPlan:
    def test_returns_correct_structure(self):
        mp = make_empty_plan()
        assert mp["log_files"] == []
        assert mp["processes"] == []
        assert mp["env_variables"] == []
        assert mp["network"]["ports"] == []
        assert mp["systemd_units"] == []
        assert mp["health_commands"] == []

    def test_plan_passes_validation(self):
        mp = make_empty_plan()
        errors = validate_monitoring_plan(mp)
        assert errors == []


class TestReadPlanForApp:
    def test_returns_monitoring_plan_for_existing_app(self):
        data = {
            "generated_at": "2026-07-15T12:00:00",
            "plans": {"postgresql": make_empty_plan()},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = read_plan_for_app("postgresql", path)
            assert "monitoring_plan" in result
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            os.unlink(path)

    def test_returns_empty_plan_for_missing_app(self):
        data = {
            "generated_at": "2026-07-15T12:00:00",
            "plans": {"other": make_empty_plan()},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = read_plan_for_app("unknown", path)
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            os.unlink(path)

    def test_returns_empty_plan_for_missing_file(self):
        result = read_plan_for_app("any", "/tmp/does_not_exist.json")
        assert result["monitoring_plan"]["log_files"] == []


class TestEnsurePlanForApp:
    def test_uses_existing_plan(self):
        data = {
            "generated_at": "2026-07-15T12:00:00",
            "plans": {"myapp": make_empty_plan()},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            result = ensure_plan_for_app("myapp", path, provider=None)
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            os.unlink(path)

    def test_creates_empty_plan_when_no_provider(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            os.unlink(path)
        try:
            result = ensure_plan_for_app("newapp", path, provider=None)
            assert result["monitoring_plan"]["log_files"] == []
            data = read_diagnostics_file(path)
            assert "newapp" in data["plans"]
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_creates_empty_plan_on_provider_failure(self):
        class FakeFailingProvider:
            def generate(self, prompt):
                raise RuntimeError("API error")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            os.unlink(path)
        try:
            result = ensure_plan_for_app("badapp", path, provider=FakeFailingProvider())
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_creates_plan_from_provider(self):
        class FakeProvider:
            def generate(self, prompt):
                return json.dumps(make_empty_plan())

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            os.unlink(path)
        try:
            result = ensure_plan_for_app("goodapp", path, provider=FakeProvider())
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_fallback_to_empty_on_invalid_provider_response(self):
        class FakeBadProvider:
            def generate(self, prompt):
                return '{"log_files": "not_a_list"}'

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            os.unlink(path)
        try:
            result = ensure_plan_for_app("badplan", path, provider=FakeBadProvider())
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestWriteReadDiagnosticsFile:
    def test_write_and_read_v2_roundtrip(self):
        data = {
            "generated_at": "2026-07-15T12:00:00",
            "plans": {"test-app": make_empty_plan()},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            written = write_diagnostics_file(data, path)
            assert written == path
            read_back = read_diagnostics_file(path)
            assert "plans" in read_back
            assert "test-app" in read_back["plans"]
        finally:
            os.unlink(path)

    def test_creates_directories(self):
        data = {
            "generated_at": "2026-07-15T12:00:00",
            "plans": {"dir-test": make_empty_plan()},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "nested", "diagnostics.json")
            written = write_diagnostics_file(data, path)
            assert os.path.exists(written)
            read_back = read_diagnostics_file(path)
            assert "plans" in read_back
            assert "dir-test" in read_back["plans"]

    def test_read_missing_file_returns_none(self):
        result = read_diagnostics_file("/tmp/nonexistent-file-12345.json")
        assert result is None

    def test_read_invalid_json_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("not valid json")
            path = f.name
        try:
            result = read_diagnostics_file(path)
            assert result is None
        finally:
            os.unlink(path)


class TestBackwardCompat:
    def test_v1_format_migrated_on_read(self):
        v1_data = {
            "principal_name": "legacy-app",
            "monitoring_plan": make_empty_plan(),
            "generated_at": "2026-01-01T00:00:00",
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(v1_data, f)
            path = f.name
        try:
            result = read_diagnostics_file(path)
            assert "plans" in result
            assert "legacy-app" in result["plans"]
            assert "principal_name" not in result
            assert "monitoring_plan" not in result
        finally:
            os.unlink(path)

    def test_v1_format_migrated_on_write(self):
        v1_data = {
            "principal_name": "legacy-app",
            "monitoring_plan": make_empty_plan(),
        }
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
            os.unlink(path)
        try:
            write_diagnostics_file(v1_data, path)
            result = read_diagnostics_file(path)
            assert "plans" in result
            assert "legacy-app" in result["plans"]
            assert "principal_name" not in result
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_v1_to_v2_read_plan_for_app(self):
        v1_data = {
            "principal_name": "oldie",
            "monitoring_plan": make_empty_plan(),
            "generated_at": "2026-01-01T00:00:00",
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(v1_data, f)
            path = f.name
        try:
            result = read_plan_for_app("oldie", path)
            assert result["monitoring_plan"]["log_files"] == []
        finally:
            os.unlink(path)
