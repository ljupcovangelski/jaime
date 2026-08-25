#!/usr/bin/env python3
"""Jaime charm — diagnostics plan generation on relation-joined."""

import datetime
import json
import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from jaime.core import CoreMixin
from jaime.diagnostics import (
    validate_diagnostics,
    build_prompt,
    write_diagnostics_file,
    read_diagnostics_file,
    make_empty_plan,
)
from jaime.principal import StatusTracker
from jaime.collector import collect_context
from jaime.logging import write_event
from ops.hookcmds import goal_state

logger = logging.getLogger(__name__)


class JaimeCharm(CoreMixin, CharmBase):
    _diagnostics_dir = "/var/lib/jaime"
    _diagnostics_path = f"{_diagnostics_dir}/diagnostics.json"

    def __init__(self, *args):
        super().__init__(*args)
        self._status_tracker = StatusTracker()

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.principal_relation_changed, self._on_principal_changed)
        self.framework.observe(self.on.principal_relation_joined, self._on_principal_joined)
        self.framework.observe(self.on.principal_relation_broken, self._on_principal_broken)

        self.framework.observe(self.on.diagnose_action, self._on_action_diagnose)
        self.framework.observe(self.on.collect_context_action, self._on_action_collect_context)
        self.framework.observe(self.on.generate_report_action, self._on_action_generate_report)
        self.framework.observe(self.on.get_suggestion_action, self._on_action_get_suggestion)
        self.framework.observe(self.on.show_status_action, self._on_action_show_status)
        self.framework.observe(self.on.show_usage_action, self._on_action_show_usage)
        self.framework.observe(self.on.reset_action, self._on_action_reset)

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

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
        """Read principal unit workload status via goal-state and drive incidents."""
        # Build the set of units actually related to this Jaime instance.
        # goal-state can return units from other relations on the same machine
        # (e.g. when two subordinates share a host), so we filter to our own
        # principal units.
        own_principal_units: set[str] = set()
        for rel in self.model.relations.get("principal", []):
            for unit in rel.units:
                own_principal_units.add(unit.name)

        try:
            gs = goal_state()
            principal_relations = gs.relations.get("principal", {})
            for unit_name, goal in principal_relations.items():
                if "/" not in unit_name:
                    continue
                if own_principal_units and unit_name not in own_principal_units:
                    continue

                status = goal.status
                since_iso = goal.since.isoformat()
                self._process_unit(unit_name, status, since_iso)
        except Exception as e:
            logger.warning("could not read principal goal-state: %s", e)

    # ------------------------------------------------------------------
    # Substrate hooks used by CoreMixin
    # ------------------------------------------------------------------

    def _collect_incident_context(self, unit_name: str, since_iso: str,
                                  incident: Incident) -> dict:
        """Collect local diagnostic context on the machine (plan-driven)."""
        log_window = self.model.config.get("log-window-minutes", 30)
        max_lines = self.model.config.get("max-context-lines", 500)
        try:
            from_dt = datetime.datetime.fromisoformat(since_iso)
        except ValueError:
            from_dt = None
        diagnostics_plan = read_diagnostics_file(self._diagnostics_path)

        context = collect_context(
            unit_name, log_window, max_lines,
            from_time=from_dt,
            diagnostics_plan=diagnostics_plan,
        )
        write_event({
            "event": "context-collected",
            "unit": unit_name,
            "incident_id": incident.id,
            "log_lines": len(context.get("unit_logs", [])),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }, self.model.config.get("audit-log-path", ""))
        return context

    def _collect_report_context(self, unit_name: str, since_iso: str) -> dict:
        """Collect context for a manually regenerated report."""
        log_window = self.model.config.get("log-window-minutes", 30)
        max_lines = self.model.config.get("max-context-lines", 500)
        diagnostics_plan = read_diagnostics_file(self._diagnostics_path)
        return collect_context(
            unit_name, log_window, max_lines,
            diagnostics_plan=diagnostics_plan,
        )

    # ------------------------------------------------------------------
    # Diagnostics plan
    # ------------------------------------------------------------------

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
        logger.info("monitoring plan written to %s", self._diagnostics_path)
        self.unit.status = ActiveStatus("Ready")

    def _generate_diagnostics(self):
        principal_name = self._get_principal_name()
        if not principal_name:
            logger.warning("no principal name available, skipping diagnostics generation")
            self.unit.status = ActiveStatus("no principal to diagnose")
            return

        provider, _ = self._get_ai_provider()
        if provider is None:
            logger.info("no AI provider configured, writing empty monitoring plan")
            plan = make_empty_plan(principal_name)
            write_diagnostics_file(plan, self._diagnostics_path)
            self.unit.status = ActiveStatus("Ready")
            return

        logger.info("generating diagnostics plan for '%s'", principal_name)
        try:
            prompt = build_prompt(principal_name)
            response, _ = provider.generate(prompt)
            logger.info("Diagnostics plan generated successfully")
            logger.debug("Diagnostics plan AI response:\n%s", response)

            # Gemini may wrap the JSON in markdown fences despite being asked not to.
            stripped = response.strip()
            if stripped.startswith("```"):
                lines = stripped.splitlines()
                inner = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
                stripped = inner.strip()

            if not stripped:
                raise ValueError("AI provider returned an empty response")

            plan = json.loads(stripped)
            plan["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        except Exception as e:
            logger.error("Diagnostics plan generation failed: %s — falling back to empty plan", e)
            plan = make_empty_plan(principal_name)
            write_diagnostics_file(plan, self._diagnostics_path)
            self.unit.status = ActiveStatus("Ready")
            return

        errors = validate_diagnostics(plan)
        if errors:
            logger.error("AI generated invalid monitoring plan: %s — falling back to empty plan", errors)
            plan = make_empty_plan(principal_name)
            write_diagnostics_file(plan, self._diagnostics_path)
            self.unit.status = ActiveStatus("Ready")
            return

        write_diagnostics_file(plan, self._diagnostics_path)
        logger.info("AI-generated monitoring plan written to %s", self._diagnostics_path)
        self.unit.status = ActiveStatus("Ready")

    def _get_principal_name(self):
        try:
            rels = self.model.relations.get("principal", [])
            if rels:
                return rels[0].app.name
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Actions (machine-specific)
    # ------------------------------------------------------------------

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
            "principal-unit": principal or "unknown",
            "jaime-unit": self.unit.name,
            "jaime-mode": self.model.config.get("mode"),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        event.set_results(result)

    def _on_action_collect_context(self, event):
        logger.info("collect-context action invoked")
        event.set_results({"context-path": "/var/lib/jaime/incidents/placeholder-context.json"})


if __name__ == "__main__":
    main(JaimeCharm)
