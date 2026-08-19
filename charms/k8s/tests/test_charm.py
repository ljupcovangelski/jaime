"""Unit tests for JaimeK8sCharm substrate-specific behaviour.

Shared CoreMixin behaviour (config validation, incident status preservation,
provider resolution, usage summary) is tested once in test_core.py. This file
covers only what is specific to the k8s charm.
"""

import unittest.mock as mock

from ops.model import ActiveStatus, MaintenanceStatus
from ops.testing import Harness

from charm import JaimeK8sCharm


def _make_harness(config_overrides=None):
    h = Harness(JaimeK8sCharm)
    h.begin()
    if config_overrides:
        h.update_config(config_overrides)
    return h


class TestWatchApplications:
    def test_empty_watch_applications_monitors_nothing(self):
        """Empty watch-applications means opt-out — no API call is made."""
        h = _make_harness({"watch-applications": ""})
        with mock.patch.object(h.charm, "_fetch_unit_statuses") as mock_fetch:
            h.charm._monitor()
        mock_fetch.assert_not_called()
        assert isinstance(h.charm.unit.status, ActiveStatus)
        assert "watch-applications" in h.charm.unit.status.message

    def test_watch_applications_parsing(self):
        h = _make_harness({"watch-applications": " postgresql-k8s, mysql-k8s "})
        assert h.charm._watch_applications() == ["postgresql-k8s", "mysql-k8s"]

    def test_watch_applications_empty_parsing(self):
        h = _make_harness({"watch-applications": ""})
        assert h.charm._watch_applications() == []

    def test_with_apps_selected_calls_fetch(self):
        h = _make_harness({"watch-applications": "postgresql-k8s"})
        with mock.patch.object(h.charm, "_fetch_unit_statuses", return_value={}):
            h.charm._monitor()
        # fetch called; empty result -> maintenance status
        assert isinstance(h.charm.unit.status, MaintenanceStatus)
