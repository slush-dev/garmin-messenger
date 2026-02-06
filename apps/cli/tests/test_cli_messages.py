"""Tests for the messages command."""

from __future__ import annotations

from uuid import UUID

import pytest

from garmin_messenger.models import ConversationDetailModel, ConversationMessageModel, ConversationMetaModel, UserLocation

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID, LAST_MSG_ID, MODULE, MSG_ID, RECIPIENT_ID, USER_ID


class TestMessagesHappyPath:
    """messages shows formatted message list."""

    def test_header(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert f"Messages in {CONV_ID}" in result.output

    def test_sender_displayed(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert USER_ID in result.output
        assert RECIPIENT_ID in result.output

    def test_message_id_hidden_by_default(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert MSG_ID not in result.output

    def test_message_id_displayed_with_uuid(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", "--uuid", CONV_ID])
        assert MSG_ID in result.output

    def test_body_displayed(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "Hello!" in result.output
        assert "Hi back!" in result.output

    def test_timestamp_displayed(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "2025-01-15" in result.output

    def test_missing_sender_shows_question_mark(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        """from_=None → '?' in output."""
        detail = ConversationDetailModel(
            metaData=ConversationMetaModel(
                conversationId=UUID(CONV_ID),
                memberIds=[USER_ID],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            ),
            messages=[
                ConversationMessageModel(
                    messageId=UUID(MSG_ID),
                    messageBody="No sender",
                    from_=None,
                    sentAt="2025-01-15T10:30:00Z",
                )
            ],
            limit=50,
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "?" in result.output
        assert "No sender" in result.output

    def test_body_truncation_at_120(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        """Long bodies are truncated to 120 chars."""
        long_body = "A" * 200
        detail = ConversationDetailModel(
            metaData=ConversationMetaModel(
                conversationId=UUID(CONV_ID),
                memberIds=[USER_ID],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            ),
            messages=[
                ConversationMessageModel(
                    messageId=UUID(MSG_ID),
                    messageBody=long_body,
                    from_=USER_ID,
                    sentAt="2025-01-15T10:30:00Z",
                )
            ],
            limit=50,
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        # Should not contain the full 200-char body
        assert "A" * 200 not in result.output
        assert "A" * 120 in result.output

    def test_missing_timestamp_shows_question_mark(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        detail = ConversationDetailModel(
            metaData=ConversationMetaModel(
                conversationId=UUID(CONV_ID),
                memberIds=[USER_ID],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            ),
            messages=[
                ConversationMessageModel(
                    messageId=UUID(MSG_ID),
                    messageBody="No time",
                    from_=USER_ID,
                    sentAt=None,
                )
            ],
            limit=50,
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "[?]" in result.output

    def test_exit_code_zero(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert result.exit_code == 0


class TestMessagesLocation:
    """Location display in messages."""

    def test_location_displayed(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_with_location,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_with_location
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "@ 45.5231, -122.6765, 15.0m" in result.output

    def test_no_location_no_marker(
        self,
        cli_runner,
        mock_auth_class,
        mock_api_class,
        sample_conversation_detail_result,
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "@ " not in result.output

    def _detail_with_message(self, **msg_kwargs):
        """Build a ConversationDetailModel with a single message."""
        return ConversationDetailModel(
            metaData=ConversationMetaModel(
                conversationId=UUID(CONV_ID),
                memberIds=[USER_ID],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            ),
            messages=[
                ConversationMessageModel(
                    messageId=UUID(MSG_ID),
                    messageBody="test",
                    from_=USER_ID,
                    sentAt="2025-01-15T10:30:00Z",
                    **msg_kwargs,
                )
            ],
            limit=50,
        )

    def test_reference_point_displayed(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        detail = self._detail_with_message(
            referencePoint=UserLocation(
                latitudeDegrees=50.0, longitudeDegrees=14.0, elevationMeters=200.0
            ),
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "REF" in result.output
        assert "@ 50.0, 14.0, 200.0m" in result.output

    def test_map_share_url_displayed(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        detail = self._detail_with_message(
            mapShareUrl="https://share.garmin.com/abc123",
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "MapShare: https://share.garmin.com/abc123" in result.output

    def test_live_track_url_displayed(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        detail = self._detail_with_message(
            liveTrackUrl="https://livetrack.garmin.com/xyz",
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "LiveTrack: https://livetrack.garmin.com/xyz" in result.output

    def test_location_without_elevation_no_meters(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        detail = self._detail_with_message(
            userLocation=UserLocation(latitudeDegrees=10.0, longitudeDegrees=20.0),
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "@ 10.0, 20.0]" in result.output
        assert "m]" not in result.output


class TestMessagesEmpty:
    """No messages found."""

    def test_empty_message(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_detail
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_empty_detail
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert "No messages found" in result.output
        assert result.exit_code == 0


class TestMessagesOptions:
    """--limit, --help, defaults."""

    def test_default_limit(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_detail
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_empty_detail
        cli_runner.invoke(cli, ["messages", CONV_ID])
        api.get_conversation_detail.assert_called_once_with(CONV_ID, limit=20)

    def test_custom_limit(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_detail
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_empty_detail
        cli_runner.invoke(cli, ["messages", CONV_ID, "--limit", "5"])
        api.get_conversation_detail.assert_called_once_with(CONV_ID, limit=5)

    def test_passes_conv_id(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_detail
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_empty_detail
        cli_runner.invoke(cli, ["messages", "some-conv-id"])
        api.get_conversation_detail.assert_called_once_with("some-conv-id", limit=20)

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["messages", "--help"])
        assert result.exit_code == 0
        assert "Show messages from a conversation" in result.output

    def test_help_shows_uuid_flag(self, cli_runner):
        result = cli_runner.invoke(cli, ["messages", "--help"])
        assert "--uuid" in result.output


class TestMessagesArgument:
    """Missing conversation_id."""

    def test_missing_conversation_id(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(cli, ["messages"])
        assert result.exit_code == 2
        assert "CONVERSATION_ID" in result.stderr or "Missing argument" in result.stderr


class TestMessagesAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["messages", CONV_ID])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr
