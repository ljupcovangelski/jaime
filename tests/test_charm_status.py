"""Unit tests for _log_principal_status in JaimeCharm."""

from ops.testing import Harness
from charm import JaimeCharm
from jaime.principal import StatusTracker

import datetime
import json
import logging
import sys
import unittest.mock as mock

sys.path.insert(0, "src")

# Fixed timestamps used across tests
SINCE = datetime.datetime(2026, 7, 13, 10, 0, 0, tzinfo=datetime.timezone.utc)
SINCE_ISO = SINCE.isoformat()

_DEFAULT_CONFIG = {
    "watch-statuses": "error,blocked",
    "failure-timeout-minutes": 5,
    "cooldown-minutes": 30,
}


def make_goal_relations(status, since=SINCE):
    """Return a goal-state relations dict for the principal endpoint."""
    unit_goal = mock.MagicMock()
    unit_goal.status = status
    unit_goal.since = since
    app_goal = mock.MagicMock()
    app_goal.status = "joined"
    app_goal.since = since
    return {"postgresql/0": unit_goal, "postgresql": app_goal}


def make_harness(tmp_path, config_overrides=None):
    """Return a started Harness with diagnostics side-effects suppressed."""
    cfg = {**_DEFAULT_CONFIG, **(config_overrides or {})}
    with mock.patch.object(JaimeCharm, "_ensure_diagnostics"):
        h = Harness(JaimeCharm)
        h.update_config(cfg)
        h.begin()
    h.charm._status_tracker = StatusTracker(state_path=str(tmp_path / "state.json"))
    return h


def call_log_status(harness, goal_relations, now):
    """Call _log_principal_status with mocked goal_state and datetime."""
    gs = mock.MagicMock()
    gs.relations = {"principal": goal_relations}

    log_records = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_records.append(record)

    handler = CapturingHandler()
    charm_logger = logging.getLogger("charm")
    charm_logger.addHandler(handler)
    charm_logger.setLevel(logging.DEBUG)

    try:
        with mock.patch("ops.hookcmds.goal_state", return_value=gs), \
             mock.patch("charm.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.datetime.fromisoformat = datetime.datetime.fromisoformat
            mock_dt.timezone.utc = datetime.timezone.utc
            harness.charm._log_principal_status()
    finally:
        charm_logger.removeHandler(handler)

    return log_records


class TestWatchedStatusLogged:
    def test_blocked_emits_json_event(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=10)
        records = call_log_status(h, make_goal_relations("blocked"), now)

        watched = [r for r in records if "principal-status-watched" in r.getMessage()]
        assert len(watched) == 1
        entry = json.loads(watched[0].getMessage())
        assert entry["event"] == "principal-status-watched"
        assert entry["unit"] == "postgresql/0"
        assert entry["workload"] == "blocked"
        assert entry["first_seen"] == SINCE_ISO
        assert entry["increment"] == 1

    def test_active_not_in_watched_emits_no_json_event(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=10)
        records = call_log_status(h, make_goal_relations("active"), now)
        assert not any("principal-status-watched" in r.getMessage() for r in records)

    def test_custom_watch_statuses_respected(self, tmp_path):
        h = make_harness(tmp_path, config_overrides={"watch-statuses": "error"})
        now = SINCE + datetime.timedelta(minutes=10)
        records = call_log_status(h, make_goal_relations("blocked"), now)
        assert not any("principal-status-watched" in r.getMessage() for r in records)

    def test_increment_increases_on_consecutive_ticks(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=10)
        call_log_status(h, make_goal_relations("blocked"), now)
        records = call_log_status(h, make_goal_relations("blocked"), now)
        watched = [r for r in records if "principal-status-watched" in r.getMessage()]
        assert json.loads(watched[0].getMessage())["increment"] == 2


class TestFailureTimeout:
    def test_no_incident_before_timeout(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=2)
        records = call_log_status(h, make_goal_relations("blocked"), now)
        assert not any("INCIDENT" in r.getMessage() for r in records)
        assert any("waiting for failure-timeout" in r.getMessage() for r in records)

    def test_incident_after_timeout(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=6)
        records = call_log_status(h, make_goal_relations("blocked"), now)
        assert any("INCIDENT" in r.getMessage() for r in records)

    def test_incident_at_exactly_timeout(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=5)
        records = call_log_status(h, make_goal_relations("blocked"), now)
        assert any("INCIDENT" in r.getMessage() for r in records)

    def test_incident_contains_first_seen(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=6)
        records = call_log_status(h, make_goal_relations("blocked"), now)
        incident = next(r for r in records if "INCIDENT" in r.getMessage())
        assert SINCE_ISO in incident.getMessage()


class TestCooldown:
    def test_second_incident_suppressed_within_cooldown(self, tmp_path):
        h = make_harness(tmp_path)
        first_now = SINCE + datetime.timedelta(minutes=10)
        records1 = call_log_status(h, make_goal_relations("blocked"), first_now)
        assert any("INCIDENT" in r.getMessage() for r in records1)

        second_now = SINCE + datetime.timedelta(minutes=20)
        records2 = call_log_status(h, make_goal_relations("blocked"), second_now)
        assert not any("INCIDENT" in r.getMessage() for r in records2)
        assert any("cooldown active" in r.getMessage() for r in records2)

    def test_second_incident_fires_after_cooldown(self, tmp_path):
        h = make_harness(tmp_path)
        first_now = SINCE + datetime.timedelta(minutes=10)
        call_log_status(h, make_goal_relations("blocked"), first_now)

        second_now = SINCE + datetime.timedelta(minutes=45)
        records = call_log_status(h, make_goal_relations("blocked"), second_now)
        assert any("INCIDENT" in r.getMessage() for r in records)


class TestRecovery:
    def test_recovery_emits_recovered_event(self, tmp_path):
        h = make_harness(tmp_path)
        h.charm._status_tracker.observe("postgresql/0", "blocked", SINCE_ISO)

        recovery_since = SINCE + datetime.timedelta(minutes=30)
        now = SINCE + datetime.timedelta(minutes=35)
        records = call_log_status(h, make_goal_relations("active", since=recovery_since), now)

        recovered = [r for r in records if "principal-status-recovered" in r.getMessage()]
        assert len(recovered) == 1
        entry = json.loads(recovered[0].getMessage())
        assert entry["event"] == "principal-status-recovered"
        assert entry["unit"] == "postgresql/0"
        assert entry["workload"] == "active"

    def test_new_episode_same_status_clears_cooldown(self, tmp_path):
        """Same status string but new since → new episode → cooldown cleared."""
        h = make_harness(tmp_path)
        since_1 = SINCE
        since_2 = SINCE + datetime.timedelta(hours=1)

        h.charm._status_tracker.observe("postgresql/0", "blocked", since_1.isoformat())
        h.charm._status_tracker.record_reported(
            "postgresql/0", (since_1 + datetime.timedelta(minutes=10)).isoformat()
        )

        now_2 = since_2 + datetime.timedelta(minutes=10)
        records = call_log_status(h, make_goal_relations("blocked", since=since_2), now_2)
        assert any("INCIDENT" in r.getMessage() for r in records)
        assert not any("cooldown active" in r.getMessage() for r in records)

    def test_recovery_resets_increment_to_one(self, tmp_path):
        h = make_harness(tmp_path)
        now = SINCE + datetime.timedelta(minutes=10)
        call_log_status(h, make_goal_relations("blocked"), now)
        call_log_status(h, make_goal_relations("blocked"), now)

        recovery_since = SINCE + datetime.timedelta(minutes=20)
        call_log_status(h, make_goal_relations("active", since=recovery_since), now)

        assert h.charm._status_tracker._state["postgresql/0"]["increment"] == 1


class TestGoalStateError:
    def test_goal_state_exception_logs_warning(self, tmp_path):
        h = make_harness(tmp_path)
        log_records = []

        class Cap(logging.Handler):
            def emit(self, r):
                log_records.append(r)

        handler = Cap()
        charm_logger = logging.getLogger("charm")
        charm_logger.addHandler(handler)
        charm_logger.setLevel(logging.WARNING)
        try:
            with mock.patch("ops.hookcmds.goal_state", side_effect=RuntimeError("socket error")):
                h.charm._log_principal_status()
        finally:
            charm_logger.removeHandler(handler)

        assert any("could not read principal goal-state" in r.getMessage() for r in log_records)
