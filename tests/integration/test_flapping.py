"""Integration test for the flapping-workload case.

Covers TASKS.md 5.2. Jaime anchors the incident timer on when it first
observed a unit go unhealthy (``unhealthy_since``), not on Juju's ``since``
field. Juju bumps ``since`` every time a charm re-sets its status, including
re-setting the same status with a new message, so a workload stuck in a retry
loop would otherwise reset the timer forever and never reach
``failure-timeout-minutes``.

The unit suite guards this logic directly; this test proves it survives a
real Juju status stream.

Requires a bootstrapped machine controller (LXD).
"""

import jubilant
import pytest

from .conftest import FAILURE_TIMEOUT_MINUTES

pytestmark = pytest.mark.integration

JAIME_APP = "jaime"
# Any charm whose workload status we can drive repeatedly. `any-charm` exposes
# an action for setting arbitrary statuses, which is exactly the flapping
# behaviour we need.
PRINCIPAL_APP = "any-charm"
PRINCIPAL_CHANNEL = "beta"


def _jaime_unit(juju: jubilant.Juju) -> str:
    return next(iter(juju.status().apps[JAIME_APP].units))


@pytest.fixture(scope="module")
def flapping_model(juju, machine_charm):
    juju.deploy(PRINCIPAL_APP, channel=PRINCIPAL_CHANNEL)
    juju.deploy(
        machine_charm,
        JAIME_APP,
        config={
            "mode": "observe",
            "provider": "none",
            "failure-timeout-minutes": FAILURE_TIMEOUT_MINUTES,
            "cooldown-minutes": 1,
            "watch-statuses": "error,blocked",
        },
    )
    juju.wait(lambda s: jubilant.all_active(s, PRINCIPAL_APP))
    juju.integrate(JAIME_APP, PRINCIPAL_APP)
    juju.wait(lambda s: jubilant.all_active(s, PRINCIPAL_APP, JAIME_APP))
    return juju


def _set_principal_status(juju, status: str, message: str):
    """Re-set the principal workload status, bumping Juju's `since` field."""
    juju.run(
        f"{PRINCIPAL_APP}/0",
        "rpc",
        {
            "method": "set_status",
            "kwargs": f'{{"status": "{status}", "message": "{message}"}}',
        },
    )


class TestFlappingWorkload:
    def test_repeated_status_resets_do_not_defer_incident(self, flapping_model):
        """Re-setting blocked with a new message must not restart the timer.

        Each re-set bumps Juju's `since`. If the timer were anchored there,
        the incident would never open. Anchored on `unhealthy_since`, it does.
        """
        juju = flapping_model
        unit = _jaime_unit(juju)

        # Flap the status repeatedly across a span longer than the timeout.
        for i in range(6):
            _set_principal_status(juju, "blocked", f"retry attempt {i}")
            juju.wait(
                lambda s: s.apps[PRINCIPAL_APP].units[f"{PRINCIPAL_APP}/0"]
                .workload_status.current == "blocked",
                timeout=120,
            )

        # Despite `since` having been bumped on every iteration, the incident
        # must still open once failure-timeout-minutes has elapsed since the
        # FIRST unhealthy observation.
        juju.wait(
            lambda s: "incident open" in s.apps[JAIME_APP].units[unit].workload_status.message,
            timeout=15 * 60,
        )

        task = juju.run(unit, "show-status")
        assert task.success
        assert task.results.get("incident-id")

    def test_first_seen_precedes_status_since(self, flapping_model):
        """show-status must expose both anchors, with first-seen the older."""
        juju = flapping_model
        task = juju.run(_jaime_unit(juju), "show-status")
        assert task.success

        first_seen = task.results.get("first-seen", "")
        status_since = task.results.get("status-since", "")
        assert first_seen and status_since
        # first-seen is when Jaime first saw the unit unhealthy; status-since
        # is Juju's last status bump, which the flapping above kept refreshing.
        assert first_seen <= status_since

    def test_flapping_between_watched_statuses_keeps_one_incident(self, flapping_model):
        """error <-> blocked flapping must not open a second incident."""
        juju = flapping_model
        unit = _jaime_unit(juju)

        before = juju.run(unit, "show-status").results.get("incident-id")

        _set_principal_status(juju, "error", "hook failed")
        _set_principal_status(juju, "blocked", "still broken")

        juju.wait(
            lambda s: "incident open" in s.apps[JAIME_APP].units[unit].workload_status.message,
            timeout=10 * 60,
        )

        after = juju.run(unit, "show-status").results.get("incident-id")
        assert after == before, "flapping between watched statuses opened a new incident"
