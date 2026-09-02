"""Tests for dependency access through the handler context."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from practice_runtime.errors import ConfigurationError

from practice_bot.context import (
    BotContext,
    BotDependencies,
    install_dependencies,
)
from tests.conftest import ADMIN_ID, USER_ID


class TestDependencies:
    """Tests for reaching the dependencies from a context."""

    def test_exposes_the_installed_dependencies(
        self, dependencies: BotDependencies
    ) -> None:
        bot_data: dict[object, object] = {}
        install_dependencies(bot_data, dependencies)
        context = BotContext(application=Mock(bot_data=bot_data))

        assert context.dependencies is dependencies
        assert context.repository is dependencies.repository
        assert context.agents is dependencies.agents
        assert context.sessions is dependencies.sessions

    def test_missing_dependencies_are_a_configuration_error(self) -> None:
        context = BotContext(application=Mock(bot_data={}))

        with pytest.raises(ConfigurationError, match="dependencies are missing"):
            _ = context.dependencies


class TestAdminChecks:
    """Tests for the access-control questions handlers ask."""

    def test_disabled_without_an_admin(self, dependencies: BotDependencies) -> None:
        assert dependencies.access_control_enabled is False
        assert dependencies.is_admin(USER_ID) is False

    def test_enabled_with_an_admin(self, dependencies: BotDependencies) -> None:
        guarded = replace(dependencies, admin_user_id=ADMIN_ID)

        assert guarded.access_control_enabled is True
        assert guarded.is_admin(ADMIN_ID) is True
        assert guarded.is_admin(USER_ID) is False
