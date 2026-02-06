"""Pydantic models for Garmin Hermes API wire format.

All JSON field names match Kotlin property names exactly (no @SerialName overrides).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid5

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

HERMES_USER_NAMESPACE = UUID("65F85187-FAE9-4211-90D9-8F534AFA231B")


def phone_to_hermes_user_id(phone: str) -> str:
    """Derive the Hermes user UUID from a phone number.

    Garmin Messenger maps phone numbers to user identifiers using UUID-v5
    with namespace ``65F85187-FAE9-4211-90D9-8F534AFA231B``.
    """
    return str(uuid5(HERMES_USER_NAMESPACE, phone))


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class DeviceType(str, Enum):
    MESSENGER_APP = "MessengerApp"
    INREACH = "inReach"
    UNKNOWN = "Unknown"
    EXTERNAL = "External"
    GARMIN_OS_APP = "GarminOSApp"


class MessageStatus(str, Enum):
    INITIALIZED = "Initialized"
    PROCESSING = "Processing"
    SENT = "Sent"
    DELIVERED = "Delivered"
    READ = "Read"
    UNDELIVERABLE = "Undeliverable"
    RETRYABLE_ERROR = "RetryableError"
    DELETED = "Deleted"
    EXPIRED = "Expired"
    UNINITIALIZED = "Uninitialized"


class HermesMessageType(str, Enum):
    UNKNOWN = "Unknown"
    MAPSHARE = "MapShare"
    REFERENCE_POINT = "ReferencePoint"


class MediaType(str, Enum):
    IMAGE_AVIF = "ImageAvif"
    AUDIO_OGG = "AudioOgg"


# --------------------------------------------------------------------------- #
# Shared sub-models
# --------------------------------------------------------------------------- #


class UserLocation(BaseModel):
    latitudeDegrees: float | None = None
    longitudeDegrees: float | None = None
    elevationMeters: float | None = None
    groundVelocityMetersPerSecond: float | None = None
    courseDegrees: float | None = None


class StatusReceipt(BaseModel):
    userId: str
    appOrDeviceInstanceId: str | None = None
    deviceType: DeviceType | None = None
    messageStatus: MessageStatus
    updatedAt: datetime | None = None


class SimpleCompoundMessageId(BaseModel):
    messageId: UUID
    conversationId: UUID


class MediaMetadata(BaseModel):
    width: int | None = None
    height: int | None = None
    durationMs: int | None = None


class SignedUploadUrl(BaseModel):
    """AWS S3 presigned upload parameters returned by Message/Send v2."""

    model_config = ConfigDict(populate_by_name=True)

    uploadUrl: str
    key: str | None = None
    # AWS S3 presigned POST fields — wire names use hyphens
    xAmzStorageClass: str | None = Field(
        default=None, alias="x-amz-storage-class",
    )
    xAmzDate: str | None = Field(default=None, alias="x-amz-date")
    xAmzSignature: str | None = Field(default=None, alias="x-amz-signature")
    xAmzAlgorithm: str | None = Field(default=None, alias="x-amz-algorithm")
    xAmzCredential: str | None = Field(default=None, alias="x-amz-credential")
    policy: str | None = None
    xAmzMetaMediaQuality: str | None = Field(
        default=None, alias="x-amz-meta-media-quality",
    )
    contentType: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "content-type", "Content-type", "content-Type", "Content-Type",
        ),
        serialization_alias="content-type",
    )


# --------------------------------------------------------------------------- #
# Message models
# --------------------------------------------------------------------------- #


class MessageModel(BaseModel):
    """Full message as returned by SignalR ReceiveMessage and some REST endpoints."""

    model_config = ConfigDict(populate_by_name=True)

    messageId: UUID
    conversationId: UUID
    parentMessageId: UUID | None = None
    messageBody: str | None = None
    to: list[str] | None = None
    from_: str | None = Field(default=None, alias="from")

    sentAt: datetime | None = None
    receivedAt: datetime | None = None
    status: list[StatusReceipt] | None = None
    userLocation: UserLocation | None = None
    referencePoint: UserLocation | None = None
    messageType: HermesMessageType | None = None
    mapShareUrl: str | None = None
    mapSharePassword: str | None = None
    liveTrackUrl: str | None = None
    fromDeviceType: DeviceType | None = None
    mediaId: UUID | None = None
    mediaType: MediaType | None = None
    mediaMetadata: MediaMetadata | None = None
    uuid: UUID | None = None
    transcription: str | None = None
    otaUuid: UUID | None = None
    fromUnitId: str | None = None
    intendedUnitId: str | None = None


class ConversationMessageModel(BaseModel):
    """Message within a conversation detail response (no conversationId/to/mediaMetadata)."""

    model_config = ConfigDict(populate_by_name=True)

    messageId: UUID
    parentMessageId: UUID | None = None
    messageBody: str | None = None
    from_: str | None = Field(default=None, alias="from")

    sentAt: datetime | None = None
    receivedAt: datetime | None = None
    status: list[StatusReceipt] | None = None
    userLocation: UserLocation | None = None
    referencePoint: UserLocation | None = None
    messageType: HermesMessageType | None = None
    mapShareUrl: str | None = None
    mapSharePassword: str | None = None
    liveTrackUrl: str | None = None
    fromDeviceType: DeviceType | None = None
    mediaId: UUID | None = None
    mediaType: MediaType | None = None
    uuid: UUID | None = None
    transcription: str | None = None
    otaUuid: UUID | None = None
    fromUnitId: str | None = None
    intendedUnitId: str | None = None


# --------------------------------------------------------------------------- #
# Conversation models
# --------------------------------------------------------------------------- #


class ConversationMetaModel(BaseModel):
    conversationId: UUID
    memberIds: list[str]
    updatedDate: datetime
    createdDate: datetime
    isMuted: bool = False
    isPost: bool = False


class ConversationDetailModel(BaseModel):
    metaData: ConversationMetaModel
    messages: list[ConversationMessageModel]
    limit: int
    lastMessageId: UUID | None = None


class GetConversationsModel(BaseModel):
    conversations: list[ConversationMetaModel]
    lastConversationId: UUID | None = None


class UserInfoModel(BaseModel):
    """Member info within a conversation."""
    userIdentifier: str | None = None
    address: str | None = None
    friendlyName: str | None = None
    imageUrl: str | None = None


class ConversationMuteDetailModel(BaseModel):
    """Entry in GET Conversation/Muted response."""
    conversationId: UUID
    expires: datetime | None = None


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #


class SendMessageRequest(BaseModel):
    to: list[str]
    messageBody: str
    userLocation: UserLocation | None = None
    referencePoint: UserLocation | None = None
    messageType: HermesMessageType | None = None
    isPost: bool = False
    mediaId: UUID | None = None
    mediaType: MediaType | None = None
    uuid: UUID | None = None
    otaUuid: UUID | None = None


class SendMessageV2Response(BaseModel):
    messageId: UUID
    conversationId: UUID
    signedUploadUrl: SignedUploadUrl | None = None
    imageQuality: str | None = None


class UpdateMessageStatusResponse(BaseModel):
    messageId: UUID | None = None
    conversationId: UUID | None = None
    status: MessageStatus | None = None


class UpdateMessageStatusRequest(BaseModel):
    """Single item for PUT Status/UpdateMessageStatuses batch request."""
    messageId: UUID
    conversationId: UUID
    messageStatus: MessageStatus


class StatusReceiptsForMessage(BaseModel):
    """Status receipts for a single message in GetUpdatedStatusesResponse."""
    messageId: UUID
    conversationId: UUID
    statusReceipts: list[StatusReceipt] | None = None


class GetUpdatedStatusesResponse(BaseModel):
    """GET Status/Updated — status changes since a date."""
    statusReceiptsForMessages: list[StatusReceiptsForMessage]
    lastMessageId: UUID | None = None


class UpdateMediaRequest(BaseModel):
    """POST Message/UpdateMedia — confirm upload or request new signed URL."""

    mediaType: MediaType
    mediaId: UUID
    messageId: UUID | None = None
    conversationId: UUID | None = None


class UpdateMediaResponse(BaseModel):
    """Response from POST Message/UpdateMedia."""

    signedUploadUrl: SignedUploadUrl
    imageQuality: str | None = None


class MediaAttachmentDownloadUrlResponse(BaseModel):
    """Response from GET Message/Media/DownloadUrl."""

    downloadUrl: str


class InReachMessageMetadata(BaseModel):
    """Satellite message metadata within a device instance."""
    messageId: UUID | None = None
    mtmsn: int | None = None
    text: str | None = None
    otaUuid: UUID | None = None


class DeviceInstanceMetadata(BaseModel):
    """Per-device metadata entry (one physical device)."""
    deviceInstanceId: UUID | None = None
    imei: int | None = None
    inReachMessageMetadata: list[InReachMessageMetadata] | None = None


class DeviceMetadataEntry(BaseModel):
    """Inner deviceMetadata object in the DeviceMetadata response."""
    userId: str | None = None
    messageId: SimpleCompoundMessageId | None = None
    deviceMessageMetadata: list[DeviceInstanceMetadata] | None = None


class MessageDeviceMetadataV2(BaseModel):
    """Top-level item returned by POST Message/DeviceMetadata."""
    hasAllMtDeviceMetadata: bool = False
    deviceMetadata: DeviceMetadataEntry | None = None


class NetworkPropertiesResponse(BaseModel):
    """GET NetworkInfo/Properties response."""
    dataConstrained: bool = False
    enablesPremiumMessaging: bool = False


# --------------------------------------------------------------------------- #
# Auth models
# --------------------------------------------------------------------------- #


class AccessAndRefreshToken(BaseModel):
    accessToken: str
    refreshToken: str
    expiresIn: int  # seconds


class NewAppRegistrationBody(BaseModel):
    smsNumber: str
    platform: str = "android"


class NewAppRegistrationResponse(BaseModel):
    requestId: str
    validUntil: str | None = None
    attemptsRemaining: int | None = None


class OtpRequest(BaseModel):
    """Pending OTP request returned by HermesAuth.request_otp()."""

    request_id: str
    phone_number: str
    device_name: str
    valid_until: str | None = None
    attempts_remaining: int | None = None


class ConfirmAppRegistrationBody(BaseModel):
    requestId: str
    smsNumber: str
    verificationCode: str
    platform: str = "android"
    # FCM registration token format: {instance_id}:APA91b{base64_data} (~163 chars)
    # We don't have Google Play Services, so push won't arrive — SignalR covers real-time.
    pnsHandle: str = (
        "cXr1bp_PSqaKHFG8W4vLHi:APA91bH8kL2xNmQpZ9vYtD5n3R7fUwXoE"
        "jKm4sCgBpV6qI0hA1dWzOyFuN8rT3lMxJvQ2bGnYk9wRcHiP7eDsUaZo"
        "L5fXtW4mBjK0vNq6SyRgCpAhD1iOuE3wTlMx"
    )
    pnsEnvironment: str = "Production"
    appDescription: str = "garmin-messenger"
    optInForSms: bool = True


class SmsOptInResult(BaseModel):
    success: bool | None = None
    fatalError: bool | None = None


class AppRegistrationResponse(BaseModel):
    instanceId: str
    accessAndRefreshToken: AccessAndRefreshToken
    smsOptInResult: SmsOptInResult | None = None


class NewInReachRegistrationUsingSsoResponse(BaseModel):
    instanceId: str
    accessAndRefreshToken: AccessAndRefreshToken


class RefreshAuthBody(BaseModel):
    refreshToken: str
    instanceId: str


# --------------------------------------------------------------------------- #
# SignalR event models
# --------------------------------------------------------------------------- #


class MessageStatusUpdate(BaseModel):
    messageId: SimpleCompoundMessageId
    userId: UUID | None = None
    deviceInstanceId: UUID | None = None
    deviceType: DeviceType | None = None
    messageStatus: MessageStatus | None = Field(
        default=None,
        validation_alias=AliasChoices("messageStatus", "status"),
    )
    updatedAt: datetime | None = None


class ConversationMuteStatusUpdate(BaseModel):
    conversationId: UUID | None = None
    isMuted: bool | None = None


class UserBlockStatusUpdate(BaseModel):
    userId: str | None = None
    isBlocked: bool | None = None


class ServerNotification(BaseModel):
    notificationType: str | None = None
    message: str | None = None
