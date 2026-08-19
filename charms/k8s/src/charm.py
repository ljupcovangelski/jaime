#!/usr/bin/env python3
"""Jaime K8s charm — monitors Kubernetes application units in the same model.

Unlike the machine subordinate, this charm:
- runs as its own pod (not co-located with any principal)
- reads unit workload statuses from the Juju controller API using a
  dedicated Juju user account
- collects diagnostics from the Kubernetes API using the pod's in-cluster
  service account
"""

import datetime
import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from jaime.core import CoreMixin
from jaime.controller import (
    ControllerError,
    ControllerAuthError,
    JujuControllerClient,
    agent_conf_path,
    parse_agent_conf,
    extract_unit_statuses,
)
from jaime.principal import StatusTracker
from jaime.incident import Incident
from jaime.collector import collect_context

logger = logging.getLogger(__name__)


class JaimeK8sCharm(CoreMixin, CharmBase):
    """Jaime K8s charm — standalone pod monitoring other applications."""

    def __init__(self, *args):
        super().__init__(*args)
        self._status_tracker = StatusTracker()

        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._on_update_status)

        self.framework.observe(self.on.show_status_action, self._on_action_show_status)
        self.framework.observe(self.on.show_usage_action, self._on_action_show_usage)
        self.framework.observe(self.on.get_suggestion_action, self._on_action_get_suggestion)
        self.framework.observe(self.on.generate_report_action, self._on_action_generate_report)
        self.framework.observe(self.on.reset_action, self._on_action_reset)

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def _on_update_status(self, event):
        self._monitor()

    def _watch_applications(self) -> list[str]:
        raw = self.model.config.get("watch-applications", "")
        return [a.strip() for a in raw.split(",") if a.strip()]

    def _resolve_juju_password(self) -> str:
        """Resolve the Juju API password from config (plain or secret URI)."""
        return self._resolve_secret(
            self.model.config.get("juju-api-password", ""), "password"
        )

    def _monitor(self):
        """Fetch statuses and drive the incident lifecycle for each unit."""
        # Monitoring is opt-in: an empty watch-applications list means nothing
        # is monitored, never "all applications in the model".
        if not self._watch_applications():
            self.unit.status = ActiveStatus(
                "Ready — no apps in watch-applications"
            )
            return

        try:
            statuses = self._fetch_unit_statuses()
        except ControllerAuthError as e:
            logger.error("Juju controller authentication failed: %s", e)
            self.unit.status = BlockedStatus(
                "juju-api credentials rejected by controller"
            )
            return
        except ControllerError as e:
            logger.warning("could not fetch unit statuses: %s", e)
            self.unit.status = MaintenanceStatus(str(e)[:100])
            return

        if not statuses:
            self.unit.status = MaintenanceStatus("no units matched watch-applications")
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        for unit_name, info in statuses.items():
            status = info["status"]
            since_iso = info["since"] or now.isoformat()
            self._process_unit(unit_name, status, since_iso)

    # ------------------------------------------------------------------
    # Juju controller access
    # ------------------------------------------------------------------

    def _fetch_unit_statuses(self) -> dict[str, dict]:
        """Fetch per-unit workload statuses from the Juju controller API."""
        username = self.model.config.get("juju-api-user", "")
        password = self._resolve_juju_password()
        if not username or not password:
            raise ControllerError(
                "juju-api-user and juju-api-password must be configured"
            )

        conf_path = agent_conf_path(unit_name=self.unit.name)
        if conf_path is None:
            raise ControllerError("agent.conf not found — cannot locate controller")

        conf = parse_agent_conf(conf_path)
        with JujuControllerClient(
            conf["api_address"], conf["ca_cert"], conf["model_uuid"]
        ) as client:
            client.login(username, password)
            full = client.full_status()
        return extract_unit_statuses(
            full,
            watch_applications=self._watch_applications(),
        )

    def _fetch_app_config(self, app_name: str) -> dict:
        """Fetch an application's current config from the controller API."""
        username = self.model.config.get("juju-api-user", "")
        password = self._resolve_juju_password()
        if not username or not password:
            return {}
        conf_path = agent_conf_path(unit_name=self.unit.name)
        if conf_path is None:
            return {}
        try:
            conf = parse_agent_conf(conf_path)
            with JujuControllerClient(
                conf["api_address"], conf["ca_cert"], conf["model_uuid"]
            ) as client:
                client.login(username, password)
                info = client.application_get(app_name)
            return info.get("config", {})
        except Exception as e:
            logger.debug("could not fetch config for %s: %s", app_name, e)
            return {}

    # ------------------------------------------------------------------
    # Substrate hooks used by CoreMixin
    # ------------------------------------------------------------------

    def _collect_incident_context(self, unit_name: str, since_iso: str,
                                  incident: Incident) -> dict:
        """Collect Kubernetes diagnostic context (pod logs, spec, events)."""
        log_window = self.model.config.get("log-window-minutes", 30)
        max_lines = self.model.config.get("max-context-lines", 500)
        try:
            since_dt = datetime.datetime.fromisoformat(since_iso)
        except ValueError:
            since_dt = None

        context = collect_context(
            unit_name, log_window, max_lines, from_time=since_dt,
        )
        app_name = unit_name.split("/")[0]
        context["juju_config"] = self._fetch_app_config(app_name)
        return context

    def _collect_report_context(self, unit_name: str, since_iso: str) -> dict:
        """Collect context for a manually regenerated report."""
        log_window = self.model.config.get("log-window-minutes", 30)
        max_lines = self.model.config.get("max-context-lines", 500)
        try:
            since_dt = datetime.datetime.fromisoformat(since_iso)
        except ValueError:
            since_dt = None
        context = collect_context(
            unit_name, log_window, max_lines, from_time=since_dt,
        )
        app_name = unit_name.split("/")[0]
        context["juju_config"] = self._fetch_app_config(app_name)
        return context


if __name__ == "__main__":
    main(JaimeK8sCharm)
