"""Shared fixtures for CLI tests.

Mock at the import boundary — patch garmin_messenger_cli.main.HermesAuth, etc.
so we never touch the actual client library.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from click.testing import CliRunner
from garmin_messenger.models import (
    ConversationDetailModel,
    ConversationMessageModel,
    ConversationMetaModel,
    ConversationMuteDetailModel,
    DeviceInstanceMetadata,
    DeviceMetadataEntry,
    GetConversationsModel,
    InReachMessageMetadata,
    MessageDeviceMetadataV2,
    NetworkPropertiesResponse,
    SendMessageV2Response,
    SignedUploadUrl,
    SimpleCompoundMessageId,
    UserInfoModel,
    UserLocation,
)

# ---------------------------------------------------------------------------
# Deterministic constants (shared with clients/python/tests)
# ---------------------------------------------------------------------------

CONV_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
MSG_ID = "11111111-2222-3333-4444-555555555555"
LAST_MSG_ID = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
INSTANCE_ID = "test-instance-id-12345"
USER_ID = "+15551234567"
RECIPIENT_ID = "+15559876543"
ACCESS_TOKEN = "eyJ.test.token"
REFRESH_TOKEN = "refresh-token-xyz"
STATUS_USER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

MODULE = "garmin_messenger_cli.main"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Mock class fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth_class():
    """Patch HermesAuth at the CLI import boundary.

    Returns (MockAuthClass, mock_instance).
    The instance has a valid access_token and resume() is a no-op.
    """
    with patch(f"{MODULE}.HermesAuth") as MockCls:
        instance = MagicMock()
        instance.access_token = ACCESS_TOKEN
        instance.refresh_token = REFRESH_TOKEN
        instance.instance_id = INSTANCE_ID
        instance.expires_at = time.time() + 3600
        instance.resume.return_value = None
        instance.request_otp.return_value = MagicMock(
            request_id="req-abc-123",
            phone_number="+15551234567",
            device_name="garmin-messenger",
        )
        instance.confirm_otp.return_value = None
        MockCls.return_value = instance
        yield MockCls, instance


@pytest.fixture
def mock_api_class():
    """Patch HermesAPI at the CLI import boundary.

    Returns (MockAPIClass, mock_instance).
    The instance supports `with` context manager.
    """
    with patch(f"{MODULE}.HermesAPI") as MockCls:
        instance = MagicMock()
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        MockCls.return_value = instance
        yield MockCls, instance


@pytest.fixture
def mock_signalr_class():
    """Patch HermesSignalR at the CLI import boundary.

    Returns (MockSRClass, mock_instance).
    """
    with patch(f"{MODULE}.HermesSignalR") as MockCls:
        instance = MagicMock()
        MockCls.return_value = instance
        yield MockCls, instance


# ---------------------------------------------------------------------------
# Sample Pydantic model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_conversations_result():
    """GetConversationsModel with one conversation."""
    return GetConversationsModel(
        conversations=[
            ConversationMetaModel(
                conversationId=UUID(CONV_ID),
                memberIds=[USER_ID, RECIPIENT_ID],
                updatedDate="2025-01-15T10:30:00Z",
                createdDate="2025-01-01T00:00:00Z",
                isMuted=False,
                isPost=False,
            )
        ],
        lastConversationId=UUID(CONV_ID),
    )


@pytest.fixture
def sample_conversation_detail_result():
    """ConversationDetailModel with 2 messages."""
    return ConversationDetailModel(
        metaData=ConversationMetaModel(
            conversationId=UUID(CONV_ID),
            memberIds=[USER_ID, RECIPIENT_ID],
            updatedDate="2025-01-15T10:30:00Z",
            createdDate="2025-01-01T00:00:00Z",
            isMuted=False,
            isPost=False,
        ),
        messages=[
            ConversationMessageModel(
                messageId=UUID(MSG_ID),
                messageBody="Hello!",
                from_=USER_ID,
                sentAt="2025-01-15T10:30:00Z",
                fromDeviceType="MessengerApp",
            ),
            ConversationMessageModel(
                messageId=UUID(LAST_MSG_ID),
                messageBody="Hi back!",
                from_=RECIPIENT_ID,
                sentAt="2025-01-15T10:31:00Z",
                fromDeviceType="MessengerApp",
            ),
        ],
        limit=50,
        lastMessageId=UUID(LAST_MSG_ID),
    )


@pytest.fixture
def sample_send_result():
    """Successful SendMessageV2Response."""
    return SendMessageV2Response(
        messageId=UUID(MSG_ID),
        conversationId=UUID(CONV_ID),
        signedUploadUrl=None,
        imageQuality=None,
    )


@pytest.fixture
def sample_empty_conversations():
    """GetConversationsModel with no conversations."""
    return GetConversationsModel(conversations=[], lastConversationId=None)


@pytest.fixture
def sample_empty_detail():
    """ConversationDetailModel with no messages."""
    return ConversationDetailModel(
        metaData=ConversationMetaModel(
            conversationId=UUID(CONV_ID),
            memberIds=[USER_ID, RECIPIENT_ID],
            updatedDate="2025-01-15T10:30:00Z",
            createdDate="2025-01-01T00:00:00Z",
            isMuted=False,
            isPost=False,
        ),
        messages=[],
        limit=50,
        lastMessageId=None,
    )


@pytest.fixture
def sample_send_media_result():
    """Successful SendMessageV2Response with a signed upload URL."""
    return SendMessageV2Response(
        messageId=UUID(MSG_ID),
        conversationId=UUID(CONV_ID),
        signedUploadUrl=SignedUploadUrl(
            uploadUrl="https://s3.amazonaws.com/certus-media-manager-prod/",
            key="media/uploads/test-object-key",
            **{
                "x-amz-storage-class": "STANDARD",
                "x-amz-date": "20250115T103000Z",
                "x-amz-signature": "abcdef1234567890",
                "x-amz-algorithm": "AWS4-HMAC-SHA256",
                "x-amz-credential": "AKIATEST/20250115/us-east-1/s3/aws4_request",
                "content-type": "image/avif",
            },
            policy="eyJleHBpcmF0aW9uIjoiMjAyNS0wMS0xNVQxMjowMDowMFoifQ==",
        ),
        imageQuality="INTERNET",
    )


@pytest.fixture
def sample_conversation_detail_with_location():
    """ConversationDetailModel with a message that has GPS location."""
    return ConversationDetailModel(
        metaData=ConversationMetaModel(
            conversationId=UUID(CONV_ID),
            memberIds=[USER_ID, RECIPIENT_ID],
            updatedDate="2025-01-15T10:30:00Z",
            createdDate="2025-01-01T00:00:00Z",
            isMuted=False,
            isPost=False,
        ),
        messages=[
            ConversationMessageModel(
                messageId=UUID(MSG_ID),
                messageBody="I'm here!",
                from_=USER_ID,
                sentAt="2025-01-15T10:30:00Z",
                fromDeviceType="MessengerApp",
                userLocation=UserLocation(
                    latitudeDegrees=45.5231,
                    longitudeDegrees=-122.6765,
                    elevationMeters=15.0,
                ),
            ),
        ],
        limit=50,
        lastMessageId=UUID(MSG_ID),
    )


USER_IDENTIFIER_1 = "308812345678901"
USER_IDENTIFIER_2 = "308812345678902"


@pytest.fixture
def sample_members_result():
    """List of UserInfoModel with 2 members."""
    return [
        UserInfoModel(
            userIdentifier=USER_IDENTIFIER_1,
            address=USER_ID,
            friendlyName="Alice",
            imageUrl="https://hermes.inreachapp.com/avatar/alice.jpg",
        ),
        UserInfoModel(
            userIdentifier=USER_IDENTIFIER_2,
            address=RECIPIENT_ID,
            friendlyName="Bob",
            imageUrl=None,
        ),
    ]


@pytest.fixture
def sample_empty_members():
    """Empty member list."""
    return []


@pytest.fixture
def sample_muted_result():
    """List of ConversationMuteDetailModel."""
    return [
        ConversationMuteDetailModel(
            conversationId=UUID(CONV_ID),
            expires="2025-02-01T00:00:00Z",
        ),
    ]


@pytest.fixture
def sample_network_result():
    """NetworkPropertiesResponse."""
    return NetworkPropertiesResponse(
        dataConstrained=False,
        enablesPremiumMessaging=True,
    )


@pytest.fixture
def sample_device_metadata_result():
    """List of MessageDeviceMetadataV2 with satellite device info."""
    return [
        MessageDeviceMetadataV2(
            hasAllMtDeviceMetadata=True,
            deviceMetadata=DeviceMetadataEntry(
                userId=USER_ID,
                messageId=SimpleCompoundMessageId(
                    messageId=UUID(MSG_ID), conversationId=UUID(CONV_ID),
                ),
                deviceMessageMetadata=[
                    DeviceInstanceMetadata(
                        deviceInstanceId=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                        imei=300234063904190,
                        inReachMessageMetadata=[
                            InReachMessageMetadata(
                                mtmsn=42,
                                text="inReach Mini 2",
                                otaUuid=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
                            ),
                        ],
                    ),
                ],
            ),
        ),
    ]


@pytest.fixture
def sample_device_metadata_no_device_result():
    """List of MessageDeviceMetadataV2 without satellite device info."""
    return [
        MessageDeviceMetadataV2(
            hasAllMtDeviceMetadata=True,
            deviceMetadata=DeviceMetadataEntry(
                userId=USER_ID,
                messageId=SimpleCompoundMessageId(
                    messageId=UUID(MSG_ID), conversationId=UUID(CONV_ID),
                ),
                deviceMessageMetadata=None,
            ),
        ),
    ]
