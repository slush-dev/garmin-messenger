"""Tests for the mute/unmute command."""

from __future__ import annotations

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID


class TestMuteDefault:
    """mute <id> mutes a conversation."""

    def test_calls_mute(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        result = cli_runner.invoke(cli, ["mute", CONV_ID])
        assert result.exit_code == 0
        api.mute_conversation.assert_called_once_with(CONV_ID, muted=True)

    def test_output(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        result = cli_runner.invoke(cli, ["mute", CONV_ID])
        assert "Muted" in result.output
        assert CONV_ID in result.output


class TestUnmute:
    """mute <id> --off unmutes a conversation."""

    def test_calls_unmute(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        result = cli_runner.invoke(cli, ["mute", CONV_ID, "--off"])
        assert result.exit_code == 0
        api.mute_conversation.assert_called_once_with(CONV_ID, muted=False)

    def test_output(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        result = cli_runner.invoke(cli, ["mute", CONV_ID, "--off"])
        assert "Unmuted" in result.output
        assert CONV_ID in result.output


class TestMuteAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["mute", CONV_ID])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestMuteMissingArg:
    """Missing conversation ID."""

    def test_missing_id(self, cli_runner):
        result = cli_runner.invoke(cli, ["mute"])
        assert result.exit_code != 0


class TestMuteHelp:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["mute", "--help"])
        assert result.exit_code == 0
        assert "Mute a conversation" in result.output
        assert "--off" in result.output
