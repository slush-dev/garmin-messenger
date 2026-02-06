"""Tests for the members command."""

from __future__ import annotations

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID, MODULE, RECIPIENT_ID, USER_ID, USER_IDENTIFIER_1


class TestMembersHappyPath:
    """members shows a table of conversation members."""

    def test_table_header(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert "USER ID" in result.output
        assert "NAME" in result.output
        assert "ADDRESS" in result.output

    def test_member_data(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert "Alice" in result.output
        assert "Bob" in result.output
        assert USER_ID in result.output
        assert RECIPIENT_ID in result.output

    def test_user_identifier_shown(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert USER_IDENTIFIER_1 in result.output

    def test_exit_code_zero(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert result.exit_code == 0

    def test_separator_line(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert "-" * 20 in result.output


class TestMembersEmpty:
    """No members found."""

    def test_empty_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_members
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_empty_members
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert "No members found" in result.output
        assert result.exit_code == 0


class TestMembersAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr


class TestMembersHelp:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["members", "--help"])
        assert result.exit_code == 0
        assert "Show members" in result.output


class TestMembersApiError:
    def test_api_exception(self, cli_runner, mock_auth_class, mock_api_class):
        _, api = mock_api_class
        api.get_conversation_members.side_effect = RuntimeError("API error")
        result = cli_runner.invoke(cli, ["members", CONV_ID])
        assert result.exit_code != 0
