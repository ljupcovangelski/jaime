"""Unit tests for jaime.suggest (suggest/act engine)."""

import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, "src")

from jaime.suggest import (
    build_suggest_prompt,
    execute_command,
    parse_commands,
    run_act,
    run_suggest,
)


class TestBuildSuggestPrompt:
    def test_contains_report(self):
        prompt = build_suggest_prompt("some report content")
        assert "some report content" in prompt

    def test_contains_instructions(self):
        prompt = build_suggest_prompt("report")
        assert "root cause" in prompt.lower()
        assert "bash" in prompt


class TestParseCommands:
    def test_extracts_single_command(self):
        response = "Here is a command:\n```bash\nsystemctl status postgresql\n```"
        assert parse_commands(response) == ["systemctl status postgresql"]

    def test_extracts_multiple_commands(self):
        response = "```bash\nsystemctl status postgresql\njournalctl -u postgresql -n 50\n```"
        result = parse_commands(response)
        assert "systemctl status postgresql" in result
        assert "journalctl -u postgresql -n 50" in result

    def test_ignores_comment_lines(self):
        response = "```bash\n# check status\nsystemctl status postgresql\n```"
        result = parse_commands(response)
        assert result == ["systemctl status postgresql"]

    def test_ignores_non_bash_blocks(self):
        response = "```python\nprint('hello')\n```"
        assert parse_commands(response) == []

    def test_empty_response_returns_empty(self):
        assert parse_commands("") == []

    def test_multiple_blocks(self):
        response = "```bash\ndf -h\n```\nsome text\n```bash\nfree -h\n```"
        result = parse_commands(response)
        assert "df -h" in result
        assert "free -h" in result


class TestExecuteCommand:
    def test_successful_command(self):
        result = execute_command("echo hello")
        assert result["returncode"] == 0
        assert "hello" in result["stdout"]

    def test_failed_command(self):
        result = execute_command("ls /nonexistent_path_xyz")
        assert result["returncode"] != 0

    def test_timeout_returns_error(self):
        result = execute_command("sleep 60", timeout=1)
        assert result["returncode"] == -1
        assert "timed out" in result["stderr"]


class TestRunSuggest:
    def test_returns_llm_response(self):
        provider = mock.MagicMock()
        provider.generate.return_value = "The issue is X. Run: ```bash\nsystemctl status\n```"
        result = run_suggest(provider, "report content")
        assert result == "The issue is X. Run: ```bash\nsystemctl status\n```"
        provider.generate.assert_called_once()

    def test_returns_empty_when_no_provider(self):
        assert run_suggest(None, "report content") == ""

    def test_returns_empty_on_provider_failure(self):
        provider = mock.MagicMock()
        provider.generate.side_effect = RuntimeError("API error")
        with pytest.raises(RuntimeError):
            run_suggest(provider, "report content")


class TestRunAct:
    def test_returns_llm_response_and_results(self):
        provider = mock.MagicMock()
        provider.generate.return_value = "```bash\necho hello\n```"
        llm_resp, results = run_act(provider, "report")
        assert llm_resp != ""
        assert len(results) == 1
        assert results[0]["command"] == "echo hello"

    def test_executes_commands(self):
        provider = mock.MagicMock()
        provider.generate.return_value = "```bash\necho hello\n```"
        _, results = run_act(provider, "report")
        assert results[0]["returncode"] == 0
        assert "hello" in results[0]["stdout"]

    def test_dry_run_does_not_execute(self):
        provider = mock.MagicMock()
        provider.generate.return_value = "```bash\necho hello\n```"
        with mock.patch("jaime.suggest.execute_command") as mock_exec:
            _, results = run_act(provider, "report", dry_run=True)
        mock_exec.assert_not_called()
        assert "dry-run" in results[0]["stderr"]

    def test_returns_empty_when_no_provider(self):
        llm_resp, results = run_act(None, "report")
        assert llm_resp == ""
        assert results == []
