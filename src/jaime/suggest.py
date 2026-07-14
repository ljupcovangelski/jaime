"""Suggest and act modes for Jaime.

suggest: calls the AI provider with the incident report as context and returns
         a Suggestion object containing the LLM's diagnosis and commands.
         Nothing is executed.

act:     same as suggest, but also executes every command in the Suggestion.
         All executions are audited to the JSONL log.
"""

import logging
import re
import subprocess

from jaime.incident import Suggestion

logger = logging.getLogger(__name__)

_SUGGEST_PROMPT_TEMPLATE = """\
You are Jaime, a Juju charm diagnostic assistant. You have been given an incident \
report for a Juju unit that is in an unhealthy state. Your job is to:

1. Diagnose the most likely root cause based on the report.
2. Suggest commands the operator can run to investigate or remediate the issue.
3. Format each suggested command on its own line inside a fenced code block tagged \
with 'bash', like this:
```bash
systemctl status postgresql
```
Keep your response concise and focused on the incident.

Incident report:
---
{report}
---
"""


def build_suggest_prompt(report_content: str) -> str:
    """Build the prompt to send to the AI provider for suggest/act mode."""
    return _SUGGEST_PROMPT_TEMPLATE.format(report=report_content)


def parse_commands(llm_response: str) -> list[str]:
    """Extract shell commands from fenced ```bash ... ``` blocks in the LLM response.

    Returns a flat list of non-empty, non-comment command strings.
    """
    commands = []
    for block in re.findall(r"```bash\s*\n(.*?)```", llm_response, re.DOTALL):
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append(line)
    return commands


def execute_command(command: str, timeout: int = 30) -> dict:
    """Execute a command and return a result dict.

    Uses shell=False by splitting the command string.
    Returns a dict with keys: command, returncode, stdout, stderr.
    """
    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"command": command, "returncode": -1, "stdout": "", "stderr": "timed out"}
    except Exception as e:
        return {"command": command, "returncode": -1, "stdout": "", "stderr": str(e)}


def run_suggest(provider, report_content: str) -> Suggestion:
    """Call the AI provider and return a Suggestion.

    Raises if the provider call fails, so the caller can surface the error.
    Returns None if provider is None.
    """
    if provider is None:
        return None
    prompt = build_suggest_prompt(report_content)
    llm_response = provider.generate(prompt)
    commands = parse_commands(llm_response)
    return Suggestion.from_llm(description=llm_response, commands=commands)


def run_act(
    provider,
    report_content: str,
    dry_run: bool = False,
) -> tuple[Suggestion | None, list[dict]]:
    """Call the AI provider, build a Suggestion, and execute its commands.

    Returns (suggestion, execution_results).
    If dry_run is True, commands are parsed but not executed.
    """
    suggestion = run_suggest(provider, report_content)
    if suggestion is None:
        return None, []

    results = []
    for cmd in suggestion.commands:
        if dry_run:
            logger.info("act dry-run: would execute: %s", cmd)
            results.append({
                "command": cmd,
                "returncode": None,
                "stdout": "",
                "stderr": "dry-run — not executed",
            })
        else:
            logger.info("act: executing command: %s", cmd)
            result = execute_command(cmd)
            logger.info("act: command %r exited %d", cmd, result["returncode"])
            results.append(result)

    return suggestion, results
