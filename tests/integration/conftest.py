"""Shared fixtures for Jaime integration tests.

These tests drive a real Juju controller. They are excluded from the default
unit sweep (root ``pyproject.toml`` sets ``testpaths = ["tests/unit"]``) and
must be invoked explicitly:

    make integration          # both substrates
    make integration-machine  # machine subordinate only
    make integration-k8s      # Kubernetes standalone only

Each substrate needs an appropriate controller to be bootstrapped and
selected: a machine cloud (LXD) for the machine charm, a Kubernetes cloud
(MicroK8s) for the k8s charm.
"""

import os
import pathlib

import jubilant
import pytest

DIST_DIR = pathlib.Path(__file__).resolve().parents[2] / "dist"

MACHINE_CHARM_GLOB = "jaime_*.charm"
K8S_CHARM_GLOB = "jaime-k8s_*.charm"

# The k8s RoleBinding in charms/k8s/jaime-k8s-rbac.yaml is bound to the
# jaime-k8s ServiceAccount, which Juju names after the application. Deploying
# under any other name yields empty log and event sections.
K8S_APP_NAME = "jaime-k8s"

# Kept short so incidents open within the lifetime of a test rather than the
# five-minute production default.
FAILURE_TIMEOUT_MINUTES = 1


def _charm_path(glob: str) -> pathlib.Path:
    """Locate a packed charm, failing with a build hint if it is missing."""
    matches = sorted(DIST_DIR.glob(glob))
    if not matches:
        pytest.fail(
            f"No charm matching {glob!r} in {DIST_DIR}. Run `make pack-all` first."
        )
    return matches[-1]


def pytest_addoption(parser):
    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="Do not tear down the temporary Juju model, for post-mortem debugging.",
    )


@pytest.fixture(scope="module")
def keep_models(request) -> bool:
    return bool(request.config.getoption("--keep-models"))


@pytest.fixture(scope="module")
def juju(keep_models):
    """A temporary Juju model, torn down at the end of the module."""
    with jubilant.temp_model(keep=keep_models) as juju:
        juju.wait_timeout = 10 * 60
        yield juju
        if keep_models:
            print(f"\nKeeping model {juju.model!r} for inspection.")


@pytest.fixture(scope="module")
def machine_charm() -> pathlib.Path:
    return _charm_path(MACHINE_CHARM_GLOB)


@pytest.fixture(scope="module")
def k8s_charm() -> pathlib.Path:
    return _charm_path(K8S_CHARM_GLOB)


@pytest.fixture(scope="session")
def ai_token() -> str:
    """AI provider token, or empty when unset.

    Tests that need a real provider skip when this is empty, so the suite
    stays runnable offline. The token is never written to a report or log.
    """
    return os.environ.get("JAIME_TEST_API_TOKEN", "")


@pytest.fixture(scope="session")
def ai_provider() -> str:
    return os.environ.get("JAIME_TEST_PROVIDER", "gemini")
