"""Tests for the muted command."""

from __future__ import annotations

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID


class TestMutedHappyPath:
    """muted lists muted conversations."""

    def test_table_header(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["muted"])
        assert "CONVERSATION ID" in result.output
        assert "EXPIRES" in result.output

    def test_row_data(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["muted"])
        assert CONV_ID in result.output
        assert "2025-02-01" in result.output

    def test_exit_code_zero(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["muted"])
        assert result.exit_code == 0

    def test_separator_line(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["muted"])
        assert "-" * 20 in result.output


class TestMutedEmpty:
    """No muted conversations."""

    def test_empty_message(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = []
        result = cli_runner.invoke(cli, ["muted"])
        assert "No muted conversations" in result.output
        assert result.exit_code == 0


class TestMutedNeverExpiry:
    """Muted conversation without expiry shows 'never'."""

    def test_never_expiry(self, cli_runner, mock_auth_class, mock_api_class):
        from uuid import UUID

        from garmin_messenger.models import ConversationMuteDetailModel
        _, api = mock_api_class
        api.get_muted_conversations.return_value = [
            ConversationMuteDetailModel(conversationId=UUID(CONV_ID), expires=None),
        ]
        result = cli_runner.invoke(cli, ["muted"])
        assert "never" in result.output


class TestMutedAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["muted"])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestMutedHelp:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["muted", "--help"])
        assert result.exit_code == 0
        assert "List muted conversations" in result.output
