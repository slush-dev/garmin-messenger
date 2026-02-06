# Garmin Messenger — Python Library

Python library for the Garmin Messenger (Hermes) protocol. Send and receive messages to Garmin InReach satellite devices programmatically.

For protocol documentation and API reference, see the [root README](../../README.md) and [docs/api-reference.md](../../docs/api-reference.md). For the CLI tool, see [apps/python-cli/](../../apps/python-cli/).

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/slush-dev/garmin-messenger.git
cd garmin-messenger/lib/python

# Set up the virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Installation

```bash
cd lib/python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Dependencies

| Package | Purpose |
|---|---|
| `httpx` | HTTP client for REST API calls |
| `pydantic` | Data validation and typed models |
| `signalrcore` | Microsoft SignalR WebSocket client |
| `garth` | Garmin SSO/OAuth support |

## Library Usage

### Authentication

```python
from garmin_messenger import HermesAuth

auth = HermesAuth(session_dir="~/.garmin-messenger")

# First time: two-step SMS OTP registration
otp_request = auth.request_otp("+1234567890")
otp_code = input("Enter SMS OTP code: ")  # collect code however you like
auth.confirm_otp(otp_request, otp_code)

# Subsequent runs: resume saved session
auth.resume()
```

Credentials are saved to `~/.garmin-messenger/hermes_credentials.json` and automatically refreshed when expired.

### Sending Messages

```python
from garmin_messenger import HermesAPI, UserLocation

with HermesAPI(auth) as api:
    response = api.send_message(
        to=["+1234567890"],
        message_body="Hello from Python!",
        # Optional: attach your location
        user_location=UserLocation(
            latitudeDegrees=48.8566,
            longitudeDegrees=2.3522,
            elevationMeters=35.0,
        ),
    )
    print(f"Sent! Message ID: {response.messageId}")
    print(f"Conversation ID: {response.conversationId}")
```

### Listing Conversations and Messages

```python
with HermesAPI(auth) as api:
    # Get recent conversations
    result = api.get_conversations(limit=20)
    for conv in result.conversations:
        print(f"Conversation {conv.conversationId}")
        print(f"  Members: {conv.memberIds}")
        print(f"  Updated: {conv.updatedDate}")

    # Get messages from a specific conversation
    detail = api.get_conversation_detail(conv.conversationId, limit=50)
    for msg in detail.messages:
        print(f"  [{msg.sentAt}] {msg.from_}: {msg.messageBody}")
```

### Real-Time Message Receiving (WebSocket)

```python
from garmin_messenger import HermesSignalR

sr = HermesSignalR(auth)

# Listen for incoming messages
sr.on_message(lambda msg: print(f"New message from {msg.from_}: {msg.messageBody}"))

# Listen for delivery status updates
sr.on_status_update(lambda upd: print(f"Message {upd.messageId} -> {upd.messageStatus}"))

# Connection lifecycle
sr.on_open(lambda: print("Connected to Garmin Messenger"))
sr.on_close(lambda: print("Disconnected"))

# Start listening (blocks the current thread)
sr.start()
```

The WebSocket client includes automatic reconnection with exponential backoff (5s up to 120s), so your application stays connected through network interruptions.

### Marking Messages as Read/Delivered

```python
# Via REST API
with HermesAPI(auth) as api:
    api.mark_as_delivered(conversation_id, message_id)
    api.mark_as_read(conversation_id, message_id)

# Via SignalR (real-time)
sr.mark_as_delivered(message_id, conversation_id)
sr.mark_as_read(message_id, conversation_id)
```

### Sending Media Attachments

```python
from garmin_messenger import HermesAPI, MediaType

with HermesAPI(auth) as api:
    # Send a message with an image (AVIF) or audio (OGG)
    with open("photo.avif", "rb") as f:
        file_data = f.read()

    response = api.send_media_message(
        to=["+1234567890"],
        message_body="Photo from camp",
        file_data=file_data,
        media_type=MediaType.avif,
    )

    # Download a media attachment from a received message
    data = api.download_media(
        uuid=msg.uuid,
        media_type=MediaType(msg.mediaType),
        media_id=msg.mediaId,
        message_id=msg.messageId,
        conversation_id=msg.conversationId,
    )
    with open("downloaded.avif", "wb") as f:
        f.write(data)
```

### Managing Conversations

```python
with HermesAPI(auth) as api:
    # Get conversation members with phone numbers
    members = api.get_conversation_members(conversation_id)
    for m in members:
        print(f"  {m.friendlyName}: {m.address}")

    # Mute / unmute a conversation
    api.mute_conversation(conversation_id, muted=True)
    api.mute_conversation(conversation_id, muted=False)

    # List muted conversations
    muted = api.get_muted_conversations()

    # Block / unblock a user
    api.block_user(user_id)
    api.unblock_user(user_id)
    blocked = api.get_blocked_users()

    # Get account capabilities
    caps = api.get_capabilities()
```

### Device Metadata and Network

```python
from garmin_messenger.models import SimpleCompoundMessageId

with HermesAPI(auth) as api:
    # Get satellite device metadata for messages (IMEI, device type, etc.)
    ids = [SimpleCompoundMessageId(messageId=msg_id, conversationId=conv_id)]
    metadata = api.get_message_device_metadata(ids)
    for entry in metadata:
        for dev in entry.deviceMetadataEntries:
            for inst in dev.deviceInstanceMetadata:
                print(f"  Device: {inst.imei} ({inst.deviceType})")

    # Get Iridium network status
    network = api.get_network_properties()
```

### Batch Status Updates

```python
with HermesAPI(auth) as api:
    # Update multiple message statuses at once
    api.update_message_statuses(updates)

    # Get statuses updated since a timestamp
    updated = api.get_updated_statuses(conversation_id, since=timestamp)
```

### Phone Number to User ID

```python
from garmin_messenger import phone_to_hermes_user_id

# Convert a phone number to a Hermes UUID-v5 (used as memberIds, from_, etc.)
user_id = phone_to_hermes_user_id("+1234567890")
```

## Data Models

All API responses are parsed into typed [Pydantic](https://docs.pydantic.dev/) models. See [`src/garmin_messenger/models.py`](src/garmin_messenger/models.py) for full definitions.

| Model | Description |
|---|---|
| `MessageModel` | Full message with body, sender, timestamps, location, media, status |
| `ConversationMetaModel` | Conversation metadata: members, dates, mute status |
| `ConversationDetailModel` | Conversation with message history |
| `ConversationMemberModel` | Conversation member with phone number and display name |
| `UserLocation` | GPS coordinates, elevation, speed, heading |
| `SendMessageV2Response` | Response after sending (message ID, conversation ID, signed upload URL) |
| `MessageStatusUpdate` | Real-time delivery/read status change |
| `MessageDeviceMetadataV2` | Satellite device info (IMEI, device type, satellite message details) |
| `NetworkPropertiesResponse` | Iridium satellite network status |
| `DeviceType` | Enum: `MessengerApp`, `inReach`, `GarminOSApp`, etc. |
| `MessageStatus` | Enum: `Sent`, `Delivered`, `Read`, `Processing`, etc. |
| `MediaType` | Enum: `avif`, `ogg` |
| `HermesMessageType` | Enum: `text`, `MapLocation`, `InReachGenericMessage`, etc. |

## API Reference

| Method | Description |
|---|---|
| **Messaging** | |
| `send_message()` | Send a text message to one or more recipients |
| `send_media_message()` | Send a message with a media attachment (convenience) |
| **Conversations** | |
| `get_conversations()` | List recent conversations |
| `get_conversation_detail()` | Get messages from a conversation |
| `get_conversation_members()` | Get members with phone numbers and names |
| `mute_conversation()` | Mute or unmute a conversation |
| `get_muted_conversations()` | List muted conversations |
| **Status** | |
| `mark_as_read()` | Mark a message as read |
| `mark_as_delivered()` | Mark a message as delivered |
| `update_message_statuses()` | Batch update message statuses |
| `get_updated_statuses()` | Get statuses changed since a timestamp |
| **Media** | |
| `upload_media()` | Upload file to S3 via presigned POST |
| `download_media()` | Download a media attachment |
| `get_media_download_url()` | Get presigned S3 download URL |
| `update_media()` | Confirm upload or request new signed URL |
| **Users** | |
| `block_user()` / `unblock_user()` | Block or unblock a user |
| `get_blocked_users()` | List blocked users |
| `get_capabilities()` | Get account capabilities |
| **Device & Network** | |
| `get_message_device_metadata()` | Get satellite device info for messages |
| `get_network_properties()` | Get Iridium network status |

## Project Structure

```
lib/python/
├── pyproject.toml             # Package config and dependencies
├── src/
│   └── garmin_messenger/
│       ├── __init__.py        # Public exports
│       ├── auth.py            # SMS OTP authentication and token management
│       ├── api.py             # REST API client (httpx)
│       ├── signalr.py         # Real-time WebSocket client (SignalR)
│       └── models.py          # Pydantic data models (43+ models)
└── tests/                     # 231 unit tests
```

## Testing

```bash
cd lib/python
python -m pytest tests/ -v
```

231 tests across 5 test files covering models, API, SignalR, authentication, and UUID generation.

## Requirements

- Python 3.10+
- A Garmin Messenger account (see [root README](../../README.md#requirements))
