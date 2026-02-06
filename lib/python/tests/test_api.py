"""Tests for garmin_messenger.api — HermesAPI REST client."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import httpx
import pytest

from garmin_messenger.api import HermesAPI
from garmin_messenger.auth import HERMES_BASE
from garmin_messenger.models import (
    ConversationDetailModel,
    ConversationMuteDetailModel,
    GetConversationsModel,
    GetUpdatedStatusesResponse,
    HermesMessageType,
    MediaAttachmentDownloadUrlResponse,
    MediaType,
    MessageDeviceMetadataV2,
    MessageStatus,
    NetworkPropertiesResponse,
    SendMessageV2Response,
    SignedUploadUrl,
    SimpleCompoundMessageId,
    UpdateMediaResponse,
    UpdateMessageStatusRequest,
    UpdateMessageStatusResponse,
    UserInfoModel,
    UserLocation,
)

from .conftest import (
    CONV_ID,
    LAST_MSG_ID,
    MEDIA_ID,
    MSG_ID,
    RECIPIENT_ID,
    S3_DOWNLOAD_URL,
    UPLOAD_URL,
    USER_ID,
)

BASE = HERMES_BASE


# =========================================================================== #
# Context manager
# =========================================================================== #


class TestContextManager:
    def test_enter_exit(self, mock_auth):
        api = HermesAPI(mock_auth)
        with api as client:
            assert client is api
        assert api._client.is_closed

    def test_close(self, mock_auth):
        api = HermesAPI(mock_auth)
        api.close()
        assert api._client.is_closed


# =========================================================================== #
# get_conversations
# =========================================================================== #


class TestGetConversations:
    def test_defaults(self, httpx_mock, api, sample_get_conversations_dict):
        httpx_mock.add_response(
            url=f"{BASE}/Conversation/Updated?Limit=50",
            json=sample_get_conversations_dict,
        )
        result = api.get_conversations()
        assert isinstance(result, GetConversationsModel)
        assert len(result.conversations) == 1

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert req.headers["Api-Version"] == "1.0"

    def test_with_after_date(self, httpx_mock, api, sample_get_conversations_dict):
        httpx_mock.add_response(json=sample_get_conversations_dict)
        dt = datetime(2025, 1, 1, 0, 0, 0)
        api.get_conversations(after_date=dt)

        req = httpx_mock.get_requests()[0]
        assert "AfterDate" in str(req.url)

    def test_custom_limit(self, httpx_mock, api, sample_get_conversations_dict):
        httpx_mock.add_response(json=sample_get_conversations_dict)
        api.get_conversations(limit=10)

        req = httpx_mock.get_requests()[0]
        assert "Limit=10" in str(req.url)

    def test_empty_list(self, httpx_mock, api):
        httpx_mock.add_response(
            json={"conversations": [], "lastConversationId": None},
        )
        result = api.get_conversations()
        assert result.conversations == []

    def test_server_error(self, httpx_mock, api):
        httpx_mock.add_response(status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            api.get_conversations()


# =========================================================================== #
# get_conversation_detail
# =========================================================================== #


class TestGetConversationDetail:
    def test_basic(self, httpx_mock, api, sample_conversation_detail_dict):
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(json=sample_conversation_detail_dict)

        result = api.get_conversation_detail(conv_id)
        assert isinstance(result, ConversationDetailModel)
        assert len(result.messages) == 2

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert CONV_ID in str(req.url)
        assert req.headers["Api-Version"] == "2.0"

    def test_with_older_than_id(self, httpx_mock, api, sample_conversation_detail_dict):
        conv_id = UUID(CONV_ID)
        older = UUID(MSG_ID)
        httpx_mock.add_response(json=sample_conversation_detail_dict)

        api.get_conversation_detail(conv_id, older_than_id=older)

        req = httpx_mock.get_requests()[0]
        assert "olderThanId" in str(req.url)

    def test_with_newer_than_id(self, httpx_mock, api, sample_conversation_detail_dict):
        conv_id = UUID(CONV_ID)
        newer = UUID(MSG_ID)
        httpx_mock.add_response(json=sample_conversation_detail_dict)

        api.get_conversation_detail(conv_id, newer_than_id=newer)

        req = httpx_mock.get_requests()[0]
        assert "newerThanId" in str(req.url)

    def test_nested_messages_from_mapping(self, httpx_mock, api,
                                          sample_conversation_detail_dict):
        """Verify 'from' → 'from_' mapping works for nested messages."""
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(json=sample_conversation_detail_dict)

        result = api.get_conversation_detail(conv_id)
        assert result.messages[0].from_ == USER_ID
        assert result.messages[1].from_ == RECIPIENT_ID
        assert result.messages[0].messageBody == "Hello!"
        assert result.messages[1].messageBody == "Hi back!"


# =========================================================================== #
# mute_conversation
# =========================================================================== #


class TestMuteConversation:
    def test_mute(self, httpx_mock, api):
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(status_code=200)

        api.mute_conversation(conv_id, muted=True)

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert f"{CONV_ID}/Mute" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"
        body = json.loads(req.content)
        assert body["isMuted"] is True

    def test_unmute(self, httpx_mock, api):
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(status_code=200)

        api.mute_conversation(conv_id, muted=False)

        req = httpx_mock.get_requests()[0]
        assert f"{CONV_ID}/Unmute" in str(req.url)


# =========================================================================== #
# send_message
# =========================================================================== #


class TestSendMessage:
    def test_basic(self, httpx_mock, api, sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        result = api.send_message(to=[RECIPIENT_ID], message_body="Hello!")
        assert isinstance(result, SendMessageV2Response)
        assert isinstance(result.messageId, UUID)

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert "Message/Send" in str(req.url)
        assert req.headers["Api-Version"] == "2.0"

    def test_generates_uuid_and_ota_uuid(self, httpx_mock, api,
                                         sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        api.send_message(to=[RECIPIENT_ID], message_body="Test")

        req = httpx_mock.get_requests()[0]
        body = json.loads(req.content)
        assert body["uuid"] is not None
        assert body["otaUuid"] is not None
        # Verify they parse as valid UUIDs
        UUID(body["uuid"])
        UUID(body["otaUuid"])

    def test_request_body_structure(self, httpx_mock, api,
                                    sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        api.send_message(to=[RECIPIENT_ID], message_body="Test msg")

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["to"] == [RECIPIENT_ID]
        assert body["messageBody"] == "Test msg"
        assert body["isPost"] is False
        # userLocation and referencePoint are serialized as null
        assert "userLocation" in body
        assert "referencePoint" in body

    def test_with_location(self, httpx_mock, api, sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        loc = UserLocation(latitudeDegrees=45.0, longitudeDegrees=-120.0)
        api.send_message(to=[RECIPIENT_ID], message_body="Loc", user_location=loc)

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["userLocation"]["latitudeDegrees"] == 45.0

    def test_with_reference_point(self, httpx_mock, api, sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        ref = UserLocation(latitudeDegrees=46.0, longitudeDegrees=-123.0)
        api.send_message(to=[RECIPIENT_ID], message_body="Ref", reference_point=ref)

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["referencePoint"]["latitudeDegrees"] == 46.0
        assert body["referencePoint"]["longitudeDegrees"] == -123.0

    def test_with_media(self, httpx_mock, api, sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        api.send_message(
            to=[RECIPIENT_ID],
            message_body="Photo",
            media_id=UUID(MEDIA_ID),
            media_type=MediaType.IMAGE_AVIF,
        )

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["mediaId"] == MEDIA_ID
        assert body["mediaType"] == "ImageAvif"

    def test_with_is_post(self, httpx_mock, api, sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        api.send_message(to=[RECIPIENT_ID], message_body="Post", is_post=True)

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["isPost"] is True

    def test_with_message_type(self, httpx_mock, api, sample_send_response_dict):
        httpx_mock.add_response(json=sample_send_response_dict)

        api.send_message(
            to=[RECIPIENT_ID],
            message_body="Location",
            message_type=HermesMessageType.MAPSHARE,
        )

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["messageType"] == "MapShare"

    def test_server_error(self, httpx_mock, api):
        httpx_mock.add_response(status_code=400)
        with pytest.raises(httpx.HTTPStatusError):
            api.send_message(to=[RECIPIENT_ID], message_body="Fail")


# =========================================================================== #
# Media attachments
# =========================================================================== #


class TestUploadMedia:
    def test_posts_to_s3_with_form_fields(self, httpx_mock, api,
                                           sample_signed_upload_url_dict):
        signed_url = SignedUploadUrl.model_validate(sample_signed_upload_url_dict)
        httpx_mock.add_response(url=UPLOAD_URL, status_code=204)

        api.upload_media(signed_url, b"fake-image-bytes")

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert str(req.url) == UPLOAD_URL
        # Verify multipart form data contains the S3 signing fields
        body = req.content.decode("utf-8", errors="replace")
        assert "STANDARD" in body  # x-amz-storage-class
        assert "AWS4-HMAC-SHA256" in body  # x-amz-algorithm
        assert "fake-image-bytes" in body  # file content

    def test_raises_on_s3_error(self, httpx_mock, api,
                                 sample_signed_upload_url_dict):
        signed_url = SignedUploadUrl.model_validate(sample_signed_upload_url_dict)
        httpx_mock.add_response(url=UPLOAD_URL, status_code=403)

        with pytest.raises(httpx.HTTPStatusError):
            api.upload_media(signed_url, b"data")

    def test_minimal_signed_url(self, httpx_mock, api):
        """Works with a signed URL that only has uploadUrl and key."""
        signed_url = SignedUploadUrl(uploadUrl=UPLOAD_URL, key="test/key")
        httpx_mock.add_response(url=UPLOAD_URL, status_code=204)

        api.upload_media(signed_url, b"data")

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"


class TestGetMediaDownloadUrl:
    def test_basic(self, httpx_mock, api, sample_media_download_url_dict):
        httpx_mock.add_response(json=sample_media_download_url_dict)

        result = api.get_media_download_url(
            uuid=UUID(MSG_ID),
            media_type=MediaType.IMAGE_AVIF,
            media_id=UUID(MEDIA_ID),
            message_id=UUID(MSG_ID),
            conversation_id=UUID(CONV_ID),
        )
        assert isinstance(result, MediaAttachmentDownloadUrlResponse)
        assert result.url == S3_DOWNLOAD_URL

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert "Message/Media/DownloadUrl" in str(req.url)
        assert req.headers["Api-Version"] == "2.0"
        assert f"mediaId={MEDIA_ID}" in str(req.url)
        assert "mediaType=ImageAvif" in str(req.url)

    def test_server_error(self, httpx_mock, api):
        httpx_mock.add_response(status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            api.get_media_download_url(
                uuid=UUID(MSG_ID),
                media_type=MediaType.IMAGE_AVIF,
                media_id=UUID(MEDIA_ID),
                message_id=UUID(MSG_ID),
                conversation_id=UUID(CONV_ID),
            )


class TestDownloadMedia:
    def test_fetches_presigned_url_then_downloads(self, httpx_mock, api,
                                                    sample_media_download_url_dict):
        # Mock the Hermes endpoint
        httpx_mock.add_response(json=sample_media_download_url_dict)
        # Mock the S3 download
        httpx_mock.add_response(
            url=S3_DOWNLOAD_URL,
            content=b"raw-image-data",
        )

        data = api.download_media(
            uuid=UUID(MSG_ID),
            media_type=MediaType.IMAGE_AVIF,
            media_id=UUID(MEDIA_ID),
            message_id=UUID(MSG_ID),
            conversation_id=UUID(CONV_ID),
        )
        assert data == b"raw-image-data"
        assert len(httpx_mock.get_requests()) == 2


class TestUpdateMedia:
    def test_basic(self, httpx_mock, api, sample_update_media_response_dict):
        httpx_mock.add_response(json=sample_update_media_response_dict)

        result = api.update_media(
            media_type=MediaType.IMAGE_AVIF,
            media_id=UUID(MEDIA_ID),
            message_id=UUID(MSG_ID),
            conversation_id=UUID(CONV_ID),
        )
        assert isinstance(result, UpdateMediaResponse)
        assert isinstance(result.signedUploadUrl, SignedUploadUrl)
        assert result.imageQuality == "INTERNET"

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert "Message/UpdateMedia" in str(req.url)
        assert req.headers["Api-Version"] == "2.0"
        body = json.loads(req.content)
        assert body["mediaType"] == "ImageAvif"
        assert body["mediaId"] == MEDIA_ID

    def test_optional_fields(self, httpx_mock, api,
                              sample_update_media_response_dict):
        httpx_mock.add_response(json=sample_update_media_response_dict)

        api.update_media(
            media_type=MediaType.AUDIO_OGG,
            media_id=UUID(MEDIA_ID),
        )

        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["messageId"] is None
        assert body["conversationId"] is None


class TestSendMediaMessage:
    def test_sends_message_then_uploads(self, httpx_mock, api,
                                         sample_send_response_with_upload_dict):
        # Mock send endpoint
        httpx_mock.add_response(json=sample_send_response_with_upload_dict)
        # Mock S3 upload
        httpx_mock.add_response(url=UPLOAD_URL, status_code=204)

        result = api.send_media_message(
            to=[RECIPIENT_ID],
            message_body="Check this photo",
            file_data=b"image-bytes",
            media_type=MediaType.IMAGE_AVIF,
        )
        assert isinstance(result, SendMessageV2Response)
        assert result.signedUploadUrl is not None

        requests = httpx_mock.get_requests()
        assert len(requests) == 2
        # First: Hermes Message/Send
        assert "Message/Send" in str(requests[0].url)
        body = json.loads(requests[0].content)
        assert body["mediaType"] == "ImageAvif"
        assert body["mediaId"] is not None  # auto-generated UUID
        # Second: S3 upload
        assert str(requests[1].url) == UPLOAD_URL

    def test_no_upload_when_server_omits_signed_url(self, httpx_mock, api,
                                                      sample_send_response_dict):
        """If server doesn't return signedUploadUrl, skip upload."""
        httpx_mock.add_response(json=sample_send_response_dict)

        result = api.send_media_message(
            to=[RECIPIENT_ID],
            message_body="Photo",
            file_data=b"data",
            media_type=MediaType.IMAGE_AVIF,
        )
        assert result.signedUploadUrl is None
        # Only one request (no S3 upload)
        assert len(httpx_mock.get_requests()) == 1


# =========================================================================== #
# mark_as_read / mark_as_delivered
# =========================================================================== #


class TestMarkAsRead:
    def test_mark_as_read(self, httpx_mock, api, sample_update_status_dict):
        conv_id = UUID(CONV_ID)
        msg_id = UUID(MSG_ID)
        httpx_mock.add_response(json=sample_update_status_dict)

        result = api.mark_as_read(conv_id, msg_id)
        assert isinstance(result, UpdateMessageStatusResponse)

        req = httpx_mock.get_requests()[0]
        assert req.method == "PUT"
        assert f"Status/Read/{CONV_ID}/{MSG_ID}" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"


class TestMarkAsDelivered:
    def test_mark_as_delivered(self, httpx_mock, api, sample_update_status_dict):
        conv_id = UUID(CONV_ID)
        msg_id = UUID(MSG_ID)
        httpx_mock.add_response(json=sample_update_status_dict)

        result = api.mark_as_delivered(conv_id, msg_id)
        assert isinstance(result, UpdateMessageStatusResponse)

        req = httpx_mock.get_requests()[0]
        assert req.method == "PUT"
        assert f"Status/Delivered/{CONV_ID}/{MSG_ID}" in str(req.url)


# =========================================================================== #
# User info endpoints
# =========================================================================== #


class TestGetCapabilities:
    def test_returns_dict(self, httpx_mock, api):
        httpx_mock.add_response(json={"canSendMedia": True, "maxGroupSize": 20})

        result = api.get_capabilities()
        assert isinstance(result, dict)
        assert result["canSendMedia"] is True

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert "UserInfo/Capabilities" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"


class TestGetBlockedUsers:
    def test_returns_list(self, httpx_mock, api):
        httpx_mock.add_response(json=[{"userId": USER_ID}])

        result = api.get_blocked_users()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_empty(self, httpx_mock, api):
        httpx_mock.add_response(json=[])
        assert api.get_blocked_users() == []


class TestBlockUser:
    def test_sends_correct_body(self, httpx_mock, api):
        httpx_mock.add_response(status_code=200)

        api.block_user(USER_ID)

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert "UserInfo/Block" in str(req.url)
        body = json.loads(req.content)
        assert body["userId"] == USER_ID


class TestUnblockUser:
    def test_sends_correct_body(self, httpx_mock, api):
        httpx_mock.add_response(status_code=200)

        api.unblock_user(USER_ID)

        req = httpx_mock.get_requests()[0]
        assert "UserInfo/Unblock" in str(req.url)
        body = json.loads(req.content)
        assert body["userId"] == USER_ID


# =========================================================================== #
# Token auto-refresh integration
# =========================================================================== #


class TestAutoRefresh:
    def test_auto_refreshes_expired_token(self, httpx_mock, mock_expired_auth,
                                          sample_registration_response):
        # Mock refresh endpoint
        httpx_mock.add_response(
            method="POST",
            url=f"{BASE}/Registration/App/Refresh",
            json=sample_registration_response,
        )
        # Mock the actual API call
        httpx_mock.add_response(
            json={"conversations": [], "lastConversationId": None},
        )

        with HermesAPI(mock_expired_auth) as api:
            result = api.get_conversations()

        assert result.conversations == []
        requests = httpx_mock.get_requests()
        assert any("/Registration/App/Refresh" in str(r.url) for r in requests)


# =========================================================================== #
# get_conversation_members
# =========================================================================== #


class TestGetConversationMembers:
    def test_basic(self, httpx_mock, api, sample_conversation_members_dict):
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(json=sample_conversation_members_dict)

        result = api.get_conversation_members(conv_id)
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], UserInfoModel)
        assert result[0].friendlyName == "Alice"

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert f"Conversation/Members/{CONV_ID}" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"

    def test_empty_list(self, httpx_mock, api):
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(json=[])

        result = api.get_conversation_members(conv_id)
        assert result == []

    def test_server_error(self, httpx_mock, api):
        conv_id = UUID(CONV_ID)
        httpx_mock.add_response(status_code=404)
        with pytest.raises(httpx.HTTPStatusError):
            api.get_conversation_members(conv_id)


# =========================================================================== #
# get_muted_conversations
# =========================================================================== #


class TestGetMutedConversations:
    def test_non_empty(self, httpx_mock, api, sample_muted_conversations_dict):
        httpx_mock.add_response(json=sample_muted_conversations_dict)

        result = api.get_muted_conversations()
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], ConversationMuteDetailModel)
        assert result[0].expires is not None
        assert result[1].expires is None

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert "Conversation/Muted" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"

    def test_empty_list(self, httpx_mock, api):
        httpx_mock.add_response(json=[])
        result = api.get_muted_conversations()
        assert result == []


# =========================================================================== #
# get_message_device_metadata
# =========================================================================== #


class TestGetMessageDeviceMetadata:
    def test_basic(self, httpx_mock, api, sample_device_metadata_dict):
        httpx_mock.add_response(json=sample_device_metadata_dict)

        ids = [SimpleCompoundMessageId(
            messageId=UUID(MSG_ID), conversationId=UUID(CONV_ID),
        )]
        result = api.get_message_device_metadata(ids)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], MessageDeviceMetadataV2)
        assert result[0].deviceMetadata.deviceMessageMetadata[0].imei == 300234063904190

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert "Message/DeviceMetadata" in str(req.url)
        assert req.headers["Api-Version"] == "2.0"
        body = json.loads(req.content)
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["messageId"] == MSG_ID

    def test_empty_response(self, httpx_mock, api):
        httpx_mock.add_response(json=[])

        result = api.get_message_device_metadata([])
        assert result == []


# =========================================================================== #
# update_message_statuses
# =========================================================================== #


class TestUpdateMessageStatuses:
    def test_batch_request(self, httpx_mock, api, sample_batch_status_response_dict):
        httpx_mock.add_response(json=sample_batch_status_response_dict)

        updates = [
            UpdateMessageStatusRequest(
                messageId=UUID(MSG_ID),
                conversationId=UUID(CONV_ID),
                messageStatus=MessageStatus.READ,
            ),
            UpdateMessageStatusRequest(
                messageId=UUID(LAST_MSG_ID),
                conversationId=UUID(CONV_ID),
                messageStatus=MessageStatus.DELIVERED,
            ),
        ]
        result = api.update_message_statuses(updates)
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], UpdateMessageStatusResponse)
        assert result[0].status == MessageStatus.READ

        req = httpx_mock.get_requests()[0]
        assert req.method == "PUT"
        assert "Status/UpdateMessageStatuses" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"
        body = json.loads(req.content)
        assert isinstance(body, list)
        assert len(body) == 2
        assert body[0]["messageStatus"] == "Read"

    def test_empty_list(self, httpx_mock, api):
        httpx_mock.add_response(json=[])
        result = api.update_message_statuses([])
        assert result == []


# =========================================================================== #
# get_updated_statuses
# =========================================================================== #


class TestGetUpdatedStatuses:
    def test_basic(self, httpx_mock, api, sample_updated_statuses_dict):
        httpx_mock.add_response(json=sample_updated_statuses_dict)

        dt = datetime(2025, 1, 15, 10, 0, 0)
        result = api.get_updated_statuses(after_date=dt)
        assert isinstance(result, GetUpdatedStatusesResponse)
        assert len(result.statusReceiptsForMessages) == 1

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert "Status/Updated" in str(req.url)
        assert "AfterDate" in str(req.url)
        assert "Limit=50" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"

    def test_custom_limit(self, httpx_mock, api, sample_updated_statuses_dict):
        httpx_mock.add_response(json=sample_updated_statuses_dict)

        dt = datetime(2025, 1, 1)
        api.get_updated_statuses(after_date=dt, limit=10)

        req = httpx_mock.get_requests()[0]
        assert "Limit=10" in str(req.url)


# =========================================================================== #
# get_network_properties
# =========================================================================== #


class TestGetNetworkProperties:
    def test_basic(self, httpx_mock, api, sample_network_properties_dict):
        httpx_mock.add_response(json=sample_network_properties_dict)

        result = api.get_network_properties()
        assert isinstance(result, NetworkPropertiesResponse)
        assert result.dataConstrained is False
        assert result.enablesPremiumMessaging is True

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert "NetworkInfo/Properties" in str(req.url)
        assert req.headers["Api-Version"] == "1.0"
