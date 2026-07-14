#!/usr/bin/env python3
"""Jaime charm — diagnostics plan generation on relation-joined."""

import json
import logging
import datetime

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from jaime.diagnostics import (
    validate_diagnostics,
    build_prompt,
    write_diagnostics_file,
    make_empty_plan,
)
from jaime.principal import StatusTracker

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

    def _on_update_status(self, event):
        try:
            relations = list(self.model.relations.get("principal", []))
        except Exception:
            relations = []

        if relations:
            self._log_principal_status()
            self.unit.status = ActiveStatus("Ready")
        else:
            self.unit.status = MaintenanceStatus("waiting for principal relation")

    def _log_principal_status(self):
        """Read principal unit workload status via goal-state and emit a JSON debug log.

        On every tick, logs the status of watched units.

        An INCIDENT is generated when:
          - the status has persisted for at least failure-timeout-minutes, AND
          - no incident has been generated yet, OR cooldown-minutes have elapsed
            since the last incident for this unit.
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
                increment = self._status_tracker.observe(unit_name, status, since_iso)

                if status not in watch_statuses:
                    if increment == 1:
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
                    continue

                # Always log the current watched status.
                entry = {
                    "event": "principal-status-watched",
                    "unit": unit_name,
                    "workload": status,
                    "first_seen": since_iso,
                    "increment": increment,
                    "timestamp": now.isoformat(),
                }
                logger.debug(json.dumps(entry))

                # Check whether failure-timeout has elapsed.
                unhealthy_minutes = (now - goal.since).total_seconds() / 60
                if unhealthy_minutes < failure_timeout:
                    logger.debug(
                        "principal unit %s: unhealthy for %.1f min, "
                        "waiting for failure-timeout (%d min)",
                        unit_name, unhealthy_minutes, failure_timeout,
                    )
                    continue

                # Check cooldown: skip if an incident was already generated recently.
                last_reported_iso = self._status_tracker.last_reported(unit_name)
                if last_reported_iso:
                    last_reported_dt = datetime.datetime.fromisoformat(last_reported_iso)
                    cooldown_elapsed = (now - last_reported_dt).total_seconds() / 60
                    if cooldown_elapsed < cooldown:
                        logger.debug(
                            "principal unit %s: cooldown active (%.1f / %d min elapsed)",
                            unit_name, cooldown_elapsed, cooldown,
                        )
                        continue

                # Generate incident.
                logger.info(
                    "INCIDENT unit=%s workload=%s first_seen=%s increment=%d",
                    unit_name, status, since_iso, increment,
                )
                self._status_tracker.record_reported(unit_name, now.isoformat())

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
        event.set_results({"context_path": "/var/lib/jaime/incidents/placeholder-context.json"})

    def _on_action_generate_report(self, event):
        logger.info("generate-report action invoked")
        event.set_results({"report_path": "/var/log/jaime/reports/placeholder-report.md"})


if __name__ == "__main__":
    main(JaimeCharm)
