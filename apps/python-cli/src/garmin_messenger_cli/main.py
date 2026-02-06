"""Garmin Messenger CLI — login, list conversations, send & receive messages.

Usage:
    garmin-messenger login [--phone "+1..."]
    garmin-messenger conversations [--limit N]
    garmin-messenger messages CONVERSATION_ID [--limit N]
    garmin-messenger send --to RECIPIENT --message TEXT
    garmin-messenger listen
"""

from __future__ import annotations

import enum
import functools
import logging
import os
import signal
import sys
import time
from uuid import UUID

import click
import yaml

yaml.add_representer(UUID, lambda dumper, data: dumper.represent_str(str(data)))
yaml.add_multi_representer(enum.Enum, lambda dumper, data: dumper.represent_str(data.value))

from garmin_messenger.api import HermesAPI
from garmin_messenger.auth import HermesAuth
from garmin_messenger.models import (
    MediaType,
    MessageModel,
    MessageStatusUpdate,
    SimpleCompoundMessageId,
    UserLocation,
    phone_to_hermes_user_id,
)
from garmin_messenger.signalr import HermesSignalR

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

log = logging.getLogger("garmin_messenger_cli")

DEFAULT_SESSION_DIR = os.path.expanduser("~/.garmin-messenger")


def _resolve_member(contacts: Contacts, member_id: str | None) -> str | None:
    """Resolve *member_id* to a friendly name.

    Tries a direct lookup first.  If that fails and *member_id* looks like
    a phone number, derives the Hermes UUID-v5 and retries.
    """
    if member_id is None:
        return None
    name = contacts.resolve_member(member_id)
    if name:
        return name
    if member_id.startswith("+"):
        return contacts.resolve_member(phone_to_hermes_user_id(member_id))
    return None


def _sender_fields(
    contacts: Contacts, from_: str | None, addresses: dict[str, str] | None = None,
) -> dict:
    """Build consistent sender fields from a raw ``from_`` value.

    Returns a dict with ``sender`` (friendly name, or the raw identifier
    when no name is known), ``sender_id`` (always UUID), and
    ``sender_phone`` (when known).
    """
    if from_ is None:
        return {"sender": None, "sender_id": None}
    if from_.startswith("+"):
        # SignalR gives us a phone number — derive the UUID
        uid = phone_to_hermes_user_id(from_)
        name = contacts.resolve_member(uid) or contacts.resolve_member(from_)
        return {"sender": name or from_, "sender_id": uid, "sender_phone": from_}
    # REST gives us a UUID — look up phone from stored addresses
    name = contacts.resolve_member(from_)
    fields: dict = {"sender": name or from_, "sender_id": from_}
    if addresses:
        phone = addresses.get(from_, "")
        if phone:
            fields["sender_phone"] = phone
    return fields


def _yaml_out(data: object) -> None:
    """Print *data* as a YAML document to stdout."""
    click.echo(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False).rstrip()
    )


def _format_location(loc: UserLocation | None) -> str:
    """Format a UserLocation as '@ lat, lon[, elevM]' or empty string."""
    if not loc or loc.latitudeDegrees is None or loc.longitudeDegrees is None:
        return ""
    parts = f"{loc.latitudeDegrees}, {loc.longitudeDegrees}"
    if loc.elevationMeters is not None:
        parts += f", {loc.elevationMeters}m"
    return f"  [@ {parts}]"


def _has_media(media_id: UUID | None) -> bool:
    """Return True if *media_id* is non-nil and non-zero."""
    return media_id is not None and media_id != UUID(int=0)


def _format_media_cmd(
    conversation_id: str, message_id: UUID, media_id: UUID | None, media_type: MediaType | None,
) -> str:
    """Return a copy-pasteable download command, or '' if no media."""
    if not _has_media(media_id):
        return ""
    mt = media_type.value if media_type else ""
    return (
        f"garmin-messenger media {conversation_id} {message_id}"
        f" --media-id {media_id} --media-type {mt}"
    )


def _media_extension(media_type: MediaType | None) -> str:
    """Return the file extension (with dot) for a MediaType."""
    if media_type == MediaType.IMAGE_AVIF:
        return ".avif"
    if media_type == MediaType.AUDIO_OGG:
        return ".ogg"
    return ".bin"


def _configure_logging(verbose: bool) -> None:
    """Set up console logging. DEBUG if verbose, else WARNING."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _get_auth(session_dir: str) -> HermesAuth:
    """Resume a saved session, or exit with a helpful message."""
    auth = HermesAuth(session_dir=session_dir)
    try:
        auth.resume()
    except RuntimeError as exc:
        click.echo(f"Error: {exc}", err=True)
        click.echo("Run 'garmin-messenger login' first to authenticate.", err=True)
        sys.exit(1)
    return auth


# ---------------------------------------------------------------------------
# Shared option decorators
# ---------------------------------------------------------------------------


def _yaml_option(f):
    """Allow ``--yaml`` on individual commands as well as on the group."""
    @click.option("--yaml", "cmd_yaml", is_flag=True, default=False,
                  help="Print output in YAML format instead of tables.")
    @functools.wraps(f)
    def wrapper(*args, cmd_yaml=False, **kwargs):
        if cmd_yaml:
            click.get_current_context().obj["yaml"] = True
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option(
    "--session-dir",
    default=DEFAULT_SESSION_DIR,
    envvar="GARMIN_SESSION_DIR",
    show_default=True,
    help="Directory for saving/resuming session tokens.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.option(
    "--yaml", "use_yaml",
    is_flag=True,
    default=False,
    help="Print output in YAML format instead of tables.",
)
@click.pass_context
def cli(ctx: click.Context, session_dir: str, verbose: bool, use_yaml: bool) -> None:
    """Unofficial Garmin Messenger (Hermes) CLI client."""
    ctx.ensure_object(dict)
    ctx.obj["session_dir"] = session_dir
    ctx.obj["yaml"] = use_yaml
    _configure_logging(verbose)


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--phone",
    default=None,
    help='Phone number with country code (e.g. "+1234567890").',
)
@click.option(
    "--device-name",
    default="garmin-messenger",
    show_default=True,
    help="Device identifier shown on the account.",
)
@_yaml_option
@click.pass_context
def login(ctx: click.Context, phone: str | None, device_name: str) -> None:
    """Authenticate via SMS OTP and save the session."""
    session_dir = ctx.obj["session_dir"]
    auth = HermesAuth(session_dir=session_dir)

    if not phone:
        phone = click.prompt("Phone number (with country code, e.g. +1234567890)")

    if not ctx.obj["yaml"]:
        click.echo(f"Requesting SMS OTP for {phone} ...")
    otp_request = auth.request_otp(phone, device_name=device_name)
    otp_code = click.prompt("Enter SMS OTP code")
    auth.confirm_otp(otp_request, otp_code)

    if not auth.access_token:
        click.echo("Authentication failed — no access token.", err=True)
        sys.exit(1)

    if ctx.obj["yaml"]:
        _yaml_out({"instance_id": auth.instance_id, "session_dir": session_dir})
    else:
        click.echo(f"Authenticated! instance={auth.instance_id}")
        click.echo(f"Session saved to {session_dir}")


# ---------------------------------------------------------------------------
# conversations
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--limit", "-n", default=20, show_default=True, help="Max conversations to fetch.")
@_yaml_option
@click.pass_context
def conversations(ctx: click.Context, limit: int) -> None:
    """List recent conversations."""
    auth = _get_auth(ctx.obj["session_dir"])
    contacts = load_contacts(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        convos = api.get_conversations(limit=limit)

    if not convos.conversations:
        if ctx.obj["yaml"]:
            _yaml_out([])
        else:
            click.echo("No conversations found.")
        return

    if ctx.obj["yaml"]:
        rows = []
        for c in convos.conversations:
            cid = str(c.conversationId)
            rows.append({
                "conversation_id": cid,
                "name": contacts.resolve_conversation(cid) or "",
                "members": [_resolve_member(contacts, mid) or mid for mid in c.memberIds],
                "updated": c.updatedDate.isoformat() if c.updatedDate else None,
                "muted": c.isMuted,
            })
        _yaml_out(rows)
    else:
        click.echo(f"{'CONVERSATION ID':<38} {'NAME':<20} {'MEMBERS':<40} {'UPDATED':<26} MUTED")
        click.echo("-" * 130)
        for c in convos.conversations:
            cid = str(c.conversationId)
            conv_name = contacts.resolve_conversation(cid) or ""
            members = ", ".join(_resolve_member(contacts, mid) or mid for mid in c.memberIds)
            updated = c.updatedDate.strftime("%Y-%m-%d %H:%M:%S") if c.updatedDate else "?"
            muted = "yes" if c.isMuted else "no"
            click.echo(f"{cid:<38} {conv_name:<20} {members:<40} {updated:<26} {muted}")


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("conversation_id")
@click.option("--limit", "-n", default=20, show_default=True, help="Max messages to fetch.")
@click.option(
    "--uuid", "show_uuid", is_flag=True, default=False,
    help="Show message_id and sender_id in output.",
)
@_yaml_option
@click.pass_context
def messages(ctx: click.Context, conversation_id: str, limit: int, show_uuid: bool) -> None:
    """Show messages from a conversation."""
    auth = _get_auth(ctx.obj["session_dir"])
    contacts = load_contacts(ctx.obj["session_dir"])
    addresses = load_addresses(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        detail = api.get_conversation_detail(conversation_id, limit=limit)

    if not detail.messages:
        if ctx.obj["yaml"]:
            _yaml_out([])
        else:
            click.echo("No messages found.")
        return

    if ctx.obj["yaml"]:
        rows = []
        for m in detail.messages:
            row: dict = {}
            if show_uuid:
                row["message_id"] = m.messageId
            fields = _sender_fields(contacts, m.from_, addresses)
            row["sender"] = fields["sender"]
            if show_uuid and fields.get("sender_id") is not None:
                row["sender_id"] = fields["sender_id"]
            if "sender_phone" in fields:
                row["sender_phone"] = fields["sender_phone"]
            row["body"] = m.messageBody
            row["sent_at"] = m.sentAt.isoformat() if m.sentAt else None
            if m.userLocation and m.userLocation.latitudeDegrees is not None:
                row["location"] = {
                    "latitude": m.userLocation.latitudeDegrees,
                    "longitude": m.userLocation.longitudeDegrees,
                    "elevation": m.userLocation.elevationMeters,
                }
            if m.referencePoint and m.referencePoint.latitudeDegrees is not None:
                row["reference_point"] = {
                    "latitude": m.referencePoint.latitudeDegrees,
                    "longitude": m.referencePoint.longitudeDegrees,
                    "elevation": m.referencePoint.elevationMeters,
                }
            if m.mapShareUrl:
                row["map_share_url"] = m.mapShareUrl
            if m.liveTrackUrl:
                row["live_track_url"] = m.liveTrackUrl
            if _has_media(m.mediaId):
                if not show_uuid:
                    row["message_id"] = m.messageId
                row["conversation_id"] = conversation_id
                row["media_id"] = m.mediaId
                if m.mediaType:
                    row["media_type"] = m.mediaType
            rows.append(row)
        _yaml_out(rows)
    else:
        conv_label = contacts.resolve_conversation(conversation_id) or conversation_id
        click.echo(f"Messages in {conv_label} (showing up to {limit}):\n")
        for m in detail.messages:
            fields = _sender_fields(contacts, m.from_, addresses)
            sender = fields["sender"] or "?"
            body = (m.messageBody or "")[:120]
            sent = m.sentAt.strftime("%Y-%m-%d %H:%M:%S") if m.sentAt else "?"
            if show_uuid:
                loc_str = _format_location(m.userLocation)
                click.echo(f"  [{sent}] ({m.messageId}) {sender}: {body}{loc_str}")
            else:
                click.echo(f"  [{sent}] {sender}: {body}{_format_location(m.userLocation)}")
            if m.referencePoint and m.referencePoint.latitudeDegrees is not None:
                click.echo(f"    REF{_format_location(m.referencePoint)}")
            if m.mapShareUrl:
                click.echo(f"    MapShare: {m.mapShareUrl}")
            if m.liveTrackUrl:
                click.echo(f"    LiveTrack: {m.liveTrackUrl}")
            media_cmd = _format_media_cmd(conversation_id, m.messageId, m.mediaId, m.mediaType)
            if media_cmd:
                click.echo(f"    {media_cmd}")


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--to", "-t", "recipient", required=True,
    help="Recipient address (phone or user ID).",
)
@click.option("--message", "-m", "message_body", required=True, help="Message body to send.")
@click.option("--latitude", "--lat", type=float, default=None, help="GPS latitude in degrees.")
@click.option("--longitude", "--lon", type=float, default=None, help="GPS longitude in degrees.")
@click.option("--elevation", type=float, default=None, help="Elevation in meters.")
@click.option(
    "--file", "-f", "file_path",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    default=None,
    help="Path to a media file to attach (AVIF image or OGG audio).",
)
@_yaml_option
@click.pass_context
def send(
    ctx: click.Context,
    recipient: str,
    message_body: str,
    latitude: float | None,
    longitude: float | None,
    elevation: float | None,
    file_path: str | None,
) -> None:
    """Send a message to a recipient.

    Use --file / -f to attach a media file (AVIF image or OGG audio).
    """
    # Validate lat/lon pairing
    if (latitude is not None) != (longitude is not None):
        click.echo("Error: --latitude and --longitude must both be provided.", err=True)
        sys.exit(2)
    if elevation is not None and latitude is None:
        click.echo("Error: --elevation requires --latitude and --longitude.", err=True)
        sys.exit(2)

    user_location = None
    if latitude is not None:
        user_location = UserLocation(
            latitudeDegrees=latitude,
            longitudeDegrees=longitude,
            elevationMeters=elevation,
        )

    # Resolve media type from file extension
    media_type = None
    file_data = None
    if file_path is not None:
        ext_map = {
            ".avif": MediaType.IMAGE_AVIF,
            ".ogg": MediaType.AUDIO_OGG,
            ".oga": MediaType.AUDIO_OGG,
        }
        ext = os.path.splitext(file_path)[1].lower()
        media_type = ext_map.get(ext)
        if media_type is None:
            click.echo(
                f"Error: Unsupported file extension '{ext}'. Supported: .avif, .ogg, .oga",
                err=True,
            )
            sys.exit(2)
        with open(file_path, "rb") as fh:
            file_data = fh.read()

    auth = _get_auth(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        if file_data is not None:
            result = api.send_media_message(
                to=[recipient],
                message_body=message_body,
                file_data=file_data,
                media_type=media_type,
                user_location=user_location,
            )
        else:
            result = api.send_message(
                to=[recipient], message_body=message_body, user_location=user_location
            )

    if ctx.obj["yaml"]:
        _yaml_out({"message_id": result.messageId, "conversation_id": str(result.conversationId)})
    else:
        click.echo(
            f"Sent! messageId={result.messageId} conversationId={result.conversationId}"
        )


# ---------------------------------------------------------------------------
# media
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("conversation_id")
@click.argument("message_id")
@click.option("--output", "-o", default=None, help="Output file path (default: {media_id}.{ext}).")
@click.option("--media-id", default=None, help="Media ID (skip fetching message details).")
@click.option("--media-type", default=None, help="Media type: ImageAvif or AudioOgg (skip fetching message details).")
@_yaml_option
@click.pass_context
def media(
    ctx: click.Context,
    conversation_id: str,
    message_id: str,
    output: str | None,
    media_id: str | None,
    media_type: str | None,
) -> None:
    """Download a media attachment from a message.

    If --media-id and --media-type are provided, skips fetching message details.
    """
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        click.echo(f"Error: invalid conversation ID: {conversation_id}", err=True)
        sys.exit(1)
    try:
        msg_uuid = UUID(message_id)
    except ValueError:
        click.echo(f"Error: invalid message ID: {message_id}", err=True)
        sys.exit(1)

    auth = _get_auth(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        if media_id and media_type:
            try:
                m_id = UUID(media_id)
            except ValueError:
                click.echo(f"Error: invalid --media-id: {media_id}", err=True)
                sys.exit(1)
            m_type = MediaType(media_type)
            dl_uuid = msg_uuid
        else:
            detail = api.get_conversation_detail(conversation_id)
            found = False
            for m in detail.messages:
                if m.messageId == msg_uuid:
                    if not _has_media(m.mediaId):
                        click.echo(f"Error: message {message_id} has no media attachment", err=True)
                        sys.exit(1)
                    m_id = m.mediaId
                    m_type = m.mediaType
                    dl_uuid = m.uuid if m.uuid else m.messageId
                    found = True
                    break
            if not found:
                click.echo(
                    f"Error: message {message_id} not found in conversation {conversation_id}",
                    err=True,
                )
                sys.exit(1)

        data = api.download_media(
            uuid=dl_uuid,
            media_type=m_type,
            media_id=m_id,
            message_id=msg_uuid,
            conversation_id=conv_uuid,
        )

    if not output:
        output = str(m_id) + _media_extension(m_type)

    with open(output, "wb") as fh:
        fh.write(data)

    if ctx.obj["yaml"]:
        _yaml_out({"file": output, "bytes": len(data), "media_type": m_type.value if m_type else ""})
    else:
        click.echo(f"Downloaded {len(data)} bytes → {output}")


# ---------------------------------------------------------------------------
# members
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("conversation_id")
@_yaml_option
@click.pass_context
def members(ctx: click.Context, conversation_id: str) -> None:
    """Show members of a conversation."""
    auth = _get_auth(ctx.obj["session_dir"])
    contacts = load_contacts(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        result = api.get_conversation_members(conversation_id)

    if not result:
        if ctx.obj["yaml"]:
            _yaml_out([])
        else:
            click.echo("No members found.")
        return

    if ctx.obj["yaml"]:
        rows = []
        for m in result:
            rows.append({
                "user_id": m.userIdentifier,
                "name": m.friendlyName,
                "local_name": contacts.resolve_member(m.userIdentifier) or "",
                "address": m.address,
            })
        _yaml_out(rows)
    else:
        click.echo(f"{'USER ID':<38} {'NAME':<20} {'LOCAL NAME':<20} ADDRESS")
        click.echo("-" * 100)
        for m in result:
            uid = m.userIdentifier or "?"
            name = m.friendlyName or "?"
            local_name = contacts.resolve_member(m.userIdentifier) or ""
            addr = m.address or "?"
            click.echo(f"{uid:<38} {name:<20} {local_name:<20} {addr}")


# ---------------------------------------------------------------------------
# mute / unmute
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("conversation_id")
@click.option("--off", "unmute", is_flag=True, default=False, help="Unmute instead of mute.")
@_yaml_option
@click.pass_context
def mute(ctx: click.Context, conversation_id: str, unmute: bool) -> None:
    """Mute a conversation (suppress notifications).

    Use --off to unmute.
    """
    auth = _get_auth(ctx.obj["session_dir"])
    muted_flag = not unmute

    with HermesAPI(auth) as api:
        api.mute_conversation(conversation_id, muted=muted_flag)

    if ctx.obj["yaml"]:
        _yaml_out({"conversation_id": conversation_id, "muted": muted_flag})
    else:
        action = "Unmuted" if unmute else "Muted"
        click.echo(f"{action} conversation {conversation_id}.")


# ---------------------------------------------------------------------------
# muted
# ---------------------------------------------------------------------------

@cli.command()
@_yaml_option
@click.pass_context
def muted(ctx: click.Context) -> None:
    """List muted conversations with expiry."""
    auth = _get_auth(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        result = api.get_muted_conversations()

    if not result:
        if ctx.obj["yaml"]:
            _yaml_out([])
        else:
            click.echo("No muted conversations.")
        return

    if ctx.obj["yaml"]:
        rows = []
        for c in result:
            rows.append({
                "conversation_id": str(c.conversationId),
                "expires": c.expires.isoformat() if c.expires else None,
            })
        _yaml_out(rows)
    else:
        click.echo(f"{'CONVERSATION ID':<38} EXPIRES")
        click.echo("-" * 65)
        for c in result:
            expires = c.expires.strftime("%Y-%m-%d %H:%M:%S") if c.expires else "never"
            click.echo(f"{c.conversationId!s:<38} {expires}")


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

@cli.command()
@_yaml_option
@click.pass_context
def network(ctx: click.Context) -> None:
    """Show network properties."""
    auth = _get_auth(ctx.obj["session_dir"])

    with HermesAPI(auth) as api:
        props = api.get_network_properties()

    if ctx.obj["yaml"]:
        _yaml_out({
            "data_constrained": props.dataConstrained,
            "premium_messaging": props.enablesPremiumMessaging,
        })
    else:
        click.echo(f"Data constrained: {props.dataConstrained}")
        click.echo(f"Premium messaging: {props.enablesPremiumMessaging}")


# ---------------------------------------------------------------------------
# sync-contacts
# ---------------------------------------------------------------------------

@cli.command("sync-contacts")
@click.option("--limit", "-n", default=100, show_default=True, help="Max conversations to fetch.")
@_yaml_option
@click.pass_context
def sync_contacts(ctx: click.Context, limit: int) -> None:
    """Sync contacts from the server into local contacts.yaml.

    Fetches conversations and their members, then merges into the local
    contacts file. Existing non-empty names are preserved; run this to
    discover new contacts, then edit ~/.garmin-messenger/contacts.yaml
    to assign friendly names.
    """
    session_dir = ctx.obj["session_dir"]
    auth = _get_auth(session_dir)
    contacts = load_contacts(session_dir)

    with HermesAPI(auth) as api:
        convos = api.get_conversations(limit=limit)
        api_members: list[tuple[str, str]] = []
        api_addresses: list[tuple[str, str]] = []
        conv_ids: list[str] = []
        for c in convos.conversations:
            cid = str(c.conversationId)
            conv_ids.append(cid)
            members_list = api.get_conversation_members(cid)
            for m in members_list:
                # userIdentifier is the UUID that matches memberIds/from_
                if not m.userIdentifier:
                    continue
                # Prefer friendlyName, fall back to phone (address)
                suggested = ""
                if m.friendlyName and m.friendlyName != "?":
                    suggested = m.friendlyName
                elif m.address:
                    suggested = m.address
                api_members.append((m.userIdentifier, suggested))
                if m.address:
                    api_addresses.append((m.userIdentifier, m.address))

    contacts.members = merge_members(contacts.members, api_members)
    contacts.conversations = merge_conversations(contacts.conversations, conv_ids)
    save_contacts(session_dir, contacts)
    existing_addresses = load_addresses(session_dir)
    save_addresses(session_dir, merge_addresses(existing_addresses, api_addresses))

    if ctx.obj["yaml"]:
        _yaml_out({
            "members": len(contacts.members),
            "conversations": len(contacts.conversations),
            "contacts_file": os.path.join(session_dir, "contacts.yaml"),
        })
    else:
        n_members = len(contacts.members)
        n_convos = len(contacts.conversations)
        click.echo(f"Synced {n_members} members, {n_convos} conversations.")
        click.echo(f"Edit {os.path.join(session_dir, 'contacts.yaml')} to set friendly names.")


# ---------------------------------------------------------------------------
# device-metadata
# ---------------------------------------------------------------------------

@cli.command("device-metadata")
@click.argument("conversation_id")
@click.argument("message_ids", nargs=-1, required=True)
@_yaml_option
@click.pass_context
def device_metadata(ctx: click.Context, conversation_id: str, message_ids: tuple[str, ...]) -> None:
    """Show satellite device metadata for messages.

    Provide a CONVERSATION_ID followed by one or more MESSAGE_IDs.
    """
    auth = _get_auth(ctx.obj["session_dir"])

    ids = [
        SimpleCompoundMessageId(messageId=mid, conversationId=conversation_id)
        for mid in message_ids
    ]

    with HermesAPI(auth) as api:
        result = api.get_message_device_metadata(ids)

    if not result:
        if ctx.obj["yaml"]:
            _yaml_out([])
        else:
            click.echo("No device metadata found.")
        return

    if ctx.obj["yaml"]:
        rows = []
        for i, md in enumerate(result):
            entry = md.deviceMetadata
            msg_label = message_ids[i]
            if entry and entry.messageId:
                msg_label = entry.messageId.messageId
            devices = (entry.deviceMessageMetadata or []) if entry else []
            dev_list = []
            for dev in devices:
                dev_dict: dict = {
                    "device_instance_id": dev.deviceInstanceId,
                    "imei": dev.imei,
                }
                sats = []
                for sat in dev.inReachMessageMetadata or []:
                    sat_dict: dict = {"text": sat.text}
                    if sat.mtmsn is not None:
                        sat_dict["mtmsn"] = sat.mtmsn
                    if sat.otaUuid is not None:
                        sat_dict["ota_uuid"] = sat.otaUuid
                    sats.append(sat_dict)
                if sats:
                    dev_dict["inreach_metadata"] = sats
                dev_list.append(dev_dict)
            rows.append({"message_id": msg_label, "devices": dev_list})
        _yaml_out(rows)
    else:
        for i, md in enumerate(result):
            entry = md.deviceMetadata
            msg_label = message_ids[i]
            if entry and entry.messageId:
                msg_label = entry.messageId.messageId
            devices = (entry.deviceMessageMetadata or []) if entry else []
            if not devices:
                click.echo(f"Message:  {msg_label}  — no satellite device info")
                continue
            click.echo(f"Message:  {msg_label}")
            for dev in devices:
                imei_str = str(dev.imei).zfill(15) if dev.imei else "?"
                click.echo(f"  Device: {dev.deviceInstanceId or '?'}")
                click.echo(f"  IMEI:   {imei_str}")
                for sat in dev.inReachMessageMetadata or []:
                    click.echo(f"    Text:  {sat.text or '?'}")
                    if sat.mtmsn is not None:
                        click.echo(f"    MTMSN: {sat.mtmsn}")
                    if sat.otaUuid is not None:
                        click.echo(f"    OTA:   {sat.otaUuid}")


# ---------------------------------------------------------------------------
# listen
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--uuid", "show_uuid", is_flag=True, default=False,
    help="Show conversation_id, message_id, and sender_id in output.",
)
@_yaml_option
@click.pass_context
def listen(ctx: click.Context, show_uuid: bool) -> None:
    """Listen for incoming messages in real time (Ctrl+C to stop)."""
    auth = _get_auth(ctx.obj["session_dir"])
    contacts = load_contacts(ctx.obj["session_dir"])
    addresses = load_addresses(ctx.obj["session_dir"])

    use_yaml = ctx.obj["yaml"]
    sr = HermesSignalR(auth)

    def on_msg(msg: MessageModel) -> None:
        if use_yaml:
            conv_id = str(msg.conversationId)
            conv_name = contacts.resolve_conversation(conv_id) or conv_id
            row: dict = {"event": "message", "conversation": conv_name}
            if show_uuid:
                row["conversation_id"] = conv_id
                row["message_id"] = msg.messageId
            fields = _sender_fields(contacts, msg.from_, addresses)
            row["sender"] = fields["sender"]
            if show_uuid and fields.get("sender_id") is not None:
                row["sender_id"] = fields["sender_id"]
            if "sender_phone" in fields:
                row["sender_phone"] = fields["sender_phone"]
            row["body"] = msg.messageBody
            if msg.userLocation and msg.userLocation.latitudeDegrees is not None:
                row["location"] = {
                    "latitude": msg.userLocation.latitudeDegrees,
                    "longitude": msg.userLocation.longitudeDegrees,
                    "elevation": msg.userLocation.elevationMeters,
                }
            if msg.referencePoint and msg.referencePoint.latitudeDegrees is not None:
                row["reference_point"] = {
                    "latitude": msg.referencePoint.latitudeDegrees,
                    "longitude": msg.referencePoint.longitudeDegrees,
                    "elevation": msg.referencePoint.elevationMeters,
                }
            if msg.mapShareUrl:
                row["map_share_url"] = msg.mapShareUrl
            if msg.liveTrackUrl:
                row["live_track_url"] = msg.liveTrackUrl
            if _has_media(msg.mediaId):
                if not show_uuid:
                    row["conversation_id"] = conv_id
                    row["message_id"] = str(msg.messageId)
                row["media_id"] = str(msg.mediaId)
                if msg.mediaType:
                    row["media_type"] = msg.mediaType
                if msg.mediaMetadata:
                    meta: dict = {}
                    if msg.mediaMetadata.width is not None:
                        meta["width"] = msg.mediaMetadata.width
                    if msg.mediaMetadata.height is not None:
                        meta["height"] = msg.mediaMetadata.height
                    if msg.mediaMetadata.durationMs is not None:
                        meta["duration_ms"] = msg.mediaMetadata.durationMs
                    if meta:
                        row["media_metadata"] = meta
            click.echo("---")
            _yaml_out(row)
        else:
            conv_id = str(msg.conversationId)
            conv_label = contacts.resolve_conversation(conv_id) or conv_id
            fields = _sender_fields(contacts, msg.from_, addresses)
            sender = fields["sender"] or "?"
            body = (msg.messageBody or "")[:120]
            click.echo(f">> [{conv_label}] {sender}: {body}{_format_location(msg.userLocation)}")
            if msg.referencePoint and msg.referencePoint.latitudeDegrees is not None:
                click.echo(f"   REF{_format_location(msg.referencePoint)}")
            if msg.mapShareUrl:
                click.echo(f"   MapShare: {msg.mapShareUrl}")
            if msg.liveTrackUrl:
                click.echo(f"   LiveTrack: {msg.liveTrackUrl}")
            media_cmd = _format_media_cmd(conv_id, msg.messageId, msg.mediaId, msg.mediaType)
            if media_cmd:
                click.echo(f"   {media_cmd}")
        sr.mark_as_delivered(msg.messageId, msg.conversationId)

    def on_status(update: MessageStatusUpdate) -> None:
        conv_id = str(update.messageId.conversationId)
        conv_label = contacts.resolve_conversation(conv_id) or conv_id
        if use_yaml:
            row: dict = {
                "event": "status",
                "conversation": conv_label,
                "status": update.messageStatus,
            }
            if show_uuid:
                row["message_id"] = update.messageId.messageId
                row["conversation_id"] = conv_id
            click.echo("---")
            _yaml_out(row)
        else:
            if show_uuid:
                click.echo(
                    f">> STATUS conv={conv_id} "
                    f"msg={update.messageId.messageId} "
                    f"status={update.messageStatus}"
                )
            else:
                click.echo(
                    f">> STATUS [{conv_label}] "
                    f"status={update.messageStatus}"
                )

    def on_nonconv(imei: str) -> None:
        if use_yaml:
            click.echo("---")
            _yaml_out({"event": "device", "imei": imei})
        else:
            click.echo(f">> DEVICE imei={imei}")

    sr.on_message(on_msg)
    sr.on_status_update(on_status)
    sr.on_nonconversational_message(on_nonconv)
    sr.on_open(lambda: click.echo("SignalR connected."))
    sr.on_close(lambda: click.echo("SignalR disconnected."))
    sr.on_error(lambda e: click.echo(f"SignalR error: {e}", err=True))

    sr.start()
    click.echo("Listening for messages (Ctrl+C to stop) ...")

    def _shutdown(sig, frame):
        click.echo("\nShutting down ...")
        sr.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(1)
