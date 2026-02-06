"""Tests for garmin_messenger.models — Pydantic model validation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from garmin_messenger.models import (
    AccessAndRefreshToken,
    AppRegistrationResponse,
    ConfirmAppRegistrationBody,
    ConversationDetailModel,
    ConversationMessageModel,
    ConversationMetaModel,
    ConversationMuteDetailModel,
    ConversationMuteStatusUpdate,
    DeviceInstanceMetadata,
    DeviceMetadataEntry,
    DeviceType,
    GetConversationsModel,
    GetUpdatedStatusesResponse,
    HermesMessageType,
    InReachMessageMetadata,
    MediaAttachmentDownloadUrlResponse,
    MediaMetadata,
    MediaType,
    MessageDeviceMetadataV2,
    MessageModel,
    MessageStatus,
    MessageStatusUpdate,
    NetworkPropertiesResponse,
    NewAppRegistrationBody,
    NewAppRegistrationResponse,
    NewInReachRegistrationUsingSsoResponse,
    RefreshAuthBody,
    SendMessageRequest,
    SendMessageV2Response,
    ServerNotification,
    SignedUploadUrl,
    SimpleCompoundMessageId,
    SmsOptInResult,
    StatusReceipt,
    StatusReceiptsForMessage,
    UpdateMediaRequest,
    UpdateMediaResponse,
    UpdateMessageStatusRequest,
    UpdateMessageStatusResponse,
    UserBlockStatusUpdate,
    UserInfoModel,
    UserLocation,
    phone_to_hermes_user_id,
)

from .conftest import (
    CONV_ID,
    MEDIA_ID,
    MSG_ID,
    RECIPIENT_ID,
    S3_DOWNLOAD_URL,
    S3_KEY,
    UPLOAD_URL,
    USER_ID,
    USER_IDENTIFIER_1,
)

# =========================================================================== #
# Enums
# =========================================================================== #


class TestDeviceType:
    def test_values(self):
        assert DeviceType.MESSENGER_APP == "MessengerApp"
        assert DeviceType.INREACH == "inReach"
        assert DeviceType.UNKNOWN == "Unknown"
        assert DeviceType.EXTERNAL == "External"
        assert DeviceType.GARMIN_OS_APP == "GarminOSApp"
        assert len(DeviceType) == 5


class TestMessageStatus:
    def test_values(self):
        expected = [
            ("INITIALIZED", "Initialized"),
            ("PROCESSING", "Processing"),
            ("SENT", "Sent"),
            ("DELIVERED", "Delivered"),
            ("READ", "Read"),
            ("UNDELIVERABLE", "Undeliverable"),
            ("RETRYABLE_ERROR", "RetryableError"),
            ("DELETED", "Deleted"),
            ("EXPIRED", "Expired"),
            ("UNINITIALIZED", "Uninitialized"),
        ]
        for attr, val in expected:
            assert getattr(MessageStatus, attr) == val
        assert len(MessageStatus) == 10


class TestHermesMessageType:
    def test_values(self):
        assert HermesMessageType.UNKNOWN == "Unknown"
        assert HermesMessageType.MAPSHARE == "MapShare"
        assert HermesMessageType.REFERENCE_POINT == "ReferencePoint"
        assert len(HermesMessageType) == 3


class TestMediaType:
    def test_values(self):
        assert MediaType.IMAGE_AVIF == "ImageAvif"
        assert MediaType.AUDIO_OGG == "AudioOgg"
        assert len(MediaType) == 2


# =========================================================================== #
# Shared sub-models
# =========================================================================== #


class TestUserLocation:
    def test_all_fields(self):
        loc = UserLocation(
            latitudeDegrees=45.5,
            longitudeDegrees=-122.6,
            elevationMeters=100.0,
            groundVelocityMetersPerSecond=1.5,
            courseDegrees=270.0,
        )
        assert loc.latitudeDegrees == 45.5
        assert loc.longitudeDegrees == -122.6
        assert loc.elevationMeters == 100.0
        assert loc.groundVelocityMetersPerSecond == 1.5
        assert loc.courseDegrees == 270.0

    def test_all_optional(self):
        loc = UserLocation()
        assert loc.latitudeDegrees is None
        assert loc.longitudeDegrees is None
        assert loc.elevationMeters is None
        assert loc.groundVelocityMetersPerSecond is None
        assert loc.courseDegrees is None

    def test_from_dict(self):
        loc = UserLocation.model_validate({"latitudeDegrees": 10.0})
        assert loc.latitudeDegrees == 10.0
        assert loc.longitudeDegrees is None


class TestStatusReceipt:
    def test_minimal(self):
        sr = StatusReceipt(userId="user1", messageStatus=MessageStatus.SENT)
        assert sr.userId == "user1"
        assert sr.messageStatus == MessageStatus.SENT
        assert sr.appOrDeviceInstanceId is None
        assert sr.deviceType is None
        assert sr.updatedAt is None

    def test_full(self):
        sr = StatusReceipt.model_validate({
            "userId": USER_ID,
            "appOrDeviceInstanceId": "inst-1",
            "deviceType": "MessengerApp",
            "messageStatus": "Delivered",
            "updatedAt": "2025-01-15T10:30:00Z",
        })
        assert sr.deviceType == DeviceType.MESSENGER_APP
        assert sr.messageStatus == MessageStatus.DELIVERED
        assert isinstance(sr.updatedAt, datetime)

    def test_enum_deserialization(self):
        sr = StatusReceipt.model_validate({
            "userId": "u",
            "messageStatus": "Read",
        })
        assert sr.messageStatus is MessageStatus.READ


class TestMediaMetadata:
    def test_defaults(self):
        mm = MediaMetadata()
        assert mm.width is None
        assert mm.height is None
        assert mm.durationMs is None

    def test_with_values(self):
        mm = MediaMetadata(width=1920, height=1080, durationMs=5000)
        assert mm.width == 1920
        assert mm.height == 1080
        assert mm.durationMs == 5000


class TestSignedUploadUrl:
    def test_minimal(self):
        u = SignedUploadUrl(uploadUrl="https://s3.amazonaws.com/bucket/key")
        assert u.uploadUrl == "https://s3.amazonaws.com/bucket/key"
        assert u.key is None
        assert u.policy is None

    def test_wire_format(self, sample_signed_upload_url_dict):
        """Parse wire-format JSON with hyphenated field names."""
        u = SignedUploadUrl.model_validate(sample_signed_upload_url_dict)
        assert u.uploadUrl == UPLOAD_URL
        assert u.key == S3_KEY
        assert u.xAmzStorageClass == "STANDARD"
        assert u.xAmzDate == "20250115T103000Z"
        assert u.xAmzSignature == "abcdef1234567890"
        assert u.xAmzAlgorithm == "AWS4-HMAC-SHA256"
        assert u.xAmzCredential == "AKIATEST/20250115/us-east-1/s3/aws4_request"
        assert u.policy == "eyJleHBpcmF0aW9uIjoiMjAyNS0wMS0xNVQxMjowMDowMFoifQ=="
        assert u.xAmzMetaMediaQuality == "INTERNET"
        assert u.contentType == "image/avif"

    def test_content_type_alias_variants(self):
        """content-type field has multiple case variants in the wild."""
        for key in ("content-type", "Content-type", "content-Type", "Content-Type"):
            u = SignedUploadUrl.model_validate(
                {"uploadUrl": "https://s3.example.com/", key: "audio/ogg"}
            )
            assert u.contentType == "audio/ogg", f"Failed for alias {key!r}"

    def test_python_field_names(self):
        """Can also construct with Python attribute names."""
        u = SignedUploadUrl(
            uploadUrl="https://s3.example.com/",
            key="media/123",
            xAmzAlgorithm="AWS4-HMAC-SHA256",
            policy="base64policy",
            contentType="image/avif",
        )
        assert u.key == "media/123"
        assert u.xAmzAlgorithm == "AWS4-HMAC-SHA256"
        assert u.contentType == "image/avif"

    def test_round_trip(self, sample_signed_upload_url_dict):
        """Parse wire format, dump by alias, re-parse."""
        u = SignedUploadUrl.model_validate(sample_signed_upload_url_dict)
        dumped = u.model_dump(mode="json", by_alias=True)
        u2 = SignedUploadUrl.model_validate(dumped)
        assert u2.xAmzSignature == u.xAmzSignature
        assert u2.contentType == u.contentType


class TestSimpleCompoundMessageId:
    def test_parse(self):
        scm = SimpleCompoundMessageId.model_validate({
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
        })
        assert isinstance(scm.messageId, UUID)
        assert isinstance(scm.conversationId, UUID)
        assert str(scm.messageId) == MSG_ID
        assert str(scm.conversationId) == CONV_ID


# =========================================================================== #
# MessageModel
# =========================================================================== #


class TestMessageModel:
    def test_from_keyword_mapping(self, sample_message_dict):
        """'from' in JSON dict maps to from_ attribute."""
        msg = MessageModel.model_validate(sample_message_dict)
        assert msg.from_ == USER_ID

    def test_from_underscore_passthrough(self):
        """'from_' key works directly."""
        msg = MessageModel.model_validate({
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
            "from_": USER_ID,
        })
        assert msg.from_ == USER_ID

    def test_minimal(self):
        msg = MessageModel.model_validate({
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
        })
        assert isinstance(msg.messageId, UUID)
        assert isinstance(msg.conversationId, UUID)
        assert msg.messageBody is None
        assert msg.from_ is None
        assert msg.to is None
        assert msg.status is None

    def test_full(self, sample_message_full_dict):
        msg = MessageModel.model_validate(sample_message_full_dict)
        assert msg.messageBody == "Full message with all fields"
        assert msg.from_ == USER_ID
        assert isinstance(msg.userLocation, UserLocation)
        assert msg.userLocation.latitudeDegrees == 45.5231
        assert isinstance(msg.referencePoint, UserLocation)
        assert msg.messageType == HermesMessageType.MAPSHARE
        assert msg.mapShareUrl == "https://share.garmin.com/abc123"
        assert msg.fromDeviceType == DeviceType.INREACH
        assert isinstance(msg.mediaMetadata, MediaMetadata)
        assert msg.mediaMetadata.width == 1920
        assert msg.transcription == "Voice message transcription text"

    def test_nested_status_receipts(self, sample_message_dict):
        msg = MessageModel.model_validate(sample_message_dict)
        assert isinstance(msg.status, list)
        assert len(msg.status) == 1
        assert isinstance(msg.status[0], StatusReceipt)
        assert msg.status[0].messageStatus == MessageStatus.DELIVERED

    def test_nested_user_location(self, sample_message_full_dict):
        msg = MessageModel.model_validate(sample_message_full_dict)
        assert isinstance(msg.userLocation, UserLocation)
        assert msg.userLocation.elevationMeters == 100.0

    def test_enum_fields(self, sample_message_full_dict):
        msg = MessageModel.model_validate(sample_message_full_dict)
        assert msg.fromDeviceType == DeviceType.INREACH
        assert msg.messageType == HermesMessageType.MAPSHARE
        assert msg.mediaType == MediaType.IMAGE_AVIF

    def test_uuid_fields(self, sample_message_full_dict):
        msg = MessageModel.model_validate(sample_message_full_dict)
        uuid_fields = (
            "messageId", "conversationId", "parentMessageId",
            "mediaId", "uuid", "otaUuid",
        )
        for field in uuid_fields:
            assert isinstance(getattr(msg, field), UUID), f"{field} should be UUID"

    def test_datetime_parsing(self, sample_message_dict):
        msg = MessageModel.model_validate(sample_message_dict)
        assert isinstance(msg.sentAt, datetime)
        assert isinstance(msg.receivedAt, datetime)
        assert msg.sentAt.year == 2025

    def test_round_trip(self, sample_message_dict):
        msg = MessageModel.model_validate(sample_message_dict)
        dumped = msg.model_dump(mode="json")
        msg2 = MessageModel.model_validate(dumped)
        assert msg2.messageId == msg.messageId
        assert msg2.messageBody == msg.messageBody
        assert msg2.from_ == msg.from_


# =========================================================================== #
# ConversationMessageModel
# =========================================================================== #


class TestConversationMessageModel:
    def test_from_keyword_mapping(self):
        msg = ConversationMessageModel.model_validate({
            "messageId": MSG_ID,
            "from": USER_ID,
        })
        assert msg.from_ == USER_ID

    def test_minimal(self):
        msg = ConversationMessageModel.model_validate({"messageId": MSG_ID})
        assert isinstance(msg.messageId, UUID)
        assert msg.messageBody is None
        assert msg.from_ is None

    def test_no_conversation_id_field(self):
        assert not hasattr(ConversationMessageModel.model_fields, "conversationId")
        assert "conversationId" not in ConversationMessageModel.model_fields
        assert "to" not in ConversationMessageModel.model_fields


# =========================================================================== #
# Conversation models
# =========================================================================== #


class TestConversationMetaModel:
    def test_from_dict(self, sample_conversation_meta_dict):
        meta = ConversationMetaModel.model_validate(sample_conversation_meta_dict)
        assert isinstance(meta.conversationId, UUID)
        assert meta.memberIds == [USER_ID, RECIPIENT_ID]
        assert isinstance(meta.updatedDate, datetime)
        assert isinstance(meta.createdDate, datetime)

    def test_defaults(self):
        meta = ConversationMetaModel.model_validate({
            "conversationId": CONV_ID,
            "memberIds": [USER_ID],
            "updatedDate": "2025-01-01T00:00:00Z",
            "createdDate": "2025-01-01T00:00:00Z",
        })
        assert meta.isMuted is False
        assert meta.isPost is False


class TestConversationDetailModel:
    def test_nested_parsing(self, sample_conversation_detail_dict):
        detail = ConversationDetailModel.model_validate(sample_conversation_detail_dict)
        assert isinstance(detail.metaData, ConversationMetaModel)
        assert isinstance(detail.messages, list)
        assert len(detail.messages) == 2
        assert isinstance(detail.messages[0], ConversationMessageModel)
        assert detail.messages[0].from_ == USER_ID
        assert detail.messages[1].from_ == RECIPIENT_ID
        assert detail.limit == 50
        assert isinstance(detail.lastMessageId, UUID)

    def test_empty_messages(self, sample_conversation_meta_dict):
        detail = ConversationDetailModel.model_validate({
            "metaData": sample_conversation_meta_dict,
            "messages": [],
            "limit": 50,
        })
        assert detail.messages == []
        assert detail.lastMessageId is None


class TestGetConversationsModel:
    def test_from_dict(self, sample_get_conversations_dict):
        result = GetConversationsModel.model_validate(sample_get_conversations_dict)
        assert len(result.conversations) == 1
        assert isinstance(result.conversations[0], ConversationMetaModel)
        assert isinstance(result.lastConversationId, UUID)

    def test_optional_last_id(self, sample_conversation_meta_dict):
        result = GetConversationsModel.model_validate({
            "conversations": [sample_conversation_meta_dict],
            "lastConversationId": None,
        })
        assert result.lastConversationId is None


# =========================================================================== #
# Request / response models
# =========================================================================== #


class TestSendMessageRequest:
    def test_minimal(self):
        req = SendMessageRequest(to=[RECIPIENT_ID], messageBody="Hello")
        assert req.to == [RECIPIENT_ID]
        assert req.messageBody == "Hello"
        assert req.userLocation is None
        assert req.isPost is False

    def test_serialization(self):
        req = SendMessageRequest(
            to=[RECIPIENT_ID],
            messageBody="Test",
            uuid=UUID(MSG_ID),
        )
        dumped = req.model_dump(mode="json")
        assert dumped["to"] == [RECIPIENT_ID]
        assert dumped["messageBody"] == "Test"
        assert dumped["uuid"] == MSG_ID


class TestSendMessageV2Response:
    def test_minimal(self, sample_send_response_dict):
        resp = SendMessageV2Response.model_validate(sample_send_response_dict)
        assert isinstance(resp.messageId, UUID)
        assert isinstance(resp.conversationId, UUID)
        assert resp.signedUploadUrl is None

    def test_with_upload_url(self, sample_send_response_with_upload_dict):
        resp = SendMessageV2Response.model_validate(
            sample_send_response_with_upload_dict,
        )
        assert isinstance(resp.signedUploadUrl, SignedUploadUrl)
        assert resp.signedUploadUrl.uploadUrl == UPLOAD_URL
        assert resp.signedUploadUrl.xAmzAlgorithm == "AWS4-HMAC-SHA256"
        assert resp.imageQuality == "INTERNET"


class TestUpdateMessageStatusResponse:
    def test_all_optional(self):
        resp = UpdateMessageStatusResponse.model_validate({})
        assert resp.messageId is None
        assert resp.conversationId is None
        assert resp.status is None

    def test_full(self, sample_update_status_dict):
        resp = UpdateMessageStatusResponse.model_validate(sample_update_status_dict)
        assert isinstance(resp.messageId, UUID)
        assert resp.status == MessageStatus.READ


# =========================================================================== #
# Auth models
# =========================================================================== #


class TestAccessAndRefreshToken:
    def test_fields(self):
        t = AccessAndRefreshToken(
            accessToken="at", refreshToken="rt", expiresIn=3600
        )
        assert t.accessToken == "at"
        assert t.refreshToken == "rt"
        assert t.expiresIn == 3600


class TestNewAppRegistrationBody:
    def test_defaults(self):
        body = NewAppRegistrationBody(smsNumber="+1234")
        assert body.smsNumber == "+1234"
        assert body.platform == "android"


class TestNewAppRegistrationResponse:
    def test_parse(self, sample_otp_response):
        resp = NewAppRegistrationResponse.model_validate(sample_otp_response)
        assert resp.requestId == "req-abc-123"
        assert resp.attemptsRemaining == 3


class TestConfirmAppRegistrationBody:
    def test_defaults(self):
        body = ConfirmAppRegistrationBody(
            requestId="req-1",
            smsNumber="+1234",
            verificationCode="123456",
        )
        assert body.platform == "android"
        assert body.pnsEnvironment == "Production"
        assert body.appDescription == "garmin-messenger"
        assert body.optInForSms is True
        assert len(body.pnsHandle) > 100


class TestAppRegistrationResponse:
    def test_nested_tokens(self, sample_registration_response):
        resp = AppRegistrationResponse.model_validate(sample_registration_response)
        assert resp.instanceId == "test-instance-id-12345"
        assert isinstance(resp.accessAndRefreshToken, AccessAndRefreshToken)
        assert resp.accessAndRefreshToken.expiresIn == 3600
        assert resp.smsOptInResult is None


class TestRefreshAuthBody:
    def test_fields(self):
        body = RefreshAuthBody(refreshToken="rt", instanceId="inst")
        assert body.refreshToken == "rt"
        assert body.instanceId == "inst"


class TestSmsOptInResult:
    def test_all_optional(self):
        r = SmsOptInResult()
        assert r.success is None
        assert r.fatalError is None


class TestNewInReachRegistrationUsingSsoResponse:
    def test_parse(self):
        resp = NewInReachRegistrationUsingSsoResponse.model_validate({
            "instanceId": "inreach-inst-001",
            "accessAndRefreshToken": {
                "accessToken": "sso-at",
                "refreshToken": "sso-rt",
                "expiresIn": 7200,
            },
        })
        assert resp.instanceId == "inreach-inst-001"
        assert isinstance(resp.accessAndRefreshToken, AccessAndRefreshToken)
        assert resp.accessAndRefreshToken.expiresIn == 7200


# =========================================================================== #
# SignalR event models
# =========================================================================== #


class TestMessageStatusUpdate:
    def test_status_key_remap(self, sample_status_update_dict):
        """'status' key (not 'messageStatus') should be remapped."""
        update = MessageStatusUpdate.model_validate(sample_status_update_dict)
        assert update.messageStatus == MessageStatus.DELIVERED
        assert isinstance(update.messageId, SimpleCompoundMessageId)
        assert isinstance(update.userId, UUID)

    def test_with_message_status_key(self):
        """Native 'messageStatus' key works directly."""
        update = MessageStatusUpdate.model_validate({
            "messageId": {"messageId": MSG_ID, "conversationId": CONV_ID},
            "messageStatus": "Read",
        })
        assert update.messageStatus == MessageStatus.READ

    def test_message_status_takes_precedence(self):
        """When both 'status' and 'messageStatus' present, messageStatus wins."""
        update = MessageStatusUpdate.model_validate({
            "messageId": {"messageId": MSG_ID, "conversationId": CONV_ID},
            "status": "Delivered",
            "messageStatus": "Read",
        })
        assert update.messageStatus == MessageStatus.READ


class TestConversationMuteStatusUpdate:
    def test_fields(self):
        update = ConversationMuteStatusUpdate.model_validate({
            "conversationId": CONV_ID,
            "isMuted": True,
        })
        assert isinstance(update.conversationId, UUID)
        assert update.isMuted is True

    def test_all_optional(self):
        update = ConversationMuteStatusUpdate.model_validate({})
        assert update.conversationId is None
        assert update.isMuted is None


class TestUserBlockStatusUpdate:
    def test_fields(self):
        update = UserBlockStatusUpdate.model_validate({
            "userId": USER_ID,
            "isBlocked": True,
        })
        assert update.userId == USER_ID
        assert update.isBlocked is True

    def test_all_optional(self):
        update = UserBlockStatusUpdate.model_validate({})
        assert update.userId is None
        assert update.isBlocked is None


class TestServerNotification:
    def test_fields(self):
        notif = ServerNotification.model_validate({
            "notificationType": "Maintenance",
            "message": "Server restarting",
        })
        assert notif.notificationType == "Maintenance"
        assert notif.message == "Server restarting"

    def test_all_optional(self):
        notif = ServerNotification.model_validate({})
        assert notif.notificationType is None
        assert notif.message is None


# =========================================================================== #
# Media attachment models
# =========================================================================== #


class TestUpdateMediaRequest:
    def test_minimal(self):
        req = UpdateMediaRequest(
            mediaType=MediaType.IMAGE_AVIF,
            mediaId=UUID(MEDIA_ID),
        )
        assert req.mediaType == MediaType.IMAGE_AVIF
        assert isinstance(req.mediaId, UUID)
        assert req.messageId is None
        assert req.conversationId is None

    def test_full(self):
        req = UpdateMediaRequest(
            mediaType=MediaType.AUDIO_OGG,
            mediaId=UUID(MEDIA_ID),
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
        )
        assert req.mediaType == MediaType.AUDIO_OGG
        assert str(req.messageId) == MSG_ID
        assert str(req.conversationId) == CONV_ID

    def test_serialization(self):
        req = UpdateMediaRequest(
            mediaType=MediaType.IMAGE_AVIF,
            mediaId=UUID(MEDIA_ID),
            messageId=UUID(MSG_ID),
        )
        dumped = req.model_dump(mode="json")
        assert dumped["mediaType"] == "ImageAvif"
        assert dumped["mediaId"] == MEDIA_ID
        assert dumped["messageId"] == MSG_ID


class TestUpdateMediaResponse:
    def test_parse(self, sample_update_media_response_dict):
        resp = UpdateMediaResponse.model_validate(sample_update_media_response_dict)
        assert isinstance(resp.signedUploadUrl, SignedUploadUrl)
        assert resp.signedUploadUrl.uploadUrl == UPLOAD_URL
        assert resp.imageQuality == "INTERNET"

    def test_optional_quality(self, sample_signed_upload_url_dict):
        resp = UpdateMediaResponse.model_validate({
            "signedUploadUrl": sample_signed_upload_url_dict,
        })
        assert resp.imageQuality is None


class TestMediaAttachmentDownloadUrlResponse:
    def test_parse(self, sample_media_download_url_dict):
        resp = MediaAttachmentDownloadUrlResponse.model_validate(
            sample_media_download_url_dict,
        )
        assert resp.downloadUrl == S3_DOWNLOAD_URL

    def test_from_dict(self):
        resp = MediaAttachmentDownloadUrlResponse.model_validate(
            {"downloadUrl": "https://s3.example.com/media/file.avif?sig=abc"},
        )
        assert resp.downloadUrl.startswith("https://s3.example.com/")


# =========================================================================== #
# Batch status / updated statuses models
# =========================================================================== #


class TestUpdateMessageStatusRequest:
    def test_construction(self):
        req = UpdateMessageStatusRequest(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageStatus=MessageStatus.READ,
        )
        assert str(req.messageId) == MSG_ID
        assert str(req.conversationId) == CONV_ID
        assert req.messageStatus == MessageStatus.READ

    def test_serialization(self):
        req = UpdateMessageStatusRequest(
            messageId=UUID(MSG_ID),
            conversationId=UUID(CONV_ID),
            messageStatus=MessageStatus.DELIVERED,
        )
        dumped = req.model_dump(mode="json")
        assert dumped["messageId"] == MSG_ID
        assert dumped["conversationId"] == CONV_ID
        assert dumped["messageStatus"] == "Delivered"

    def test_from_dict(self):
        req = UpdateMessageStatusRequest.model_validate({
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
            "messageStatus": "Read",
        })
        assert req.messageStatus is MessageStatus.READ


class TestStatusReceiptsForMessage:
    def test_with_receipts(self):
        obj = StatusReceiptsForMessage.model_validate({
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
            "statusReceipts": [
                {"userId": USER_ID, "messageStatus": "Read"},
            ],
        })
        assert isinstance(obj.messageId, UUID)
        assert len(obj.statusReceipts) == 1
        assert isinstance(obj.statusReceipts[0], StatusReceipt)
        assert obj.statusReceipts[0].messageStatus == MessageStatus.READ

    def test_without_receipts(self):
        obj = StatusReceiptsForMessage.model_validate({
            "messageId": MSG_ID,
            "conversationId": CONV_ID,
        })
        assert obj.statusReceipts is None


class TestGetUpdatedStatusesResponse:
    def test_parse(self, sample_updated_statuses_dict):
        resp = GetUpdatedStatusesResponse.model_validate(sample_updated_statuses_dict)
        assert len(resp.statusReceiptsForMessages) == 1
        msg = resp.statusReceiptsForMessages[0]
        assert isinstance(msg, StatusReceiptsForMessage)
        assert isinstance(msg.messageId, UUID)
        assert len(msg.statusReceipts) == 1
        assert isinstance(resp.lastMessageId, UUID)

    def test_empty_list(self):
        resp = GetUpdatedStatusesResponse.model_validate({
            "statusReceiptsForMessages": [],
        })
        assert resp.statusReceiptsForMessages == []
        assert resp.lastMessageId is None


# =========================================================================== #
# Conversation member / mute models
# =========================================================================== #


class TestUserInfoModel:
    def test_all_fields(self):
        info = UserInfoModel.model_validate({
            "userIdentifier": USER_IDENTIFIER_1,
            "address": USER_ID,
            "friendlyName": "Alice",
            "imageUrl": "https://example.com/avatar.jpg",
        })
        assert info.userIdentifier == USER_IDENTIFIER_1
        assert info.address == USER_ID
        assert info.friendlyName == "Alice"
        assert info.imageUrl == "https://example.com/avatar.jpg"

    def test_all_optional(self):
        info = UserInfoModel()
        assert info.userIdentifier is None
        assert info.address is None
        assert info.friendlyName is None
        assert info.imageUrl is None

    def test_list_parse(self, sample_conversation_members_dict):
        members = [UserInfoModel.model_validate(m)
                    for m in sample_conversation_members_dict]
        assert len(members) == 2
        assert isinstance(members[0], UserInfoModel)
        assert members[0].friendlyName == "Alice"
        assert members[1].friendlyName == "Bob"
        assert members[1].imageUrl is None


class TestConversationMuteDetailModel:
    def test_with_expires(self):
        obj = ConversationMuteDetailModel.model_validate({
            "conversationId": CONV_ID,
            "expires": "2025-02-01T00:00:00Z",
        })
        assert isinstance(obj.conversationId, UUID)
        assert isinstance(obj.expires, datetime)

    def test_without_expires(self):
        obj = ConversationMuteDetailModel.model_validate({
            "conversationId": CONV_ID,
            "expires": None,
        })
        assert obj.expires is None

    def test_list_parse(self, sample_muted_conversations_dict):
        items = [ConversationMuteDetailModel.model_validate(c)
                 for c in sample_muted_conversations_dict]
        assert len(items) == 2
        assert items[0].expires is not None
        assert items[1].expires is None


# =========================================================================== #
# Device metadata / network properties models
# =========================================================================== #


class TestMessageDeviceMetadataV2:
    def test_full(self, sample_device_metadata_dict):
        md = MessageDeviceMetadataV2.model_validate(sample_device_metadata_dict[0])
        assert md.hasAllMtDeviceMetadata is True
        assert md.deviceMetadata is not None
        assert isinstance(md.deviceMetadata, DeviceMetadataEntry)
        assert md.deviceMetadata.messageId.messageId == UUID(MSG_ID)
        assert md.deviceMetadata.messageId.conversationId == UUID(CONV_ID)
        devices = md.deviceMetadata.deviceMessageMetadata
        assert isinstance(devices, list)
        assert len(devices) == 1
        dev = devices[0]
        assert isinstance(dev, DeviceInstanceMetadata)
        assert dev.imei == 300234063904190
        sat = dev.inReachMessageMetadata
        assert isinstance(sat, list)
        assert len(sat) == 1
        assert isinstance(sat[0], InReachMessageMetadata)
        assert sat[0].mtmsn == 42
        assert sat[0].text == "inReach Mini 2"
        assert isinstance(sat[0].otaUuid, UUID)

    def test_no_device_metadata(self, sample_device_metadata_no_device_dict):
        md = MessageDeviceMetadataV2.model_validate(
            sample_device_metadata_no_device_dict[0]
        )
        assert md.hasAllMtDeviceMetadata is True
        assert md.deviceMetadata is not None
        assert md.deviceMetadata.deviceMessageMetadata is None

    def test_minimal(self):
        md = MessageDeviceMetadataV2()
        assert md.hasAllMtDeviceMetadata is False
        assert md.deviceMetadata is None


class TestNetworkPropertiesResponse:
    def test_defaults(self):
        resp = NetworkPropertiesResponse()
        assert resp.dataConstrained is False
        assert resp.enablesPremiumMessaging is False

    def test_explicit_values(self, sample_network_properties_dict):
        resp = NetworkPropertiesResponse.model_validate(sample_network_properties_dict)
        assert resp.dataConstrained is False
        assert resp.enablesPremiumMessaging is True

    def test_all_true(self):
        resp = NetworkPropertiesResponse.model_validate({
            "dataConstrained": True,
            "enablesPremiumMessaging": True,
        })
        assert resp.dataConstrained is True
        assert resp.enablesPremiumMessaging is True


# =========================================================================== #
# phone_to_hermes_user_id
# =========================================================================== #


class TestPhoneToHermesUserId:
    def test_known_vector(self):
        assert phone_to_hermes_user_id("+15555550100") == "11153808-b0a5-5f9b-bbcf-b35be7e4359e"

    def test_is_uuid_v5(self):
        result = phone_to_hermes_user_id("+15551234567")
        u = UUID(result)
        assert u.version == 5

    def test_deterministic(self):
        a = phone_to_hermes_user_id("+15551234567")
        b = phone_to_hermes_user_id("+15551234567")
        assert a == b

    def test_different_phones_differ(self):
        a = phone_to_hermes_user_id("+15551234567")
        b = phone_to_hermes_user_id("+15559876543")
        assert a != b
