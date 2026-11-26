from __future__ import annotations

import copy

import pytest

from core.entitlements import Tier
from workflows import (
    CURRENT_SCHEMA_VERSION,
    WorkflowDefinition,
    WorkflowValidationError,
    export_workflow,
    import_workflow,
    limits_for_tier,
    validate_workflow,
)

BASE = {
    "name": "Welcome",
    "description": "Welcome new members.",
    "trigger_type": "member_join",
    "trigger_config": {},
    "conditions": [{"type": "account_age_lt", "days": 7}],
    "actions": [{"type": "send_message", "message": "Hello {user.mention}"}],
}


def test_validation_adds_versioned_metadata() -> None:
    result = validate_workflow(BASE)
    assert result["schema_version"] == CURRENT_SCHEMA_VERSION
    assert result["enabled"] is True
    assert result["description"] == "Welcome new members."
    assert result["workflow_id"] is None


def test_validation_rejects_unknown_fields() -> None:
    payload = copy.deepcopy(BASE)
    payload["malicious"] = "value"
    with pytest.raises(WorkflowValidationError) as exc:
        validate_workflow(payload)
    assert exc.value.field == "workflow"


def test_validation_rejects_unknown_action() -> None:
    payload = copy.deepcopy(BASE)
    payload["actions"] = [{"type": "run_shell", "command": "rm -rf /"}]
    with pytest.raises(WorkflowValidationError):
        validate_workflow(payload)


def test_portable_export_drops_guild_identifiers() -> None:
    payload = copy.deepcopy(BASE)
    payload.update(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "guild_id": 123,
            "definition_id": "19f6d3ba-5a3f-4b51-a3bc-2e4b98ad0a11",
            "revision": 4,
        }
    )
    exported = export_workflow(payload)
    assert "guild_id" not in exported
    assert "definition_id" not in exported
    assert "revision" not in exported
    assert import_workflow(exported) == exported
    assert WorkflowDefinition.from_mapping(exported).name == "Welcome"


def test_tier_limits_are_monotonic() -> None:
    assert limits_for_tier(Tier.FREE).max_active == 5
    assert limits_for_tier(Tier.BASIC).max_actions == 5
    assert limits_for_tier(Tier.PRO).max_active is None
