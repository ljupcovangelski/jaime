#!/usr/bin/env python3
"""
Minimal Jaime charm skeleton.

This file implements a light-weight operator framework charm that registers basic
event handlers and dummy actions. The handlers intentionally do not implement
the production logic — they provide a safe scaffold to iterate on.
"""
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus
import logging
import datetime

logger = logging.getLogger(__name__)


class JaimeCharm(CharmBase):
    """A minimal charm skeleton for Jaime.

    This charm provides the basic hooks and actions so the charm can be built,
    deployed, and related. Core logic (incident lifecycle, collectors, reports)
    will be implemented in later tasks.
    """

    def __init__(self, *args):
        super().__init__(*args)

        # Observe basic framework and relation events
        self.framework.observe(self.on.update_status, self._on_update_status)
        # Relation endpoint name comes from metadata.yaml as 'principal'
        self.framework.observe(self.on.principal_relation_changed, self._on_principal_changed)
        self.framework.observe(self.on.principal_relation_joined, self._on_principal_joined)
        self.framework.observe(self.on.principal_relation_broken, self._on_principal_broken)

        # Actions
        self.framework.observe(self.on.diagnose_action, self._on_action_diagnose)
        self.framework.observe(self.on.collect_context_action, self._on_action_collect_context)
        self.framework.observe(self.on.generate_report_action, self._on_action_generate_report)

        # Start in maintenance until the charm has run its first update-status
        self.unit.status = MaintenanceStatus("initialising")

    def _on_update_status(self, event):
        # Minimal status handling: if related principal exists, become Active.
        try:
            relations = list(self.model.relations.get("principal", []))
        except Exception:
            relations = []

        if relations:
            self.unit.status = ActiveStatus("Ready")
        else:
            # If not related yet, remain in maintenance so operators can see the state
            self.unit.status = MaintenanceStatus("waiting for principal relation")

    # Relation handlers are intentionally minimal and non-mutating;
    # they exist so the charm can be related without errors.
    def _on_principal_joined(self, event):
        logger.info("principal relation joined: %s", event.relation)
        # No data exchange in the scaffold

    def _on_principal_changed(self, event):
        logger.info("principal relation changed: %s", event.relation)

    def _on_principal_broken(self, event):
        logger.info("principal relation broken: %s", event.relation)
        # Ensure status reflects that relation was removed
        self.unit.status = MaintenanceStatus("principal relation removed")

    # Dummy actions — they return minimal, safe results and write no files.
    def _on_action_diagnose(self, event):
        logger.info("diagnose action invoked")
        principal = None
        try:
            rels = self.model.relations.get("principal") or []
            if rels:
                rel = rels[0]
                # Best-effort principal unit name
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
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
        event.set_results({"diagnose": result})

    def _on_action_collect_context(self, event):
        logger.info("collect-context action invoked")
        # Scaffold: no file I/O yet. Return a placeholder path.
        event.set_results({"context_path": "/var/lib/jaime/incidents/placeholder-context.json"})

    def _on_action_generate_report(self, event):
        logger.info("generate-report action invoked")
        # Scaffold: no AI calls or filesystem writes. Return placeholder path.
        event.set_results({"report_path": "/var/log/jaime/reports/placeholder-report.md"})


if __name__ == "__main__":
    main(JaimeCharm)
