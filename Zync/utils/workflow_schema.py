"""Compatibility re-export for the workflow schema.

The implementation now lives in :mod:`workflows.schema`, which owns versioned
and portable definitions. This module stays importable for older integrations.
"""

from __future__ import annotations

from workflows.schema import (
    ACTION_TYPES,
    CONDITION_TYPES,
    CURRENT_SCHEMA_VERSION,
    MATCH_MODES,
    MODERATION_ACTIONS,
    SAFETY_SOURCES,
    SCHEDULED_TASK_KINDS,
    SCHEDULE_FREQUENCIES,
    SUPPORTED_SCHEMA_VERSIONS,
    TRIGGER_TYPES,
    WorkflowDefinition,
    WorkflowLimits,
    WorkflowValidationError,
    count_active_workflows,
    enforce_tier_limits,
    export_workflow,
    get_guild_tier,
    import_workflow,
    limits_for_tier,
    parse_jsonb,
    resolve_tier,
    validate_actions,
    validate_conditions,
    validate_trigger,
    validate_workflow,
)

__all__ = [
    "ACTION_TYPES",
    "CONDITION_TYPES",
    "CURRENT_SCHEMA_VERSION",
    "MATCH_MODES",
    "MODERATION_ACTIONS",
    "SAFETY_SOURCES",
    "SCHEDULED_TASK_KINDS",
    "SCHEDULE_FREQUENCIES",
    "SUPPORTED_SCHEMA_VERSIONS",
    "TRIGGER_TYPES",
    "WorkflowDefinition",
    "WorkflowLimits",
    "WorkflowValidationError",
    "count_active_workflows",
    "enforce_tier_limits",
    "export_workflow",
    "get_guild_tier",
    "import_workflow",
    "limits_for_tier",
    "parse_jsonb",
    "resolve_tier",
    "validate_actions",
    "validate_conditions",
    "validate_trigger",
    "validate_workflow",
]
