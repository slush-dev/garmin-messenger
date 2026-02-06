"""Tests for local contact management — contacts.py and CLI integration."""

from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import yaml
from garmin_messenger.models import (
    ConversationMetaModel,
    GetConversationsModel,
    UserInfoModel,
)

from garmin_messenger_cli.contacts import (
    Contacts,
    load_addresses,
    load_contacts,
    merge_addresses,
    merge_conversations,
    merge_members,
    save_addresses,
    save_contacts,
)
from garmin_messenger_cli.main import cli

from .conftest import (
    CONV_ID,
    MODULE,
    RECIPIENT_ID,
    USER_ID,
    USER_IDENTIFIER_1,
    USER_IDENTIFIER_2,
)

# =========================================================================
# Unit tests — Contacts dataclass
# =========================================================================


class TestResolve:
    """Contacts.resolve_member / resolve_conversation."""

    def test_resolve_member_found(self):
        c = Contacts(members={"uid-1": "Alice"})
        assert c.resolve_member("uid-1") == "Alice"

    def test_resolve_member_empty_string(self):
        c = Contacts(members={"uid-1": ""})
        assert c.resolve_member("uid-1") is None

    def test_resolve_member_missing(self):
        c = Contacts(members={})
        assert c.resolve_member("uid-1") is None

    def test_resolve_member_none_id(self):
        c = Contacts(members={"uid-1": "Alice"})
        assert c.resolve_member(None) is None

    def test_resolve_conversation_found(self):
        c = Contacts(conversations={"abc": "Family"})
        assert c.resolve_conversation("abc") == "Family"

    def test_resolve_conversation_empty_string(self):
        c = Contacts(conversations={"abc": ""})
        assert c.resolve_conversation("abc") is None

    def test_resolve_conversation_missing(self):
        c = Contacts(conversations={})
        assert c.resolve_conversation("abc") is None

    def test_resolve_conversation_none_id(self):
        c = Contacts(conversations={"abc": "X"})
        assert c.resolve_conversation(None) is None



# =========================================================================
# Unit tests — load_contacts
# =========================================================================


class TestLoadContacts:
    """load_contacts from filesystem."""

    def test_missing_file(self, tmp_path):
        c = load_contacts(str(tmp_path))
        assert c.members == {}
        assert c.conversations == {}

    def test_valid_file(self, tmp_path):
        data = {
            "members": {"uid-1": "Alice", "uid-2": ""},
            "conversations": {"conv1": "Chat", "conv2": ""},
        }
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))
        c = load_contacts(str(tmp_path))
        assert c.members["uid-1"] == "Alice"
        assert c.members["uid-2"] == ""
        assert c.conversations["conv1"] == "Chat"

    def test_malformed_yaml(self, tmp_path):
        (tmp_path / "contacts.yaml").write_text("{{{{not yaml")
        c = load_contacts(str(tmp_path))
        assert c.members == {}
        assert c.conversations == {}

    def test_empty_file(self, tmp_path):
        (tmp_path / "contacts.yaml").write_text("")
        c = load_contacts(str(tmp_path))
        assert c.members == {}
        assert c.conversations == {}

    def test_partial_members_only(self, tmp_path):
        data = {"members": {"uid-1": "Bob"}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))
        c = load_contacts(str(tmp_path))
        assert c.members["uid-1"] == "Bob"
        assert c.conversations == {}

    def test_partial_conversations_only(self, tmp_path):
        data = {"conversations": {"c1": "Fam"}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))
        c = load_contacts(str(tmp_path))
        assert c.members == {}
        assert c.conversations["c1"] == "Fam"

    def test_non_dict_root(self, tmp_path):
        (tmp_path / "contacts.yaml").write_text("- a list\n- not dict\n")
        c = load_contacts(str(tmp_path))
        assert c.members == {}

    def test_null_values_become_empty_string(self, tmp_path):
        (tmp_path / "contacts.yaml").write_text(
            "members:\n  uid-1: null\nconversations:\n  c1: null\n"
        )
        c = load_contacts(str(tmp_path))
        assert c.members["uid-1"] == ""
        assert c.conversations["c1"] == ""


# =========================================================================
# Unit tests — save_contacts
# =========================================================================


class TestSaveContacts:
    """save_contacts to filesystem."""

    def test_creates_file(self, tmp_path):
        c = Contacts(members={"uid-1": "Alice"}, conversations={"c1": "Chat"})
        save_contacts(str(tmp_path), c)
        assert (tmp_path / "contacts.yaml").exists()

    def test_creates_directory(self, tmp_path):
        subdir = tmp_path / "sub" / "dir"
        save_contacts(str(subdir), Contacts())
        assert (subdir / "contacts.yaml").exists()

    def test_roundtrip(self, tmp_path):
        original = Contacts(
            members={"uid-1": "Alice", "uid-2": "Bob"},
            conversations={"c1": "Family", "c2": ""},
        )
        save_contacts(str(tmp_path), original)
        loaded = load_contacts(str(tmp_path))
        assert loaded.members == original.members
        assert loaded.conversations == original.conversations


# =========================================================================
# Unit tests — load_addresses / save_addresses
# =========================================================================


class TestAddressesFile:
    """Separate state.yaml file for UUID → phone mapping."""

    def test_load_missing_file(self, tmp_path):
        assert load_addresses(str(tmp_path)) == {}

    def test_roundtrip(self, tmp_path):
        original = {"uid-1": "+15551234567", "uid-2": "+15559876543"}
        save_addresses(str(tmp_path), original)
        loaded = load_addresses(str(tmp_path))
        assert loaded == original

    def test_malformed_yaml(self, tmp_path):
        (tmp_path / "state.yaml").write_text("{{{{not yaml")
        assert load_addresses(str(tmp_path)) == {}

    def test_non_dict_root(self, tmp_path):
        (tmp_path / "state.yaml").write_text("- a list\n")
        assert load_addresses(str(tmp_path)) == {}

    def test_non_dict_addresses(self, tmp_path):
        (tmp_path / "state.yaml").write_text("addresses:\n- a list\n")
        assert load_addresses(str(tmp_path)) == {}

    def test_null_values_become_empty(self, tmp_path):
        (tmp_path / "state.yaml").write_text("addresses:\n  uid-1: null\n")
        loaded = load_addresses(str(tmp_path))
        assert loaded["uid-1"] == ""

    def test_file_has_do_not_edit_comment(self, tmp_path):
        save_addresses(str(tmp_path), {"uid-1": "+15551234567"})
        content = (tmp_path / "state.yaml").read_text()
        assert "DO NOT EDIT" in content


# =========================================================================
# Unit tests — merge_members
# =========================================================================


class TestMergeMembers:
    """merge_members preserves non-empty, overwrites empty, adds new."""

    def test_new_added(self):
        result = merge_members({}, [("uid-1", "Alice")])
        assert result["uid-1"] == "Alice"

    def test_non_empty_preserved(self):
        result = merge_members({"uid-1": "Custom"}, [("uid-1", "ServerAlice")])
        assert result["uid-1"] == "Custom"

    def test_empty_overwritten(self):
        result = merge_members({"uid-1": ""}, [("uid-1", "ServerAlice")])
        assert result["uid-1"] == "ServerAlice"

    def test_mixed(self):
        existing = {"uid-1": "Custom", "uid-2": ""}
        api = [("uid-1", "Server1"), ("uid-2", "Server2"), ("uid-3", "Server3")]
        result = merge_members(existing, api)
        assert result["uid-1"] == "Custom"
        assert result["uid-2"] == "Server2"
        assert result["uid-3"] == "Server3"

    def test_does_not_modify_original(self):
        existing = {"uid-1": "Alice"}
        merge_members(existing, [("uid-2", "Bob")])
        assert "uid-2" not in existing


# =========================================================================
# Unit tests — merge_conversations
# =========================================================================


class TestMergeConversations:
    """merge_conversations adds new with empty string, preserves existing."""

    def test_new_added(self):
        result = merge_conversations({}, ["c1", "c2"])
        assert result["c1"] == ""
        assert result["c2"] == ""

    def test_existing_preserved(self):
        result = merge_conversations({"c1": "Family"}, ["c1"])
        assert result["c1"] == "Family"

    def test_existing_empty_preserved(self):
        result = merge_conversations({"c1": ""}, ["c1"])
        assert result["c1"] == ""

    def test_does_not_modify_original(self):
        existing = {"c1": "Family"}
        merge_conversations(existing, ["c2"])
        assert "c2" not in existing


# =========================================================================
# Unit tests — merge_addresses
# =========================================================================


class TestMergeAddresses:
    """merge_addresses overwrites with latest server value."""

    def test_new_added(self):
        result = merge_addresses({}, [("uid-1", "+15551234567")])
        assert result["uid-1"] == "+15551234567"

    def test_existing_overwritten(self):
        result = merge_addresses({"uid-1": "+15550000000"}, [("uid-1", "+15551234567")])
        assert result["uid-1"] == "+15551234567"

    def test_empty_phone_skipped(self):
        result = merge_addresses({}, [("uid-1", "")])
        assert "uid-1" not in result

    def test_does_not_modify_original(self):
        existing = {"uid-1": "+15550000000"}
        merge_addresses(existing, [("uid-2", "+15551234567")])
        assert "uid-2" not in existing


# =========================================================================
# Command tests — sync-contacts
# =========================================================================


CONV_ID_2 = "b2c3d4e5-f6a7-8901-bcde-f12345678901"


def _make_conversations_result(conv_ids=None, member_ids=None):
    """Build a GetConversationsModel from a list of conv IDs."""
    if conv_ids is None:
        conv_ids = [CONV_ID]
    if member_ids is None:
        member_ids = [USER_ID, RECIPIENT_ID]
    return GetConversationsModel(
        conversations=[
            ConversationMetaModel(
                conversationId=UUID(cid),
                memberIds=member_ids,
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
            )
            for cid in conv_ids
        ],
        lastConversationId=UUID(conv_ids[-1]),
    )


class TestSyncContactsCommand:
    """sync-contacts command keys contacts by userIdentifier (the UUID
    that matches memberIds/from_ on the real server)."""

    def test_happy_path(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(userIdentifier=USER_IDENTIFIER_1, address=USER_ID, friendlyName="Alice"),
        ]

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "sync-contacts"]
        )
        assert result.exit_code == 0
        assert "Synced" in result.output
        assert (tmp_path / "contacts.yaml").exists()
        loaded = load_contacts(str(tmp_path))
        # Keyed by userIdentifier, value is friendlyName
        assert loaded.members[USER_IDENTIFIER_1] == "Alice"
        # Address (phone) stored in separate file
        addrs = load_addresses(str(tmp_path))
        assert addrs[USER_IDENTIFIER_1] == USER_ID

    def test_merge_preserves_existing_names(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        pre = {"members": {USER_IDENTIFIER_1: "CustomAlice"}, "conversations": {}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(pre))

        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(
                userIdentifier=USER_IDENTIFIER_1, address=USER_ID,
                friendlyName="ServerAlice",
            ),
        ]

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        loaded = load_contacts(str(tmp_path))
        assert loaded.members[USER_IDENTIFIER_1] == "CustomAlice"

    def test_api_calls(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result([CONV_ID, CONV_ID_2])
        api.get_conversation_members.return_value = []

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        api.get_conversations.assert_called_once_with(limit=100)
        assert api.get_conversation_members.call_count == 2

    def test_custom_limit(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = []

        cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "sync-contacts", "--limit", "5"]
        )
        api.get_conversations.assert_called_once_with(limit=5)

    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["sync-contacts", "--help"])
        assert result.exit_code == 0
        assert "Sync contacts" in result.output

    def test_multiple_members(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(
                userIdentifier=USER_IDENTIFIER_1, address=USER_ID,
                friendlyName="Alice",
            ),
            UserInfoModel(
                userIdentifier=USER_IDENTIFIER_2, address=RECIPIENT_ID,
                friendlyName="Bob",
            ),
        ]

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        loaded = load_contacts(str(tmp_path))
        assert loaded.members[USER_IDENTIFIER_1] == "Alice"
        assert loaded.members[USER_IDENTIFIER_2] == "Bob"

    def test_question_mark_friendly_name_falls_back_to_address(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        """Server returns '?' for friendlyName when contacts not uploaded."""
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(userIdentifier=USER_IDENTIFIER_1, address=USER_ID, friendlyName="?"),
        ]

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        loaded = load_contacts(str(tmp_path))
        assert loaded.members[USER_IDENTIFIER_1] == USER_ID

    def test_no_friendly_name_falls_back_to_address(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(userIdentifier=USER_IDENTIFIER_1, address=USER_ID, friendlyName=None),
        ]

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        loaded = load_contacts(str(tmp_path))
        assert loaded.members[USER_IDENTIFIER_1] == USER_ID

    def test_no_user_identifier_skipped(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(userIdentifier=None, address=USER_ID, friendlyName="Ghost"),
        ]

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        loaded = load_contacts(str(tmp_path))
        assert len(loaded.members) == 0

    def test_no_address_no_friendly_name_stores_empty(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()
        api.get_conversation_members.return_value = [
            UserInfoModel(userIdentifier=USER_IDENTIFIER_1, address=None, friendlyName=None),
        ]

        cli_runner.invoke(cli, ["--session-dir", str(tmp_path), "sync-contacts"])

        loaded = load_contacts(str(tmp_path))
        assert loaded.members[USER_IDENTIFIER_1] == ""


# =========================================================================
# Enrichment tests — display commands resolve names
# =========================================================================


class TestConversationsEnrichment:
    """conversations command resolves member IDs to names.

    memberIds in the test fixtures use USER_ID/RECIPIENT_ID (phone numbers).
    On the real server these would be UUIDs matching userIdentifier.
    The contacts file keys must match the memberIds values for resolution.
    """

    def test_shows_contact_names(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        # Keys match memberIds values from _make_conversations_result
        data = {"members": {USER_ID: "Alice", RECIPIENT_ID: "Bob"}, "conversations": {}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))

        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "conversations"]
        )
        assert "Alice" in result.output
        assert "Bob" in result.output

    def test_falls_back_to_id(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "conversations"]
        )
        assert USER_ID in result.output
        assert RECIPIENT_ID in result.output

    def test_shows_conversation_name(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        data = {"members": {}, "conversations": {CONV_ID: "Family chat"}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))

        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "conversations"]
        )
        assert "Family chat" in result.output
        # UUID is always shown
        assert CONV_ID in result.output

    def test_name_column_header(
        self, cli_runner, mock_auth_class, mock_api_class, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversations.return_value = _make_conversations_result()

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "conversations"]
        )
        assert "NAME" in result.output


class TestMessagesEnrichment:
    """messages command resolves sender to contact name.

    from_ in the test fixtures uses USER_ID (phone number).
    On the real server this would be a UUID matching userIdentifier.
    """

    def test_shows_contact_name(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_conversation_detail_result, tmp_path
    ):
        # Key matches from_ value
        data = {"members": {USER_ID: "Alice"}, "conversations": {}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))

        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "messages", CONV_ID]
        )
        assert "Alice" in result.output

    def test_falls_back_to_from(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_conversation_detail_result, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "messages", CONV_ID]
        )
        assert USER_ID in result.output

    def test_header_shows_conversation_name(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_conversation_detail_result, tmp_path
    ):
        data = {"members": {}, "conversations": {CONV_ID: "Family chat"}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))

        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "messages", CONV_ID]
        )
        assert "Family chat" in result.output
        assert CONV_ID not in result.output

    def test_header_falls_back_to_conv_id(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_conversation_detail_result, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversation_detail.return_value = sample_conversation_detail_result

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "messages", CONV_ID]
        )
        assert f"Messages in {CONV_ID}" in result.output


class TestMembersEnrichment:
    """members command resolves LOCAL NAME via userIdentifier."""

    def test_local_name_column(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_members_result, tmp_path
    ):
        # Key by userIdentifier (USER_IDENTIFIER_1), not address
        data = {"members": {USER_IDENTIFIER_1: "MyAlice"}, "conversations": {}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))

        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "members", CONV_ID]
        )
        assert "LOCAL NAME" in result.output
        assert "MyAlice" in result.output

    def test_local_name_empty_when_no_contact(
        self, cli_runner, mock_auth_class, mock_api_class,
        sample_members_result, tmp_path
    ):
        _, api = mock_api_class
        api.get_conversation_members.return_value = sample_members_result

        result = cli_runner.invoke(
            cli, ["--session-dir", str(tmp_path), "members", CONV_ID]
        )
        assert "LOCAL NAME" in result.output


class TestListenEnrichment:
    """listen command resolves sender to contact name.

    from_ in MessageModel uses the same ID format as memberIds/userIdentifier.
    """

    def _get_on_msg(self, cli_runner, mock_auth_class, mock_signalr_class, tmp_path):
        _, sr = mock_signalr_class
        with patch(f"{MODULE}.time.sleep", side_effect=SystemExit(0)), \
             patch(f"{MODULE}.signal.signal"):
            cli_runner.invoke(
                cli, ["--session-dir", str(tmp_path), "listen"]
            )
        return sr.on_message.call_args[0][0]

    def test_resolves_contact_name(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys, tmp_path
    ):
        data = {"members": {USER_ID: "Alice"}, "conversations": {}}
        (tmp_path / "contacts.yaml").write_text(yaml.dump(data))

        on_msg = self._get_on_msg(
            cli_runner, mock_auth_class, mock_signalr_class, tmp_path
        )

        from garmin_messenger.models import MessageModel
        msg = MessageModel(
            messageId=UUID("11111111-2222-3333-4444-555555555555"),
            conversationId=UUID(CONV_ID),
            messageBody="Hello",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert "Alice" in captured.out

    def test_falls_back_to_from(
        self, cli_runner, mock_auth_class, mock_signalr_class, capsys, tmp_path
    ):
        on_msg = self._get_on_msg(
            cli_runner, mock_auth_class, mock_signalr_class, tmp_path
        )

        from garmin_messenger.models import MessageModel
        msg = MessageModel(
            messageId=UUID("11111111-2222-3333-4444-555555555555"),
            conversationId=UUID(CONV_ID),
            messageBody="Hello",
            from_=USER_ID,
        )
        on_msg(msg)
        captured = capsys.readouterr()
        assert USER_ID in captured.out
