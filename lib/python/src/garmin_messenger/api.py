"""Hermes REST API client for Garmin Messenger.

All requests go to https://hermes.inreachapp.com/ with an AccessToken header.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime
from uuid import UUID, uuid4

import httpx

from garmin_messenger.auth import HermesAuth
from garmin_messenger.models import (
    ConversationDetailModel,
    ConversationMuteDetailModel,
    GetConversationsModel,
    GetUpdatedStatusesResponse,
    HermesMessageType,
    MediaAttachmentDownloadUrlResponse,
    MediaType,
    MessageDeviceMetadataV2,
    NetworkPropertiesResponse,
    SendMessageRequest,
    SendMessageV2Response,
    SignedUploadUrl,
    SimpleCompoundMessageId,
    UpdateMediaRequest,
    UpdateMediaResponse,
    UpdateMessageStatusRequest,
    UpdateMessageStatusResponse,
    UserInfoModel,
    UserLocation,
)

log = logging.getLogger(__name__)


def _generate_ota_uuid(
    *,
    timestamp: int | None = None,
    group_index: int | None = None,
    fragment_index: int | None = None,
    reserved1: int = 0,
    reserved2: int = 0,
    random_value: int | None = None,
) -> UUID:
    """Generate an OTA UUID using the Garmin app's budget UUID layout."""
    if timestamp is None:
        timestamp = int(time.time())
    timestamp &= 0xFFFFFFFF
    if random_value is None:
        random_value = secrets.randbits(64)
    random_bytes = random_value.to_bytes(8, "big", signed=False)

    raw = bytearray(16)
    raw[6] = 0x80
    raw[8] = 0x80
    raw[14] = 0x80
    raw[0:4] = timestamp.to_bytes(4, "big", signed=False)
    raw[4] = random_bytes[0]
    raw[5] = random_bytes[1]
    raw[7] = random_bytes[2]
    raw[9] = random_bytes[3]
    raw[10] = random_bytes[4]
    raw[11] = random_bytes[5]
    raw[12] = random_bytes[6]
    raw[13] = random_bytes[7]

    if group_index is not None:
        if not 0 <= group_index < 15:
            raise ValueError("group_index must be in range 0..14")
        raw[6] |= (group_index + 1) & 0x0F
    if fragment_index is not None:
        if not 0 <= fragment_index < 31:
            raise ValueError("fragment_index must be in range 0..30")
        raw[8] |= (fragment_index + 1) & 0x1F
    if reserved1 not in (0, 1):
        raise ValueError("reserved1 must be 0 or 1")
    raw[8] |= (reserved1 & 1) << 5
    if not 0 <= reserved2 < (1 << 14):
        raise ValueError("reserved2 must be in range 0..16383")
    raw[14] |= (reserved2 >> 8) & 0x3F
    raw[15] |= reserved2 & 0xFF

    return UUID(bytes=bytes(raw))


class HermesAPI:
    """Synchronous Hermes REST API client backed by httpx."""

    def __init__(self, auth: HermesAuth, timeout: float = 30.0):
        self.auth = auth
        self.base_url = auth.hermes_base
        self._client = httpx.Client(timeout=timeout)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ----- conversations -----------------------------------------------------

    def get_conversations(
        self,
        *,
        after_date: datetime | None = None,
        limit: int = 50,
    ) -> GetConversationsModel:
        """GET Conversation/Updated — list conversations updated after a date."""
        params: dict = {"Limit": limit}
        if after_date is not None:
            params["AfterDate"] = after_date.isoformat()
        resp = self._get("Conversation/Updated", params=params, api_version="1.0")
        return GetConversationsModel.model_validate(resp.json())

    def get_conversation_detail(
        self,
        conversation_id: UUID,
        *,
        limit: int = 50,
        older_than_id: UUID | None = None,
        newer_than_id: UUID | None = None,
    ) -> ConversationDetailModel:
        """GET Conversation/Details/{id} — messages in a conversation."""
        params: dict = {"Limit": limit}
        if older_than_id:
            params["olderThanId"] = str(older_than_id)
        if newer_than_id:
            params["newerThanId"] = str(newer_than_id)
        resp = self._get(
            f"Conversation/Details/{conversation_id}",
            params=params,
            api_version="2.0",
        )
        return ConversationDetailModel.model_validate(resp.json())

    def mute_conversation(self, conversation_id: UUID, *, muted: bool = True) -> None:
        """POST Conversation/{id}/Mute or Unmute."""
        action = "Mute" if muted else "Unmute"
        if muted:
            self._post(
                f"Conversation/{conversation_id}/{action}",
                json={"isMuted": True},
                api_version="1.0",
            )
        else:
            self._post(
                f"Conversation/{conversation_id}/{action}",
                api_version="1.0",
            )

    def get_conversation_members(
        self,
        conversation_id: UUID,
    ) -> list[UserInfoModel]:
        """GET Conversation/Members/{conversationId} — member details."""
        resp = self._get(
            f"Conversation/Members/{conversation_id}",
            api_version="1.0",
        )
        return [UserInfoModel.model_validate(m) for m in resp.json()]

    def get_muted_conversations(self) -> list[ConversationMuteDetailModel]:
        """GET Conversation/Muted — list muted conversations with expiry."""
        resp = self._get("Conversation/Muted", api_version="1.0")
        return [ConversationMuteDetailModel.model_validate(c) for c in resp.json()]

    # ----- messages ----------------------------------------------------------

    def send_message(
        self,
        to: list[str],
        message_body: str,
        *,
        user_location: UserLocation | None = None,
        reference_point: UserLocation | None = None,
        message_type: HermesMessageType | None = None,
        is_post: bool = False,
        media_id: UUID | None = None,
        media_type: MediaType | None = None,
    ) -> SendMessageV2Response:
        """POST Message/Send (API v2) — send a message to one or more recipients."""
        req = SendMessageRequest(
            to=to,
            messageBody=message_body,
            userLocation=user_location,
            referencePoint=reference_point,
            messageType=message_type,
            isPost=is_post,
            mediaId=media_id,
            mediaType=media_type,
            uuid=uuid4(),
            otaUuid=_generate_ota_uuid(),
        )
        # Android app always serializes userLocation/referencePoint as null;
        # server rejects requests with those fields missing entirely.
        resp = self._post(
            "Message/Send",
            json=req.model_dump(mode="json"),
            api_version="2.0",
        )
        return SendMessageV2Response.model_validate(resp.json())

    # ----- media attachments -------------------------------------------------

    def upload_media(
        self,
        signed_url: SignedUploadUrl,
        file_data: bytes,
    ) -> None:
        """Upload media to S3 using a presigned POST from Hermes.

        Args:
            signed_url: SignedUploadUrl from SendMessageV2Response or UpdateMediaResponse.
            file_data: Raw file bytes to upload.
        """
        fields: dict[str, str] = {}
        if signed_url.key is not None:
            fields["key"] = signed_url.key
        if signed_url.xAmzStorageClass is not None:
            fields["x-amz-storage-class"] = signed_url.xAmzStorageClass
        if signed_url.xAmzDate is not None:
            fields["x-amz-date"] = signed_url.xAmzDate
        if signed_url.xAmzSignature is not None:
            fields["x-amz-signature"] = signed_url.xAmzSignature
        if signed_url.xAmzAlgorithm is not None:
            fields["x-amz-algorithm"] = signed_url.xAmzAlgorithm
        if signed_url.xAmzCredential is not None:
            fields["x-amz-credential"] = signed_url.xAmzCredential
        if signed_url.policy is not None:
            fields["policy"] = signed_url.policy
        if signed_url.xAmzMetaMediaQuality is not None:
            fields["x-amz-meta-media-quality"] = signed_url.xAmzMetaMediaQuality
        if signed_url.contentType is not None:
            fields["Content-Type"] = signed_url.contentType

        # S3 presigned POST: fields as form data, file as "file" part
        content_type = signed_url.contentType or "application/octet-stream"
        files = {"file": ("attachment", file_data, content_type)}
        log.debug("S3 POST %s fields=%s", signed_url.uploadUrl, list(fields.keys()))
        resp = self._client.post(signed_url.uploadUrl, data=fields, files=files)
        if not resp.is_success:
            log.error(
                "S3 upload → %d: %s", resp.status_code, resp.text[:500],
            )
        resp.raise_for_status()

    def get_media_download_url(
        self,
        *,
        uuid: UUID,
        media_type: MediaType,
        media_id: UUID,
        message_id: UUID,
        conversation_id: UUID,
    ) -> MediaAttachmentDownloadUrlResponse:
        """GET Message/Media/DownloadUrl — get a presigned S3 download URL."""
        params = {
            "uuid": str(uuid),
            "mediaType": media_type.value,
            "mediaId": str(media_id),
            "messageId": str(message_id),
            "conversationId": str(conversation_id),
        }
        resp = self._get("Message/Media/DownloadUrl", params=params, api_version="2.0")
        return MediaAttachmentDownloadUrlResponse.model_validate(resp.json())

    def download_media(
        self,
        *,
        uuid: UUID,
        media_type: MediaType,
        media_id: UUID,
        message_id: UUID,
        conversation_id: UUID,
    ) -> bytes:
        """Download a media attachment — fetches the presigned URL then downloads.

        Returns the raw file bytes.
        """
        url_resp = self.get_media_download_url(
            uuid=uuid,
            media_type=media_type,
            media_id=media_id,
            message_id=message_id,
            conversation_id=conversation_id,
        )
        log.debug("Downloading media from %s", url_resp.url[:80])
        resp = self._client.get(url_resp.url)
        resp.raise_for_status()
        return resp.content

    def update_media(
        self,
        *,
        media_type: MediaType,
        media_id: UUID,
        message_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> UpdateMediaResponse:
        """POST Message/UpdateMedia — confirm upload or request new signed URL."""
        req = UpdateMediaRequest(
            mediaType=media_type,
            mediaId=media_id,
            messageId=message_id,
            conversationId=conversation_id,
        )
        resp = self._post(
            "Message/UpdateMedia",
            json=req.model_dump(mode="json"),
            api_version="2.0",
        )
        return UpdateMediaResponse.model_validate(resp.json())

    def send_media_message(
        self,
        to: list[str],
        message_body: str,
        file_data: bytes,
        media_type: MediaType,
        *,
        user_location: UserLocation | None = None,
        reference_point: UserLocation | None = None,
        is_post: bool = False,
    ) -> SendMessageV2Response:
        """Send a message with a media attachment (convenience method).

        Combines send_message (with mediaId) + S3 upload in one call.
        Returns the SendMessageV2Response from the initial send.
        """
        media_id = uuid4()
        result = self.send_message(
            to=to,
            message_body=message_body,
            user_location=user_location,
            reference_point=reference_point,
            is_post=is_post,
            media_id=media_id,
            media_type=media_type,
        )
        if result.signedUploadUrl:
            self.upload_media(result.signedUploadUrl, file_data)
        else:
            log.warning(
                "Server did not return signedUploadUrl for media message %s",
                result.messageId,
            )
        return result

    def get_message_device_metadata(
        self,
        message_ids: list[SimpleCompoundMessageId],
    ) -> list[MessageDeviceMetadataV2]:
        """POST Message/DeviceMetadata — get satellite device metadata."""
        resp = self._post(
            "Message/DeviceMetadata",
            json=[m.model_dump(mode="json") for m in message_ids],
            api_version="2.0",
        )
        return [MessageDeviceMetadataV2.model_validate(r) for r in resp.json()]

    # ----- status updates ----------------------------------------------------

    def mark_as_read(
        self, conversation_id: UUID, message_id: UUID
    ) -> UpdateMessageStatusResponse:
        """PUT Status/Read/{conversationId}/{messageId}."""
        resp = self._put(
            f"Status/Read/{conversation_id}/{message_id}",
            api_version="1.0",
        )
        return UpdateMessageStatusResponse.model_validate(resp.json())

    def mark_as_delivered(
        self, conversation_id: UUID, message_id: UUID
    ) -> UpdateMessageStatusResponse:
        """PUT Status/Delivered/{conversationId}/{messageId}."""
        resp = self._put(
            f"Status/Delivered/{conversation_id}/{message_id}",
            api_version="1.0",
        )
        return UpdateMessageStatusResponse.model_validate(resp.json())

    def update_message_statuses(
        self,
        updates: list[UpdateMessageStatusRequest],
    ) -> list[UpdateMessageStatusResponse]:
        """PUT Status/UpdateMessageStatuses — batch status update."""
        resp = self._put(
            "Status/UpdateMessageStatuses",
            json=[u.model_dump(mode="json") for u in updates],
            api_version="1.0",
        )
        return [UpdateMessageStatusResponse.model_validate(r) for r in resp.json()]

    def get_updated_statuses(
        self,
        *,
        after_date: datetime,
        limit: int = 50,
    ) -> GetUpdatedStatusesResponse:
        """GET Status/Updated — status changes since a date."""
        params = {"AfterDate": after_date.isoformat(), "Limit": limit}
        resp = self._get("Status/Updated", params=params, api_version="1.0")
        return GetUpdatedStatusesResponse.model_validate(resp.json())

    # ----- user info ---------------------------------------------------------

    def get_capabilities(self) -> dict:
        """GET UserInfo/Capabilities."""
        resp = self._get("UserInfo/Capabilities", api_version="1.0")
        return resp.json()

    def get_blocked_users(self) -> list[dict]:
        """GET UserInfo/BlockedUsers."""
        resp = self._get("UserInfo/BlockedUsers", api_version="1.0")
        return resp.json()

    def block_user(self, user_id: str) -> None:
        """POST UserInfo/Block."""
        self._post(
            "UserInfo/Block",
            json={"userId": user_id},
            api_version="1.0",
        )

    def unblock_user(self, user_id: str) -> None:
        """POST UserInfo/Unblock."""
        self._post(
            "UserInfo/Unblock",
            json={"userId": user_id},
            api_version="1.0",
        )

    # ----- network info ------------------------------------------------------

    def get_network_properties(self) -> NetworkPropertiesResponse:
        """GET NetworkInfo/Properties — network status flags."""
        resp = self._get("NetworkInfo/Properties", api_version="1.0")
        return NetworkPropertiesResponse.model_validate(resp.json())

    # ----- internal HTTP helpers ---------------------------------------------

    def _headers(self, api_version: str = "2.0") -> dict[str, str]:
        h = self.auth.headers()
        h["Api-Version"] = api_version
        return h

    def _get(
        self,
        path: str,
        *,
        params: dict | None = None,
        api_version: str = "2.0",
    ) -> httpx.Response:
        url = f"{self.base_url}/{path}"
        log.debug("GET %s params=%s", url, params)
        resp = self._client.get(url, headers=self._headers(api_version), params=params)
        log.debug("GET %s → %d (%d bytes)", url, resp.status_code, len(resp.content))
        log.debug("  Response body: %s", resp.text[:2000])
        if not resp.is_success:
            log.error("GET %s → %d: %s", url, resp.status_code, resp.text)
        resp.raise_for_status()
        return resp

    def _post(
        self,
        path: str,
        *,
        json: dict | list | None = None,
        api_version: str = "2.0",
    ) -> httpx.Response:
        url = f"{self.base_url}/{path}"
        log.debug("POST %s body=%s", url, json)
        resp = self._client.post(url, headers=self._headers(api_version), json=json)
        log.debug("POST %s → %d (%d bytes)", url, resp.status_code, len(resp.content))
        log.debug("  Response body: %s", resp.text[:2000])
        if not resp.is_success:
            log.error("POST %s → %d: %s", url, resp.status_code, resp.text)
        resp.raise_for_status()
        return resp

    def _put(
        self,
        path: str,
        *,
        json: dict | list | None = None,
        api_version: str = "2.0",
    ) -> httpx.Response:
        url = f"{self.base_url}/{path}"
        log.debug("PUT %s body=%s", url, json)
        resp = self._client.put(url, headers=self._headers(api_version), json=json)
        log.debug("PUT %s → %d (%d bytes)", url, resp.status_code, len(resp.content))
        log.debug("  Response body: %s", resp.text[:2000])
        if not resp.is_success:
            log.error("PUT %s → %d: %s", url, resp.status_code, resp.text)
        resp.raise_for_status()
        return resp
