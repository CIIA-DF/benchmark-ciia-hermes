"""A10: enabled config is distinct from scoped observed worker presence."""

import pytest
from sqlalchemy import delete, update

from contracts.execution import CapabilitiesResponse
from services.backend.auth import authenticate
from services.backend.schema import permissions, principals
from tests.backend import test_a5


@pytest.fixture
def clock(monkeypatch):
    return test_a5.clock.__wrapped__(monkeypatch)


def capability(client, name="simulation"):
    response = client.get("/capabilities", headers=client.operator_headers)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    parsed = CapabilitiesResponse.model_validate(response.json())
    return next(item for item in parsed.executors if item.name == name)


def test_enabled_without_worker_is_explicitly_unknown(client, clock, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "PRIVATE-api-model-is-not-worker-proof")
    value = capability(client)
    assert value.available is True and value.enabled is True
    assert value.worker_recent is False and value.last_seen_at is None
    assert value.model is None and value.configuration_known is False
    unavailable = capability(client, "hermes")
    assert unavailable.enabled is False and unavailable.available is False
    assert unavailable.worker_recent is False and unavailable.model is None


@pytest.mark.parametrize("age,recent", [(59.999, True), (60.0, True), (60.001, False)])
def test_empty_poll_is_recent_at_exact_sixty_second_boundary(client, clock, age, recent):
    assert client.post("/runs/claim", json={"executor": "simulation"}).status_code == 204
    observed = clock.now
    clock.now += age
    value = capability(client)
    assert value.worker_recent is recent and value.last_seen_at == observed
    assert value.available is True and value.enabled is True
    assert value.model is None and value.configuration_known is False


def test_disabled_configuration_does_not_erase_observed_presence(client, clock):
    assert client.post("/runs/claim", json={"executor": "simulation"}).status_code == 204
    client.app.state.execution.enabled = set()
    value = capability(client)
    assert value.available is False and value.enabled is False and value.worker_recent is True


@pytest.mark.parametrize("revocation", ["scope", "role", "executor"])
def test_presence_is_filtered_by_current_worker_profile_and_shared_scope(
    client, engine, clock, revocation
):
    assert client.post("/runs/claim", json={"executor": "simulation"}).status_code == 204
    assert capability(client).worker_recent is True
    actor = authenticate(engine, client.worker_headers["Authorization"])
    with engine.begin() as conn:
        if revocation == "scope":
            conn.execute(
                delete(permissions).where(permissions.c.principal_id == actor["principal_id"])
            )
        else:
            conn.execute(
                update(principals)
                .where(principals.c.principal_id == actor["principal_id"])
                .values(**{revocation: "operator" if revocation == "role" else "hermes"})
            )
    value = capability(client)
    assert value.worker_recent is False and value.last_seen_at is None


def test_capabilities_requires_operator_and_does_not_advertise_future_observation(client, clock):
    assert client.get("/capabilities").status_code == 403
    assert client.get("/capabilities", headers={"Authorization": ""}).status_code == 401
    assert client.post("/runs/claim", json={"executor": "simulation"}).status_code == 204
    clock.now -= 1
    value = capability(client)
    assert value.worker_recent is False and value.last_seen_at is None
