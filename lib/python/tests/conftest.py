"""Shared fixtures for Garmin Messenger Python client tests."""

from __future__ import annotations

import time

import pytest

from garmin_messenger.api import HermesAPI
from garmin_messenger.auth import HermesAuth

# ---------------------------------------------------------------------------
# Deterministic test constants
# ---------------------------------------------------------------------------

CONV_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
MSG_ID = "11111111-2222-3333-4444-555555555555"
PARENT_MSG_ID = "66666666-7777-8888-9999-aaaaaaaaaaaa"
LAST_MSG_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
MEDIA_ID = "99999999-8888-7777-6666-555544443333"
INSTANCE_ID = "test-instance-id-12345"
USER_ID = "+15551234567"
RECIPIENT_ID = "+15559876543"
OTA_UUID = "22222222-3333-4444-5555-666677778888"
STATUS_USER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

ACCESS_TOKEN = "eyJ.test.token"
REFRESH_TOKEN = "refresh-token-xyz"


# ---------------------------------------------------------------------------
# Sample wire-format dicts (matching Hermes API JSON)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_otp_response():
    return {
        "requestId": "req-abc-123",
        "validUntil": "2025-06-01T12:00:00Z",
        "attemptsRemaining": 3,
    }


@pytest.fixture
def sample_registration_response():
    return {
        "instanceId": INSTANCE_ID,
        "accessAndRefreshToken": {
            "accessToken": ACCESS_TOKEN,
            "refreshToken": REFRESH_TOKEN,
            "expiresIn": 3600,
        },
    }


@pytest.fixture
def sample_message_dict():
    """Minimal message with the raw 'from' JSON key (Python keyword collision)."""
    return {
        "messageId": MSG_ID,
        "conversationId": CONV_ID,
        "messageBody": "Hello from satellite!",
        "from": USER_ID,
        "to": [RECIPIENT_ID],
        "sentAt": "2025-01-15T10:30:00Z",
        "receivedAt": "2025-01-15T10:30:05Z",
        "status": [
            {
                "userId": USER_ID,
                "appOrDeviceInstanceId": INSTANCE_ID,
                "deviceType": "MessengerApp",
                "messageStatus": "Delivered",
                "updatedAt": "2025-01-15T10:30:05Z",
            }
        ],
        "fromDeviceType": "MessengerApp",
    }


@pytest.fixture
def sample_message_full_dict():
    """All 24 fields of MessageModel populated."""
    return {
        "messageId": MSG_ID,
        "conversationId": CONV_ID,
        "parentMessageId": PARENT_MSG_ID,
        "messageBody": "Full message with all fields",
        "to": [RECIPIENT_ID],
        "from": USER_ID,
        "sentAt": "2025-01-15T10:30:00Z",
        "receivedAt": "2025-01-15T10:30:05Z",
        "status": [
            {
                "userId": USER_ID,
                "messageStatus": "Delivered",
            }
        ],
        "userLocation": {
            "latitudeDegrees": 45.5231,
            "longitudeDegrees": -122.6765,
            "elevationMeters": 100.0,
            "groundVelocityMetersPerSecond": 1.5,
            "courseDegrees": 270.0,
        },
        "referencePoint": {
            "latitudeDegrees": 46.0,
            "longitudeDegrees": -123.0,
        },
        "messageType": "MapShare",
        "mapShareUrl": "https://share.garmin.com/abc123",
        "mapSharePassword": "secret",
        "liveTrackUrl": "https://livetrack.garmin.com/xyz",
        "fromDeviceType": "inReach",
        "mediaId": MEDIA_ID,
        "mediaType": "ImageAvif",
        "mediaMetadata": {
            "width": 1920,
            "height": 1080,
            "durationMs": None,
        },
        "uuid": MSG_ID,
        "transcription": "Voice message transcription text",
        "otaUuid": OTA_UUID,
        "fromUnitId": "unit-001",
        "intendedUnitId": "unit-002",
    }


@pytest.fixture
def sample_conversation_meta_dict():
    return {
        "conversationId": CONV_ID,
        "memberIds": [USER_ID, RECIPIENT_ID],
        "updatedDate": "2025-01-15T10:30:00Z",
        "createdDate": "2025-01-01T00:00:00Z",
        "isMuted": False,
        "isPost": False,
    }


@pytest.fixture
def sample_conversation_detail_dict(sample_conversation_meta_dict):
    return {
        "metaData": sample_conversation_meta_dict,
        "messages": [
            {
                "messageId": MSG_ID,
                "messageBody": "Hello!",
                "from": USER_ID,
                "sentAt": "2025-01-15T10:30:00Z",
                "fromDeviceType": "MessengerApp",
            },
            {
                "messageId": LAST_MSG_ID,
                "messageBody": "Hi back!",
                "from": RECIPIENT_ID,
                "sentAt": "2025-01-15T10:31:00Z",
                "fromDeviceType": "MessengerApp",
            },
        ],
        "limit": 50,
        "lastMessageId": LAST_MSG_ID,
    }


@pytest.fixture
def sample_get_conversations_dict(sample_conversation_meta_dict):
    return {
        "conversations": [sample_conversation_meta_dict],
        "lastConversationId": CONV_ID,
    }


UPLOAD_URL = "https://s3.amazonaws.com/certus-media-manager-prod/"
S3_KEY = "media/uploads/test-object-key"
S3_DOWNLOAD_URL = (
    "https://s3.amazonaws.com/certus-media-manager-prod/media/test.avif"
    "?AWSAccessKeyId=AKIATEST&Signature=testsig&Expires=9999999999"
)


@pytest.fixture
def sample_signed_upload_url_dict():
    """Wire-format SignedUploadUrl with hyphenated field names."""
    return {
        "uploadUrl": UPLOAD_URL,
        "key": S3_KEY,
        "x-amz-storage-class": "STANDARD",
        "x-amz-date": "20250115T103000Z",
        "x-amz-signature": "abcdef1234567890",
        "x-amz-algorithm": "AWS4-HMAC-SHA256",
        "x-amz-credential": "AKIATEST/20250115/us-east-1/s3/aws4_request",
        "policy": "eyJleHBpcmF0aW9uIjoiMjAyNS0wMS0xNVQxMjowMDowMFoifQ==",
        "x-amz-meta-media-quality": "INTERNET",
        "content-type": "image/avif",
    }


@pytest.fixture
def sample_send_response_dict():
    return {
        "messageId": MSG_ID,
        "conversationId": CONV_ID,
        "signedUploadUrl": None,
        "imageQuality": None,
    }


@pytest.fixture
def sample_send_response_with_upload_dict(sample_signed_upload_url_dict):
    """SendMessageV2Response with signedUploadUrl populated (media message)."""
    return {
        "messageId": MSG_ID,
        "conversationId": CONV_ID,
        "signedUploadUrl": sample_signed_upload_url_dict,
        "imageQuality": "INTERNET",
    }


@pytest.fixture
def sample_media_download_url_dict():
    return {"url": S3_DOWNLOAD_URL}


@pytest.fixture
def sample_update_media_response_dict(sample_signed_upload_url_dict):
    return {
        "signedUploadUrl": sample_signed_upload_url_dict,
        "imageQuality": "INTERNET",
    }


@pytest.fixture
def sample_update_status_dict():
    return {
        "messageId": MSG_ID,
        "conversationId": CONV_ID,
        "status": "Read",
    }


@pytest.fixture
def sample_batch_status_response_dict():
    return [
        {"messageId": MSG_ID, "conversationId": CONV_ID, "status": "Read"},
        {"messageId": LAST_MSG_ID, "conversationId": CONV_ID, "status": "Delivered"},
    ]


@pytest.fixture
def sample_updated_statuses_dict():
    return {
        "statusReceiptsForMessages": [
            {
                "messageId": MSG_ID,
                "conversationId": CONV_ID,
                "statusReceipts": [
                    {
                        "userId": USER_ID,
                        "appOrDeviceInstanceId": INSTANCE_ID,
                        "deviceType": "MessengerApp",
                        "messageStatus": "Read",
                        "updatedAt": "2025-01-15T10:35:00Z",
                    }
                ],
            }
        ],
        "lastMessageId": MSG_ID,
    }


DEVICE_INSTANCE_ID = "dddddddd-1111-2222-3333-444455556666"


@pytest.fixture
def sample_device_metadata_dict():
    return [
        {
            "hasAllMtDeviceMetadata": True,
            "deviceMetadata": {
                "userId": USER_ID,
                "messageId": {"messageId": MSG_ID, "conversationId": CONV_ID},
                "deviceMessageMetadata": [
                    {
                        "deviceInstanceId": DEVICE_INSTANCE_ID,
                        "imei": 300234063904190,
                        "inReachMessageMetadata": [
                            {
                                "messageId": OTA_UUID,
                                "mtmsn": 42,
                                "text": "inReach Mini 2",
                                "otaUuid": OTA_UUID,
                            }
                        ],
                    }
                ],
            },
        }
    ]


@pytest.fixture
def sample_device_metadata_no_device_dict():
    return [
        {
            "hasAllMtDeviceMetadata": True,
            "deviceMetadata": {
                "userId": USER_ID,
                "messageId": {"messageId": MSG_ID, "conversationId": CONV_ID},
                "deviceMessageMetadata": None,
            },
        }
    ]


USER_IDENTIFIER_1 = "308812345678901"
USER_IDENTIFIER_2 = "308812345678902"


@pytest.fixture
def sample_conversation_members_dict():
    return [
        {
            "userIdentifier": USER_IDENTIFIER_1,
            "address": USER_ID,
            "friendlyName": "Alice",
            "imageUrl": "https://hermes.inreachapp.com/avatar/alice.jpg",
        },
        {
            "userIdentifier": USER_IDENTIFIER_2,
            "address": RECIPIENT_ID,
            "friendlyName": "Bob",
            "imageUrl": None,
        },
    ]


MUTE_CONV_ID_2 = "cccccccc-dddd-eeee-ffff-111122223333"


@pytest.fixture
def sample_muted_conversations_dict():
    return [
        {"conversationId": CONV_ID, "expires": "2025-02-01T00:00:00Z"},
        {"conversationId": MUTE_CONV_ID_2, "expires": None},
    ]


@pytest.fixture
def sample_network_properties_dict():
    return {"dataConstrained": False, "enablesPremiumMessaging": True}


@pytest.fixture
def sample_status_update_dict():
    """SignalR MessageStatusUpdate — note 'status' key (not 'messageStatus')."""
    return {
        "messageId": {
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
        },
        "status": "Delivered",
        "userId": STATUS_USER_UUID,
        "updatedAt": "2025-01-15T10:35:00Z",
    }


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth(tmp_path):
    """HermesAuth with a valid (non-expired) token."""
    auth = HermesAuth(
        hermes_base="https://hermes.inreachapp.com",
        session_dir=str(tmp_path),
    )
    auth.access_token = ACCESS_TOKEN
    auth.refresh_token = REFRESH_TOKEN
    auth.instance_id = INSTANCE_ID
    auth.expires_at = time.time() + 3600
    return auth


@pytest.fixture
def mock_expired_auth(tmp_path):
    """HermesAuth with an expired token."""
    auth = HermesAuth(
        hermes_base="https://hermes.inreachapp.com",
        session_dir=str(tmp_path),
    )
    auth.access_token = ACCESS_TOKEN
    auth.refresh_token = REFRESH_TOKEN
    auth.instance_id = INSTANCE_ID
    auth.expires_at = time.time() - 100
    return auth


# ---------------------------------------------------------------------------
# API fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def api(mock_auth):
    """HermesAPI client with mocked auth."""
    with HermesAPI(mock_auth) as client:
        yield client
