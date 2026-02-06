"""Tests for the conversations command."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID, MODULE, RECIPIENT_ID, USER_ID


class TestConversationsHappyPath:
    """conversations lists a table of conversations."""

    def test_table_header(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        assert "CONVERSATION ID" in result.output
        assert "MEMBERS" in result.output
        assert "UPDATED" in result.output
        assert "MUTED" in result.output

    def test_row_data_conv_id(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        assert CONV_ID in result.output

    def test_row_data_members(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        assert USER_ID in result.output
        assert RECIPIENT_ID in result.output

    def test_row_data_date(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        assert "2025-01-15" in result.output

    def test_muted_status_no(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        # isMuted=False → "no"
        assert "no" in result.output

    def test_exit_code_zero(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        assert result.exit_code == 0

    def test_separator_line(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["conversations"])
        assert "-" * 20 in result.output


class TestConversationsEmpty:
    """No conversations found."""

    def test_empty_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_conversations
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_empty_conversations
        result = cli_runner.invoke(cli, ["conversations"])
        assert "No conversations found" in result.output
        assert result.exit_code == 0


class TestConversationsOptions:
    """--limit, --help, defaults."""

    def test_default_limit(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_conversations
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_empty_conversations
        cli_runner.invoke(cli, ["conversations"])
        api.get_conversations.assert_called_once_with(limit=20)

    def test_custom_limit(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_conversations
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_empty_conversations
        cli_runner.invoke(cli, ["conversations", "--limit", "5"])
        api.get_conversations.assert_called_once_with(limit=5)

    def test_short_flag_n(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_conversations
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_empty_conversations
        cli_runner.invoke(cli, ["conversations", "-n", "10"])
        api.get_conversations.assert_called_once_with(limit=10)

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["conversations", "--help"])
        assert result.exit_code == 0
        assert "List recent conversations" in result.output


class TestConversationsAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["conversations"])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestConversationsApiError:
    """API errors propagate."""

    def test_api_exception(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        _, api = mock_api_class
        api.get_conversations.side_effect = RuntimeError("API error")
        result = cli_runner.invoke(cli, ["conversations"])
        assert result.exit_code != 0


class TestConversationsVerbose:
    """Verbose mode."""

    def test_verbose(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_conversations
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_empty_conversations
        result = cli_runner.invoke(cli, ["--verbose", "conversations"])
        assert result.exit_code == 0
