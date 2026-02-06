"""Local contact management — maps member/conversation IDs to friendly names.

Stores a contacts.yaml file in the session directory (~/.garmin-messenger/)
that users can edit manually after populating with ``sync-contacts``.

Also manages state.yaml (auto-generated data like UUID → phone, not user-editable).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import yaml

log = logging.getLogger(__name__)

CONTACTS_FILE = "contacts.yaml"
STATE_FILE = "state.yaml"


@dataclass
class Contacts:
    """In-memory representation of the local contacts file."""

    members: dict[str, str] = field(default_factory=dict)
    conversations: dict[str, str] = field(default_factory=dict)

    def resolve_member(self, member_id: str | None) -> str | None:
        """Return the friendly name for *member_id*, or ``None`` if unknown/empty."""
        if member_id is None:
            return None
        name = self.members.get(member_id, "")
        return name if name else None

    def resolve_conversation(self, conv_id: str | None) -> str | None:
        """Return the friendly name for *conv_id*, or ``None`` if unknown/empty."""
        if conv_id is None:
            return None
        name = self.conversations.get(conv_id, "")
        return name if name else None


def load_contacts(session_dir: str) -> Contacts:
    """Read contacts.yaml from *session_dir*. Returns empty Contacts on any error."""
    path = os.path.join(session_dir, CONTACTS_FILE)
    if not os.path.isfile(path):
        return Contacts()
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return Contacts()
        members = data.get("members") or {}
        conversations = data.get("conversations") or {}
        if not isinstance(members, dict) or not isinstance(conversations, dict):
            return Contacts()
        # Ensure all keys and values are strings
        members = {str(k): str(v) if v is not None else "" for k, v in members.items()}
        conversations = {str(k): str(v) if v is not None else "" for k, v in conversations.items()}
        return Contacts(members=members, conversations=conversations)
    except Exception:
        log.debug("Failed to load contacts from %s", path, exc_info=True)
        return Contacts()


def save_contacts(session_dir: str, contacts: Contacts) -> None:
    """Write contacts.yaml to *session_dir*, creating the directory if needed."""
    os.makedirs(session_dir, exist_ok=True)
    path = os.path.join(session_dir, CONTACTS_FILE)
    data = {
        "members": contacts.members,
        "conversations": contacts.conversations,
    }
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def merge_members(
    existing: dict[str, str],
    api_members: list[tuple[str, str]],
) -> dict[str, str]:
    """Merge server member data into the existing members dict.

    *api_members* is a list of ``(key, suggested_name)`` pairs.
    - New keys are added with the suggested name.
    - Existing keys with an empty name are updated with the suggested name.
    - Existing keys with a non-empty name are preserved.
    """
    result = dict(existing)
    for key, suggested in api_members:
        if key not in result or not result[key]:
            result[key] = suggested
    return result


def merge_conversations(
    existing: dict[str, str],
    conv_ids: list[str],
) -> dict[str, str]:
    """Merge conversation IDs into the existing conversations dict.

    New IDs are added with an empty string. Existing entries are preserved.
    """
    result = dict(existing)
    for cid in conv_ids:
        if cid not in result:
            result[cid] = ""
    return result


# -------------------------------------------------------------------------
# Addresses — auto-generated UUID → phone mapping (not user-editable)
# -------------------------------------------------------------------------


def load_addresses(session_dir: str) -> dict[str, str]:
    """Read the addresses section from state.yaml. Returns empty dict on any error."""
    path = os.path.join(session_dir, STATE_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return {}
        addresses = data.get("addresses") or {}
        if not isinstance(addresses, dict):
            return {}
        return {str(k): str(v) if v is not None else "" for k, v in addresses.items()}
    except Exception:
        log.debug("Failed to load addresses from %s", path, exc_info=True)
        return {}


def save_addresses(session_dir: str, addresses: dict[str, str]) -> None:
    """Write addresses into state.yaml, creating the file if needed."""
    os.makedirs(session_dir, exist_ok=True)
    path = os.path.join(session_dir, STATE_FILE)
    data = {"addresses": addresses}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# DO NOT EDIT — auto-generated by garmin-messenger\n")
        yaml.dump(data, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def merge_addresses(
    existing: dict[str, str],
    api_addresses: list[tuple[str, str]],
) -> dict[str, str]:
    """Merge server address data into the existing addresses dict.

    *api_addresses* is a list of ``(uuid, phone)`` pairs.
    Always overwrites with the latest server value (phone numbers don't change).
    """
    result = dict(existing)
    for uuid, phone in api_addresses:
        if phone:
            result[uuid] = phone
    return result
