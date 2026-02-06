"""Tests for --yaml global flag across all commands."""

from __future__ import annotations

import yaml
import pytest

from garmin_messenger_cli.main import cli

from garmin_messenger.models import phone_to_hermes_user_id

from .conftest import (
    CONV_ID,
    MODULE,
    MSG_ID,
    LAST_MSG_ID,
    INSTANCE_ID,
    RECIPIENT_ID,
    USER_ID,
    USER_IDENTIFIER_1,
    USER_IDENTIFIER_2,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_yaml(output: str):
    """Parse YAML output, returning the deserialized data."""
    return yaml.safe_load(output)


# ---------------------------------------------------------------------------
# conversations --yaml
# ---------------------------------------------------------------------------


class TestConversationsYaml:
    def test_is_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_conversation_id_present(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        data = _parse_yaml(result.output)
        assert data[0]["conversation_id"] == CONV_ID

    def test_members_is_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        data = _parse_yaml(result.output)
        assert isinstance(data[0]["members"], list)
        assert USER_ID in data[0]["members"]
        assert RECIPIENT_ID in data[0]["members"]

    def test_muted_is_bool(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        data = _parse_yaml(result.output)
        assert data[0]["muted"] is False

    def test_updated_is_iso_string(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        data = _parse_yaml(result.output)
        assert "2025-01-15" in data[0]["updated"]

    def test_empty_returns_empty_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_conversations
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_empty_conversations
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data == []

    def test_no_table_header(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversations_result
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = sample_conversations_result
        result = cli_runner.invoke(cli, ["--yaml", "conversations"])
        assert "CONVERSATION ID" not in result.output
        assert "---" not in result.output or "conversation_id" in result.output


# ---------------------------------------------------------------------------
# messages --yaml
# ---------------------------------------------------------------------------


class TestMessagesYaml:
    def test_is_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversation_detail_result
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["--yaml", "messages", CONV_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_message_fields(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversation_detail_result
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["--yaml", "messages", CONV_ID])
        data = _parse_yaml(result.output)
        msg = data[0]
        assert msg["body"] == "Hello!"
        assert msg["sender"] == USER_ID  # phone fallback when no contact name
        assert msg["sender_phone"] == USER_ID
        assert "sender_id" not in msg  # hidden by default
        assert "message_id" not in msg  # hidden by default
        assert "2025-01-15" in msg["sent_at"]

    def test_message_fields_with_uuid(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversation_detail_result
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["--yaml", "messages", "--uuid", CONV_ID])
        data = _parse_yaml(result.output)
        msg = data[0]
        assert msg["sender_id"] == phone_to_hermes_user_id(USER_ID)
        assert msg["message_id"] == MSG_ID
        assert msg["sender_phone"] == USER_ID

    def test_location_included(
        self, cli_runner, mock_auth_class, mock_api_class, sample_conversation_detail_with_location
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_with_location
        result = cli_runner.invoke(cli, ["--yaml", "messages", CONV_ID])
        data = _parse_yaml(result.output)
        loc = data[0]["location"]
        assert loc["latitude"] == 45.5231
        assert loc["longitude"] == -122.6765
        assert loc["elevation"] == 15.0

    def test_empty_returns_empty_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_detail
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_empty_detail
        result = cli_runner.invoke(cli, ["--yaml", "messages", CONV_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data == []


# ---------------------------------------------------------------------------
# send --yaml
# ---------------------------------------------------------------------------


class TestSendYaml:
    def test_returns_dict(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["--yaml", "send", "--to", RECIPIENT_ID, "--message", "Hi"]
        )
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, dict)

    def test_message_id_present(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["--yaml", "send", "--to", RECIPIENT_ID, "--message", "Hi"]
        )
        data = _parse_yaml(result.output)
        assert data["message_id"] == MSG_ID

    def test_conversation_id_present(
        self, cli_runner, mock_auth_class, mock_api_class, sample_send_result
    ):
        _, api = mock_api_class
        api.send_message.return_value = sample_send_result
        result = cli_runner.invoke(
            cli, ["--yaml", "send", "--to", RECIPIENT_ID, "--message", "Hi"]
        )
        data = _parse_yaml(result.output)
        assert data["conversation_id"] == CONV_ID


# ---------------------------------------------------------------------------
# members --yaml
# ---------------------------------------------------------------------------


class TestMembersYaml:
    def test_is_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["--yaml", "members", CONV_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, list)
        assert len(data) == 2

    def test_member_fields(
        self, cli_runner, mock_auth_class, mock_api_class, sample_members_result
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result
        result = cli_runner.invoke(cli, ["--yaml", "members", CONV_ID])
        data = _parse_yaml(result.output)
        assert data[0]["user_id"] == USER_IDENTIFIER_1
        assert data[0]["name"] == "Alice"
        assert data[0]["address"] == USER_ID

    def test_empty_returns_empty_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_empty_members
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_empty_members
        result = cli_runner.invoke(cli, ["--yaml", "members", CONV_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data == []


# ---------------------------------------------------------------------------
# mute --yaml
# ---------------------------------------------------------------------------


class TestMuteYaml:
    def test_mute_returns_dict(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        _, api = mock_api_class
        result = cli_runner.invoke(cli, ["--yaml", "mute", CONV_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data["conversation_id"] == CONV_ID
        assert data["muted"] is True

    def test_unmute_returns_dict(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        _, api = mock_api_class
        result = cli_runner.invoke(cli, ["--yaml", "mute", "--off", CONV_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data["muted"] is False


# ---------------------------------------------------------------------------
# muted --yaml
# ---------------------------------------------------------------------------


class TestMutedYaml:
    def test_is_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["--yaml", "muted"])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_conversation_id(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["--yaml", "muted"])
        data = _parse_yaml(result.output)
        assert data[0]["conversation_id"] == CONV_ID

    def test_expires_iso(
        self, cli_runner, mock_auth_class, mock_api_class, sample_muted_result
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = sample_muted_result
        result = cli_runner.invoke(cli, ["--yaml", "muted"])
        data = _parse_yaml(result.output)
        assert "2025-02-01" in data[0]["expires"]

    def test_empty_returns_empty_list(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        _, api = mock_api_class
        api.get_muted_conversations.return_value = []
        result = cli_runner.invoke(cli, ["--yaml", "muted"])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data == []


# ---------------------------------------------------------------------------
# network --yaml
# ---------------------------------------------------------------------------


class TestNetworkYaml:
    def test_returns_dict(
        self, cli_runner, mock_auth_class, mock_api_class, sample_network_result
    ):
        _, api = mock_api_class
        api.get_network_properties.return_value = sample_network_result
        result = cli_runner.invoke(cli, ["--yaml", "network"])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, dict)

    def test_fields(
        self, cli_runner, mock_auth_class, mock_api_class, sample_network_result
    ):
        _, api = mock_api_class
        api.get_network_properties.return_value = sample_network_result
        result = cli_runner.invoke(cli, ["--yaml", "network"])
        data = _parse_yaml(result.output)
        assert data["data_constrained"] is False
        assert data["premium_messaging"] is True


# ---------------------------------------------------------------------------
# device-metadata --yaml
# ---------------------------------------------------------------------------


class TestDeviceMetadataYaml:
    def test_is_list(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["--yaml", "device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_device_fields(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_result
        result = cli_runner.invoke(cli, ["--yaml", "device-metadata", CONV_ID, MSG_ID])
        data = _parse_yaml(result.output)
        dev = data[0]["devices"][0]
        assert dev["imei"] == 300234063904190
        assert "inreach_metadata" in dev
        assert dev["inreach_metadata"][0]["text"] == "inReach Mini 2"
        assert dev["inreach_metadata"][0]["mtmsn"] == 42

    def test_empty_returns_empty_list(
        self, cli_runner, mock_auth_class, mock_api_class
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = []
        result = cli_runner.invoke(cli, ["--yaml", "device-metadata", CONV_ID, MSG_ID])
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert data == []

    def test_no_devices(
        self, cli_runner, mock_auth_class, mock_api_class, sample_device_metadata_no_device_result
    ):
        _, api = mock_api_class
        api.get_message_device_metadata.return_value = sample_device_metadata_no_device_result
        result = cli_runner.invoke(cli, ["--yaml", "device-metadata", CONV_ID, MSG_ID])
        data = _parse_yaml(result.output)
        assert data[0]["devices"] == []


# ---------------------------------------------------------------------------
# login --yaml
# ---------------------------------------------------------------------------


class TestLoginYaml:
    def test_returns_dict(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(
            cli, ["--yaml", "login", "--phone", "+15551234567"]
        )
        assert result.exit_code == 0
        data = _parse_yaml(result.output)
        assert isinstance(data, dict)
        assert data["instance_id"] == INSTANCE_ID

    def test_session_dir_present(self, cli_runner, mock_auth_class):
        result = cli_runner.invoke(
            cli, ["--yaml", "login", "--phone", "+15551234567"]
        )
        data = _parse_yaml(result.output)
        assert "session_dir" in data


# ---------------------------------------------------------------------------
# --yaml flag in --help
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _sender_fields consistency
# ---------------------------------------------------------------------------


class TestSenderFieldsConsistency:
    """sender_id is always a UUID, sender_phone present when phone is known."""

    def test_messages_sender_id_is_uuid_when_from_is_phone(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_conversation_detail_result
    ):
        """messages: from_ is a phone in the fixture → sender_id = derived UUID."""
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result
        result = cli_runner.invoke(cli, ["--yaml", "messages", "--uuid", CONV_ID])
        data = _parse_yaml(result.output)
        msg = data[0]
        assert msg["sender_id"] == phone_to_hermes_user_id(USER_ID)
        assert msg["sender_phone"] == USER_ID

    def test_messages_sender_id_is_uuid_when_from_is_uuid(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """messages: from_ is a UUID (real server behavior) → sender_id = same UUID."""
        from garmin_messenger.models import ConversationDetailModel, ConversationMetaModel, ConversationMessageModel
        from uuid import UUID as _UUID
        uuid_from = "11153808-b0a5-5f9b-bbcf-b35be7e4359e"
        detail = ConversationDetailModel(
            metaData=ConversationMetaModel(
                conversationId=_UUID(CONV_ID),
                memberIds=[uuid_from],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            ),
            messages=[
                ConversationMessageModel(
                    messageId=_UUID(MSG_ID),
                    messageBody="Hello!",
                    from_=uuid_from,
                    sentAt="2025-01-15T10:30:00Z",
                ),
            ],
            limit=50,
            lastMessageId=_UUID(MSG_ID),
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "--yaml", "messages", "--uuid", CONV_ID]
        )
        data = _parse_yaml(result.output)
        msg = data[0]
        assert msg["sender_id"] == uuid_from
        assert "sender_phone" not in msg

    def test_messages_sender_phone_from_contacts(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """messages: from_ is a UUID, but address is known from sync-contacts → sender_phone shown."""
        from garmin_messenger.models import ConversationDetailModel, ConversationMetaModel, ConversationMessageModel
        from uuid import UUID as _UUID
        uuid_from = "11153808-b0a5-5f9b-bbcf-b35be7e4359e"
        phone = "+15555550100"
        contacts_data = {
            "members": {uuid_from: "Marek"},
            "conversations": {},
        }
        (tmp_path / "contacts.yaml").write_text(yaml.dump(contacts_data))
        (tmp_path / "state.yaml").write_text(yaml.dump({"addresses": {uuid_from: phone}}))

        detail = ConversationDetailModel(
            metaData=ConversationMetaModel(
                conversationId=_UUID(CONV_ID),
                memberIds=[uuid_from],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            ),
            messages=[
                ConversationMessageModel(
                    messageId=_UUID(MSG_ID),
                    messageBody="Ahoj",
                    from_=uuid_from,
                    sentAt="2025-01-15T10:30:00Z",
                ),
            ],
            limit=50,
            lastMessageId=_UUID(MSG_ID),
        )
        _, api = mock_api_class
        api.get_conversation_detail.return_value = detail
        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "--yaml", "messages", "--uuid", CONV_ID]
        )
        parsed = _parse_yaml(result.output)
        msg = parsed[0]
        assert msg["sender"] == "Marek"
        assert msg["sender_id"] == uuid_from
        assert msg["sender_phone"] == phone


# ---------------------------------------------------------------------------
# --yaml flag in --help
# ---------------------------------------------------------------------------


class TestYamlHelp:
    def test_help_shows_yaml_flag(self, cli_runner):
        result = cli_runner.invoke(cli, ["--help"])
        assert "--yaml" in result.output
        assert "YAML" in result.output
