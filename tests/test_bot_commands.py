"""Tests for the command menu."""

from english_practice.bot import commands


class TestMenu:
    """Tests for what Telegram is told about."""

    def test_menu_matches_the_declared_commands(self) -> None:
        menu = commands.menu()

        assert [entry.command for entry in menu] == [
            command.name for command in commands.COMMANDS
        ]

    def test_every_command_is_described(self) -> None:
        assert all(command.description for command in commands.COMMANDS)

    def test_admin_commands_stay_out_of_the_public_menu(self) -> None:
        names = {entry.command for entry in commands.menu()}

        assert names.isdisjoint({command.name for command in commands.ADMIN_COMMANDS})


class TestHelpText:
    """Tests for the /help body."""

    def test_lists_every_public_command(self) -> None:
        text = commands.help_text()

        for command in commands.COMMANDS:
            assert command.slash in text

    def test_admin_commands_are_opt_in(self) -> None:
        assert "/pending" not in commands.help_text()
        assert "/pending" in commands.help_text(include_admin=True)
