"""Tests for the media download command."""

from __future__ import annotations

from uuid import UUID

import yaml
from garmin_messenger.models import (
    ConversationDetailModel,
    ConversationMessageModel,
    ConversationMetaModel,
    MediaType,
)

from garmin_messenger_cli.main import cli

from .conftest import CONV_ID, LAST_MSG_ID, MSG_ID, USER_ID

MEDIA_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _parse_yaml(output: str):
    return yaml.safe_load(output)


def _detail_with_media():
    """ConversationDetailModel with a media message."""
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
                messageBody="Check this photo",
                from_=USER_ID,
                sentAt="2025-01-15T10:30:00Z",
                mediaId=UUID(MEDIA_ID),
                mediaType=MediaType.IMAGE_AVIF,
                uuid=UUID(MSG_ID),
            ),
        ],
        limit=50,
        lastMessageId=UUID(MSG_ID),
    )


def _detail_without_media():
    """ConversationDetailModel with a message that has no media."""
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
                messageBody="Just text",
                from_=USER_ID,
                sentAt="2025-01-15T10:30:00Z",
            ),
        ],
        limit=50,
        lastMessageId=UUID(MSG_ID),
    )


class TestMediaCommand:
    """media CONVERSATION_ID MESSAGE_ID downloads a media attachment."""

    def test_requires_two_args(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(cli, ["media"])
        assert result.exit_code == 2

    def test_invalid_conversation_id(self, cli_runner, mock_auth_class, mock_api_class):
        result = cli_runner.invoke(cli, ["media", "not-a-uuid", MSG_ID])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "invalid" in (result.stderr or "").lower()

    def test_invalid_message_id(self, cli_runner, mock_auth_class, mock_api_class):
        result = cli_runner.invoke(cli, ["media", CONV_ID, "not-a-uuid"])
        assert result.exit_code != 0

    def test_downloads_with_shortcut_flags(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """--media-id and --media-type skip fetching conversation detail."""
        _, api = mock_api_class
        api.download_media.return_value = b"\x00\x00\x00\x1cftyp"

        out_file = str(tmp_path / "photo.avif")
        result = cli_runner.invoke(cli, [
            "media", CONV_ID, MSG_ID,
            "--media-id", MEDIA_ID,
            "--media-type", "ImageAvif",
            "--output", out_file,
        ])
        assert result.exit_code == 0
        api.get_conversation_detail.assert_not_called()
        api.download_media.assert_called_once()
        assert (tmp_path / "photo.avif").read_bytes() == b"\x00\x00\x00\x1cftyp"

    def test_downloads_by_fetching_detail(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """Without --media-id, fetches conversation detail to find the message."""
        _, api = mock_api_class
        api.get_conversation_detail.return_value = _detail_with_media()
        api.download_media.return_value = b"AUDIO_DATA"

        out_file = str(tmp_path / "out.avif")
        result = cli_runner.invoke(cli, [
            "media", CONV_ID, MSG_ID, "--output", out_file,
        ])
        assert result.exit_code == 0
        api.get_conversation_detail.assert_called_once()
        api.download_media.assert_called_once()
        assert (tmp_path / "out.avif").read_bytes() == b"AUDIO_DATA"

    def test_message_not_found(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        """Error when message ID not in conversation."""
        _, api = mock_api_class
        api.get_conversation_detail.return_value = _detail_with_media()
        result = cli_runner.invoke(cli, [
            "media", CONV_ID, LAST_MSG_ID,
        ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()

    def test_message_has_no_media(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        """Error when message has no media attachment."""
        _, api = mock_api_class
        api.get_conversation_detail.return_value = _detail_without_media()
        result = cli_runner.invoke(cli, [
            "media", CONV_ID, MSG_ID,
        ])
        assert result.exit_code != 0
        assert "no media" in result.output.lower() or "no media" in (result.stderr or "").lower()

    def test_default_output_filename(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path, monkeypatch
    ):
        """Without --output, writes to {media_id}.{ext} in cwd."""
        _, api = mock_api_class
        api.download_media.return_value = b"IMG"
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(cli, [
            "media", CONV_ID, MSG_ID,
            "--media-id", MEDIA_ID,
            "--media-type", "ImageAvif",
        ])
        assert result.exit_code == 0
        assert (tmp_path / f"{MEDIA_ID}.avif").exists()

    def test_default_output_ogg(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path, monkeypatch
    ):
        """AudioOgg → .ogg extension."""
        _, api = mock_api_class
        api.download_media.return_value = b"OGG"
        monkeypatch.chdir(tmp_path)

        result = cli_runner.invoke(cli, [
            "media", CONV_ID, MSG_ID,
            "--media-id", MEDIA_ID,
            "--media-type", "AudioOgg",
        ])
        assert result.exit_code == 0
        assert (tmp_path / f"{MEDIA_ID}.ogg").exists()

    def test_text_output_shows_bytes(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """Text mode shows byte count and filename."""
        _, api = mock_api_class
        api.download_media.return_value = b"X" * 42

        out_file = str(tmp_path / "photo.avif")
        result = cli_runner.invoke(cli, [
            "media", CONV_ID, MSG_ID,
            "--media-id", MEDIA_ID,
            "--media-type", "ImageAvif",
            "--output", out_file,
        ])
        assert "42" in result.output
        assert "photo.avif" in result.output

    def test_yaml_output(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """--yaml shows structured output."""
        _, api = mock_api_class
        api.download_media.return_value = b"Y" * 100

        out_file = str(tmp_path / "photo.avif")
        result = cli_runner.invoke(cli, [
            "--yaml", "media", CONV_ID, MSG_ID,
            "--media-id", MEDIA_ID,
            "--media-type", "ImageAvif",
            "--output", out_file,
        ])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data["bytes"] == 100
        assert data["media_type"] == "ImageAvif"
        assert "photo.avif" in data["file"]

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["media", "--help"])
        assert result.exit_code == 0
        assert "CONVERSATION_ID" in result.output
        assert "MESSAGE_ID" in result.output


class TestMediaAuth:
    """Auth failures."""

    def test_no_session_exits(self, cli_runner, mock_auth_class):
        _, instance = mock_auth_class
        instance.resume.side_effect = RuntimeError("No saved session")
        result = cli_runner.invoke(cli, ["media", CONV_ID, MSG_ID])
        assert result.exit_code == 1
        assert "Run 'garmin-messenger login'" in result.stderr
