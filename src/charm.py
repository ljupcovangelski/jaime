#!/usr/bin/env python3
"""Jaime charm — diagnostics plan generation on relation-joined."""

import json
import logging
import datetime

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from jaime.diagnostics import (
    validate_diagnostics,
    build_prompt,
    write_diagnostics_file,
    read_diagnostics_file,
    make_empty_plan,
)
from jaime.principal import StatusTracker
from jaime.incident import Incident
from jaime.collector import collect_context
from jaime.report import generate_report
from jaime.logging import write_event
from jaime.suggest import run_suggest, run_act

logger = logging.getLogger(__name__)


class JaimeCharm(CharmBase):
    _diagnostics_dir = "/var/lib/jaime"
    _diagnostics_path = f"{_diagnostics_dir}/diagnostics.json"

    def __init__(self, *args):
        super().__init__(*args)
        self._status_tracker = StatusTracker()

        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.principal_relation_changed, self._on_principal_changed)
        self.framework.observe(self.on.principal_relation_joined, self._on_principal_joined)
        self.framework.observe(self.on.principal_relation_broken, self._on_principal_broken)

        self.framework.observe(self.on.diagnose_action, self._on_action_diagnose)
        self.framework.observe(self.on.collect_context_action, self._on_action_collect_context)
        self.framework.observe(self.on.generate_report_action, self._on_action_generate_report)
        self.framework.observe(self.on.show_status_action, self._on_action_show_status)
        self.framework.observe(self.on.reset_action, self._on_action_reset)

    def _on_update_status(self, event):
        try:
            relations = list(self.model.relations.get("principal", []))
        except Exception:
            relations = []

        if relations:
            self._log_principal_status()
        else:
            self.unit.status = MaintenanceStatus("waiting for principal relation")

    def _log_principal_status(self):
        """Read principal unit workload status via goal-state and emit a JSON debug log.

        On every tick, logs the status of watched units and updates Jaime's own
        unit status to reflect the current monitoring state.

        State machine for self.unit.status:
          - healthy / not watched      → ActiveStatus("Ready")
          - watched, within timeout    → WaitingStatus("<status> - waiting (x/y min)")
          - collecting context         → MaintenanceStatus("collecting context: <status> (<id>)")
          - generating report          → MaintenanceStatus("generating report: <status> (<id>)")
          - incident open / cooldown   → ActiveStatus("incident open: <status> (<id>)")
          - recovered after incident   → ActiveStatus("Ready")
        """
        watch_statuses = {
            s.strip()
            for s in self.model.config.get("watch-statuses", "error,blocked").split(",")
            if s.strip()
        }
        failure_timeout = self.model.config.get("failure-timeout-minutes", 5)
        cooldown = self.model.config.get("cooldown-minutes", 30)

        now = datetime.datetime.now(datetime.timezone.utc)

        try:
            from ops.hookcmds import goal_state
            gs = goal_state()
            principal_relations = gs.relations.get("principal", {})
            for unit_name, goal in principal_relations.items():
                if "/" not in unit_name:
                    continue

                status = goal.status
                since_iso = goal.since.isoformat()
                # Capture incident state before observe() may clear it on a new episode.
                had_open_incident = self._status_tracker.has_open_incident(unit_name)
                prior_incident = self._status_tracker.current_incident(unit_name)
                increment = self._status_tracker.observe(unit_name, status, since_iso)

                # --- Recovery ---
                if status not in watch_statuses:
                    if increment == 1 and had_open_incident and prior_incident:
                        # Close the open incident.
                        closed = Incident.from_dict(prior_incident).close()
                        self._status_tracker.close_incident(unit_name, closed.to_dict())
                        logger.info(
                            json.dumps({
                                "event": "incident-closed",
                                "unit": unit_name,
                                "workload": status,
                                "incident": closed.to_dict(),
                                "timestamp": now.isoformat(),
                            })
                        )
                    elif increment == 1:
                        logger.debug(
                            json.dumps({
                                "event": "principal-status-recovered",
                                "unit": unit_name,
                                "workload": status,
                                "timestamp": now.isoformat(),
                            })
                        )
                    else:
                        logger.debug(
                            "principal unit %s: workload=%s (not watched, increment=%d)",
                            unit_name, status, increment,
                        )
                    self.unit.status = ActiveStatus("Ready")
                    continue

                # Always log the current watched status.
                logger.debug(json.dumps({
                    "event": "principal-status-watched",
                    "unit": unit_name,
                    "workload": status,
                    "first_seen": since_iso,
                    "increment": increment,
                    "timestamp": now.isoformat(),
                }))

                # --- Within failure-timeout: waiting ---
                unhealthy_minutes = (now - goal.since).total_seconds() / 60
                if unhealthy_minutes < failure_timeout:
                    logger.debug(
                        "principal unit %s: unhealthy for %.1f min, "
                        "waiting for failure-timeout (%d min)",
                        unit_name, unhealthy_minutes, failure_timeout,
                    )
                    self.unit.status = WaitingStatus(
                        f"{status} - waiting ({unhealthy_minutes:.1f}/{failure_timeout} min)"
                    )
                    continue

                # --- Cooldown: incident already open ---
                last_reported_iso = self._status_tracker.last_reported(unit_name)
                if last_reported_iso:
                    last_reported_dt = datetime.datetime.fromisoformat(last_reported_iso)
                    cooldown_elapsed = (now - last_reported_dt).total_seconds() / 60
                    if cooldown_elapsed < cooldown:
                        incident_dict = self._status_tracker.current_incident(unit_name)
                        logger.debug(json.dumps({
                            "event": "principal-status-cooldown",
                            "unit": unit_name,
                            "workload": status,
                            "first_seen": since_iso,
                            "increment": increment,
                            "cooldown_elapsed_minutes": round(cooldown_elapsed, 1),
                            "cooldown_minutes": cooldown,
                            "incident": incident_dict,
                            "timestamp": now.isoformat(),
                        }))
                        short_id = (incident_dict or {}).get("id", "")[:8]
                        self.unit.status = ActiveStatus(
                            f"incident open: {status} ({short_id})"
                        )
                        continue

                # --- Open a new incident ---
                incident = Incident.open()
                short_id = incident.id[:8]
                logger.info(json.dumps({
                    "event": "incident-opened",
                    "unit": unit_name,
                    "workload": status,
                    "first_seen": since_iso,
                    "increment": increment,
                    "incident": incident.to_dict(),
                    "timestamp": now.isoformat(),
                }))
                self._status_tracker.record_reported(unit_name, now.isoformat(), incident.to_dict())
                self.unit.status = ActiveStatus(
                    f"incident open: {status} ({short_id})"
                )
                write_event({
                    "event": "incident-start",
                    "unit": unit_name,
                    "workload": status,
                    "first_seen": since_iso,
                    "incident_id": incident.id,
                    "timestamp": now.isoformat(),
                }, self.model.config.get("audit-log-path", ""))

                # Collect bounded context
                self.unit.status = MaintenanceStatus(
                    f"collecting context: {status} ({short_id})"
                )
                log_window = self.model.config.get("log-window-minutes", 30)
                max_lines = self.model.config.get("max-context-lines", 500)
                plan = read_diagnostics_file(self._diagnostics_path)
                context = collect_context(
                    unit_name, log_window, max_lines, diagnostics_plan=plan,
                )
                write_event({
                    "event": "context-collected",
                    "unit": unit_name,
                    "incident_id": incident.id,
                    "log_lines": len(context.get("unit_logs", [])),
                    "timestamp": now.isoformat(),
                }, self.model.config.get("audit-log-path", ""))

                # Generate report
                self.unit.status = MaintenanceStatus(
                    f"generating report: {status} ({short_id})"
                )
                base_report_path = generate_report(
                    incident_id=incident.id,
                    unit_name=unit_name,
                    workload=status,
                    first_seen=since_iso,
                    context=context,
                    report_dir=self.model.config.get("report-dir", ""),
                )
                with open(base_report_path) as f:
                    base_content = f.read()

                ai_suggestions, act_results = self._run_mode_logic(base_content)

                report_path = generate_report(
                    incident_id=incident.id,
                    unit_name=unit_name,
                    workload=status,
                    first_seen=since_iso,
                    context=context,
                    report_dir=self.model.config.get("report-dir", ""),
                    ai_suggestions=ai_suggestions,
                    act_results=act_results or None,
                )
                write_event({
                    "event": "report-generated",
                    "unit": unit_name,
                    "incident_id": incident.id,
                    "report_path": report_path,
                    "mode": self.model.config.get("mode", "observe"),
                    "timestamp": now.isoformat(),
                }, self.model.config.get("audit-log-path", ""))
                logger.info(
                    "incident %s: report written to %s",
                    short_id, report_path,
                )
                self.unit.status = ActiveStatus(
                    f"incident open: {status} ({short_id})"
                )

        except Exception as e:
            logger.warning("could not read principal goal-state: %s", e)

    def _on_principal_joined(self, event):
        logger.info("principal relation joined: %s", event.relation)
        self._ensure_diagnostics()

    def _on_principal_changed(self, event):
        logger.info("principal relation changed: %s", event.relation)

    def _on_principal_broken(self, event):
        logger.info("principal relation broken: %s", event.relation)
        self.unit.status = MaintenanceStatus("principal relation removed")

    def _ensure_diagnostics(self):
        diagnostics_raw = self.model.config.get("diagnostics", "")

        if diagnostics_raw:
            self._apply_diagnostics_config(diagnostics_raw)
        else:
            self._generate_diagnostics()

    def _apply_diagnostics_config(self, diagnostics_raw):
        try:
            plan = json.loads(diagnostics_raw)
        except json.JSONDecodeError as e:
            logger.error("diagnostics config is not valid JSON: %s", e)
            self.unit.status = BlockedStatus("invalid diagnostics config (not JSON)")
            return

        errors = validate_diagnostics(plan)
        if errors:
            logger.error("diagnostics config validation failed: %s", errors)
            self.unit.status = BlockedStatus(f"invalid diagnostics config: {errors[0]}")
            return

        write_diagnostics_file(plan, self._diagnostics_path)
        logger.info("diagnostics plan written to %s", self._diagnostics_path)
        self.unit.status = ActiveStatus("diagnostics configured")

    def _generate_diagnostics(self):
        principal_name = self._get_principal_name()
        if not principal_name:
            logger.warning("no principal name available, skipping diagnostics generation")
            self.unit.status = ActiveStatus("no principal to diagnose")
            return

        provider = self._get_ai_provider()
        if provider is None:
            logger.info("no AI provider configured, writing empty diagnostics plan")
            plan = make_empty_plan(principal_name)
            write_diagnostics_file(plan, self._diagnostics_path)
            self.unit.status = ActiveStatus("empty diagnostics plan (no AI)")
            return

        logger.info("generating diagnostics plan for '%s' via %s", principal_name, self.model.config.get("provider"))
        try:
            prompt = build_prompt(principal_name)
            response = provider.generate(prompt)
            plan = json.loads(response)
            plan["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        except Exception as e:
            logger.error("AI diagnostics generation failed: %s", e)
            self.unit.status = BlockedStatus("diagnostics generation failed")
            return

        errors = validate_diagnostics(plan)
        if errors:
            logger.error("AI generated invalid diagnostics plan: %s", errors)
            self.unit.status = BlockedStatus("AI generated invalid diagnostics")
            return

        write_diagnostics_file(plan, self._diagnostics_path)
        logger.info("AI-generated diagnostics plan written to %s", self._diagnostics_path)
        self.unit.status = ActiveStatus("diagnostics generated by AI")

    def _get_principal_name(self):
        try:
            rels = self.model.relations.get("principal", [])
            if rels:
                return rels[0].app.name
        except Exception:
            pass
        return None

    def _run_mode_logic(self, report_content: str) -> tuple[str, list]:
        """Run suggest or act logic based on the configured mode.

        Returns (ai_suggestions, act_results).
        Returns ("", []) in observe mode or when no provider is configured.
        """
        mode = self.model.config.get("mode", "observe")
        if mode not in ("suggest", "act"):
            return "", []

        provider = self._get_ai_provider()
        if provider is None:
            logger.warning("mode is '%s' but no AI provider is configured", mode)
            return "", []

        if mode == "suggest":
            suggestions = run_suggest(provider, report_content)
            return suggestions, []

        # act mode
        suggestions, act_results = run_act(provider, report_content)
        for result in act_results:
            write_event({
                "event": "act-command-executed",
                "command": result["command"],
                "returncode": result["returncode"],
                "stderr": result.get("stderr", ""),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }, self.model.config.get("audit-log-path", ""))
        return suggestions, act_results

    def _get_ai_provider(self):
        provider_name = self.model.config.get("provider", "none")
        if provider_name == "none":
            return None

        api_token = self.model.config.get("api-token", "")
        if not api_token:
            logger.warning("provider '%s' configured but api-token is empty", provider_name)
            return None

        model = self.model.config.get("model", "") or self._default_model(provider_name)

        if provider_name == "gemini":
            from jaime.providers.gemini import GeminiProvider
            return GeminiProvider(api_token, model)

        logger.warning("unsupported provider: %s", provider_name)
        return None

    @staticmethod
    def _default_model(provider_name):
        mapping = {"gemini": "gemini-2.0-flash"}
        return mapping.get(provider_name, "")

    def _on_action_diagnose(self, event):
        logger.info("diagnose action invoked")
        principal = None
        try:
            rels = self.model.relations.get("principal") or []
            if rels:
                rel = rels[0]
                principal = list(rel.units)[0].name if list(rel.units) else None
        except Exception:
            principal = None

        result = {
            "principal": {
                "unit": principal or "unknown",
                "status": "unknown",
                "charm_version": "unknown",
            },
            "jaime": {"unit": self.unit.name, "mode": self.model.config.get("mode")},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        event.set_results({"diagnose": result})

    def _on_action_collect_context(self, event):
        logger.info("collect-context action invoked")
        event.set_results({"context-path": "/var/lib/jaime/incidents/placeholder-context.json"})

    def _on_action_generate_report(self, event):
        """Generate and return the Markdown report for the current open incident."""
        logger.info("generate-report action invoked")

        # Find the current open incident across all tracked units.
        incident_id = None
        unit_name = None
        workload = None
        first_seen = None
        for uname, entry in self._status_tracker._state.items():
            inc = entry.get("incident")
            if inc and inc.get("closed_at") is None:
                incident_id = inc.get("id")
                unit_name = uname
                workload = entry.get("status", "unknown")
                first_seen = entry.get("since", "")
                break

        if not incident_id:
            event.fail("no open incident found")
            return

        log_window = self.model.config.get("log-window-minutes", 30)
        max_lines = self.model.config.get("max-context-lines", 500)
        report_dir = self.model.config.get("report-dir", "")

        plan = read_diagnostics_file(self._diagnostics_path)
        context = collect_context(
            unit_name, log_window, max_lines, diagnostics_plan=plan,
        )

        # Base report
        base_report_path = generate_report(
            incident_id=incident_id,
            unit_name=unit_name,
            workload=workload,
            first_seen=first_seen,
            context=context,
            report_dir=report_dir,
        )
        with open(base_report_path) as f:
            base_content = f.read()

        ai_suggestions, act_results = self._run_mode_logic(base_content)

        report_path = generate_report(
            incident_id=incident_id,
            unit_name=unit_name,
            workload=workload,
            first_seen=first_seen,
            context=context,
            report_dir=report_dir,
            ai_suggestions=ai_suggestions,
            act_results=act_results or None,
        )
        with open(report_path) as f:
            content = f.read()

        event.set_results({
            "incident-id": incident_id,
            "report-path": report_path,
            "report": content,
        })

    def _on_action_show_status(self, event):
        """Return the current monitoring state for all tracked principal units."""
        logger.info("show-status action invoked")
        state = self._status_tracker._state
        if not state:
            event.set_results({"result": "no status observed yet"})
            return
        results = {}
        for unit_name, entry in state.items():
            results.update({
                "unit": unit_name,
                "workload": entry.get("status", "unknown"),
                "first-seen": entry.get("since", ""),
                "increment": str(entry.get("increment", 0)),
                "last-reported": entry.get("last_reported") or "",
                "incident-id": (entry.get("incident") or {}).get("id", ""),
                "incident-opened-at": (entry.get("incident") or {}).get("opened_at", ""),
            })
        event.set_results(results)

    def _on_action_reset(self, event):
        """Close any open incidents, clear all status state, and return to Ready."""
        logger.info("reset action invoked")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for unit_name in list(self._status_tracker._state):
            if self._status_tracker.has_open_incident(unit_name):
                incident_dict = self._status_tracker.current_incident(unit_name)
                closed = Incident.from_dict(incident_dict).close()
                logger.info(json.dumps({
                    "event": "incident-closed",
                    "unit": unit_name,
                    "reason": "manual reset",
                    "incident": closed.to_dict(),
                    "timestamp": now,
                }))
        self._status_tracker._state = {}
        self._status_tracker._save()
        self.unit.status = ActiveStatus("Ready")
        logger.info("status state cleared")
        event.set_results({"result": "status state cleared"})


if __name__ == "__main__":
    main(JaimeCharm)
