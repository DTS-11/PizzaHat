"""Regression checks for the minimal Discord command surface."""

from __future__ import annotations

import asyncio

import discord
import pytest

from cogs.setup import ACTIONS, CONDITIONS, TRIGGERS, WorkflowBuilder
from core.bot import INITIAL_EXTENSIONS, Lucent
from services.protection import CONTENT_MODULES
from workflows import (
    WorkflowValidationError,
    validate_supported_workflow,
    validate_workflow,
)


def _loaded_bot() -> Lucent:
    async def load() -> Lucent:
        bot = Lucent()
        bot.db = None
        for extension in INITIAL_EXTENSIONS:
            await bot.load_extension(extension)
        return bot

    bot = asyncio.run(load())
    return bot


def test_application_tree_is_minimal() -> None:
    bot = _loaded_bot()
    try:
        chat = {
            command.name
            for command in bot.tree.get_commands(type=discord.AppCommandType.chat_input)
        }
        assert chat == {"help", "status", "setup", "view_setup"}
        users = {
            command.name
            for command in bot.tree.get_commands(type=discord.AppCommandType.user)
        }
        messages = {
            command.name
            for command in bot.tree.get_commands(type=discord.AppCommandType.message)
        }
        assert users == {"Ban", "Kick", "Warn", "Timeout", "View Cases"}
        assert messages == {"Delete", "Warn Author"}
    finally:
        asyncio.run(bot.close())


def test_message_content_intent_is_enabled() -> None:
    bot = Lucent()
    try:
        assert bot.can_read_message_content is True
    finally:
        asyncio.run(bot.close())


def test_content_workflows_are_allowed_with_intent() -> None:
    text_workflow = {
        "trigger_type": "message_create",
        "trigger_config": {"contains_text": "!hello"},
        "conditions": [],
        "actions": [{"type": "send_message", "message": "hi"}],
    }
    validate_supported_workflow(text_workflow, can_read_message_content=True)


def test_content_workflows_are_rejected_without_intent() -> None:
    text_workflow = {
        "trigger_type": "message_create",
        "trigger_config": {"contains_text": "!hello"},
        "conditions": [],
        "actions": [{"type": "send_message", "message": "hi"}],
    }
    metadata_workflow = {
        "trigger_type": "member_join",
        "trigger_config": {},
        "conditions": [{"type": "account_age_lt", "days": 7}],
        "actions": [{"type": "send_message", "message": "hi"}],
    }
    try:
        validate_supported_workflow(text_workflow, can_read_message_content=False)
    except WorkflowValidationError:
        pass
    else:
        raise AssertionError("text workflow should be rejected")

    validate_supported_workflow(metadata_workflow, can_read_message_content=False)


def test_content_placeholder_is_rejected_without_intent() -> None:
    workflow = {
        "trigger_type": "member_join",
        "trigger_config": {},
        "conditions": [],
        "actions": [
            {"type": "send_message", "message": "You wrote: {content}"},
        ],
    }
    with pytest.raises(WorkflowValidationError):
        validate_supported_workflow(workflow, can_read_message_content=False)


def test_metadata_only_automod_modules_are_not_marked_unavailable() -> None:
    assert "message_spam" not in CONTENT_MODULES
    assert "mass_mentions" not in CONTENT_MODULES
    assert {"banned_words", "invites", "all_caps"} <= CONTENT_MODULES


def test_setup_builder_uses_valid_workflow_schema() -> None:
    for trigger in TRIGGERS:
        for condition in CONDITIONS:
            for action in ACTIONS:
                builder = WorkflowBuilder(1)
                builder.trigger = trigger
                builder.condition = condition
                builder.action = action
                builder.condition_value = {
                    "account_age_lt": "7",
                    "cooldown_sec": "60",
                    "is_bot": "true",
                    "safety_source": "any",
                    "safety_module": "automod",
                    "moderation_action": "warn",
                }.get(condition, "")
                builder.action_value = {
                    "add_role": "123456789012345678",
                    "remove_role": "123456789012345678",
                    "timeout_member": "10",
                    "open_ticket": "Support",
                }.get(action, "Hello from Lucent!")
                definition = validate_workflow(builder.definition())
                validate_supported_workflow(definition, can_read_message_content=False)


def test_setup_builder_rejects_non_numeric_values() -> None:
    builder = WorkflowBuilder(1)
    builder.condition = "account_age_lt"
    builder.condition_value = "soon"
    with pytest.raises(WorkflowValidationError):
        builder.definition()
