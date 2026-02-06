# Garmin Messenger API Reference

**Scope**: App-to-server communication only — sending and receiving messages to/from other Garmin Messenger users via the Hermes REST API and SignalR WebSocket. Device-to-phone communication (Bluetooth/protobuf/GFDI) is out of scope.

---

## Table of Contents

1. [Service Map](#1-service-map)
2. [Authentication Flow](#2-authentication-flow)
3. [Hermes REST API](#3-hermes-rest-api)
4. [SignalR Real-Time Layer](#4-signalr-real-time-layer)
5. [Media Attachments](#5-media-attachments)
6. [Open Questions](#6-open-questions)

---

## 1. Service Map

Relevant services for app-to-server messaging:

| Service | Production URL | Test URL | Purpose |
|---------|---------------|----------|---------|
| **Hermes** | `hermes.inreachapp.com` | `test-hermes.inreachapp.com` | Core messaging REST API + SignalR WebSocket |
| **SSO** | `sso.garmin.com` | `ssotest.garmin.com` | User login (Single Sign-On) |
| **DI-OAuth2** | `diauth.garmin.com/di-oauth2-service/` | `diauthtest.garmin.com/di-oauth2-service/` | OAuth2 token exchange |
| **Media Storage** | `s3.amazonaws.com/certus-media-manager-prod/` | — | Media attachments (S3 presigned URLs) |

Hermes supports multiple environments: Production, Test, and Dev.

---

## 2. Authentication Flow

### Overview

The app supports two authentication paths:

**Path A: AccountManager** (primary — requires Garmin Connect app on device):
```
Android AccountManager → subject_token exchange → requestToken → sso/login → service_ticket exchange → Registration/SSO
```

**Path B: WebView SSO** (fallback — standalone, no other Garmin app needed):
```
SSO WebView login → CAS ticket → service_ticket exchange → Registration/SSO
```

Our Python client implements **Path B** (we don't have Android AccountManager).

---

### Path A: AccountManager Flow (for reference)

Used when an existing `com.garmin.di` / `GARMIN` account exists in Android AccountManager
(populated by Garmin Connect app).

1. Read OAuth2 token from AccountManager
2. **Subject token exchange**: token → MESSENGER_MOBILE_ANDROID_DI token
3. POST `sso/requestToken` with Messenger token → `logintoken`
4. GET `sso/login?logintoken=...&service=https://hermes.inreachapp.com/` → HTML with CAS `serviceTicket`
5. **Service ticket exchange**: CAS ticket → SSO DI-OAuth2 token
6. POST `Registration/SSO/{imei}` with SSO DI token → Hermes JWT

> **Note**: The subject_token exchange (step 2) requires a DI-OAuth2 token obtained from
> `diauth.garmin.com` directly. Tokens from the legacy `connectapi.garmin.com/oauth-service/oauth/exchange/user/2.0`
> endpoint (e.g., from the `garth` library) are **rejected** with "The provided IT Access Token is invalid."

---

### Path B: WebView SSO Flow (what we implement)

Used when no existing Garmin account is found. The app opens an SSO
sign-in widget in a WebView.

#### Step 1: SSO Login

**WebView URL**:
```
https://sso.garmin.com/sso/embed?
  clientId=MESSENGER_MOBILE_ANDROID
  &locale=en_US
  &redirectAfterAccountLoginUrl=https://sso.garmin.com/sso/embed
  &createAccountShown=false
  &socialEnabled=false
  &reauth=true
  &mobile=true
  &cssUrl=https://exploreapp.azureedge.net/css/messenger-sso.css
  &openCreateAccount=false
```

User authenticates. SSO redirects to:
```
https://sso.garmin.com/sso/embed?ticket=ST-xxxxxx-xxxxx-cas
```

The WebViewClient intercepts the redirect, extracts the `ticket` query parameter, and
rebuilds the service URL (scheme + authority + path, no query params) → `https://sso.garmin.com/sso/embed`.

**Python equivalent**: Use `garth.login()` to establish SSO session (CASTGC cookie), then:
```
GET sso.garmin.com/sso/login?service=https://sso.garmin.com/sso/embed
  (with garth's session cookies, allow_redirects=False)
  → 302 Location: https://sso.garmin.com/sso/embed?ticket=ST-xxxx
```

#### Step 2: DI-OAuth2 Service Ticket Exchange

```
POST https://diauth.garmin.com/di-oauth2-service/oauth/token
  Headers:
    Content-Type: application/x-www-form-urlencoded
    Accept-Encoding: en_US          (intentional — app sends locale here)
    Accept-Charset: UTF-8
  Form fields:
    client_id=MESSENGER_MOBILE_ANDROID_DI
    service_ticket={CAS ticket from Step 1}
    service_url=https://sso.garmin.com/sso/embed
    grant_type=https://connectapi.garmin.com/di-oauth2-service/oauth/grant/service_ticket
```

Response: `DiOAuth2TokenExchangeResponse`:
```json
{"access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600,
 "refresh_token": "...", "scope": "..."}
```

#### Step 3: Hermes SSO Registration

```
POST https://hermes.inreachapp.com/Registration/SSO/{imei}
  Headers:
    AccessToken: {DI-OAuth2 token from Step 2}
    ssoBearerToken: {DI-OAuth2 token from Step 2}    (same value)
    Api-Version: 1.0
```

The `{imei}` path parameter identifies the InReach device being registered. See
[IMEI Serialization](#imei-serialization) below for format details.

Response: `NewInReachRegistrationUsingSsoResponse`:
```json
{"instanceId": "...", "accessAndRefreshToken": {"accessToken": "...", "refreshToken": "...", "expiresIn": 3600}}
```

The `accessToken` is the final Hermes JWT (ES256 algorithm).

> **Warning**: This endpoint is designed for registering a physical InReach device.
> Using a fake/placeholder IMEI (e.g. all zeros) may work but is untested.
> For phone-only registration, see [SMS Registration](#sms-registration-new-users-without-sso) below.

---

### DI-OAuth2 Interface

All three grant types POST to `oauth/token` with identical headers:

| Grant Type | Fields | Purpose |
|-----------|--------|---------|
| `urn:ietf:params:oauth:grant-type:token-exchange` | client_id, subject_token, subject_token_type, grant_type | Exchange AccountManager token → Messenger token |
| `https://connectapi.garmin.com/di-oauth2-service/oauth/grant/service_ticket` | client_id, service_ticket, service_url, grant_type | Exchange CAS ticket → DI-OAuth2 token |
| (standard refresh) | client_id, refresh_token, grant_type | Refresh DI-OAuth2 token |

---

### IMEI Serialization

The `{imei}` path parameter in `Registration/SSO/{imei}` and `Registration/inReach/{imei}`
is an InReach device IMEI (satellite modem identifier, typically 15 digits like `300234063904190`).

**Serialization**: The IMEI is serialized as a decimal string, left-padded with `'0'` to a minimum of **15 characters**.

Example: IMEI `300234063904190` → `"300234063904190"` in the URL path.

### Registration Paths — Choosing the Right One

The Hermes API has three distinct registration paths:

| Path | Endpoint | Auth | Identifier | Use Case |
|------|----------|------|------------|----------|
| **SSO + Device** | `POST Registration/SSO/{imei}` | `AccessToken` + `ssoBearerToken` (DI-OAuth2) | 15-digit InReach IMEI | User with physical InReach device, authenticated via SSO |
| **SMS + Phone** | `POST Registration/App` → `Confirm` | `RegistrationApiKey` | SMS phone number | Phone-only user, no InReach device, verified via SMS OTP |
| **Token Refresh** | `POST Registration/App/Refresh` | None (body auth) | `instanceId` from prior registration | Renewing an expired access token |

**SSO path** (`Registration/SSO/{imei}`):
- Requires a real InReach device IMEI (15-digit satellite modem ID)
- The IMEI comes from a connected Bluetooth InReach device (15-digit satellite modem ID)

**SMS path** (`Registration/App`):
- No IMEI needed — identifies user by phone number
- Two-step: initiate → receive SMS OTP → confirm
- Body: `{"smsNumber": "+1234567890", "platform": "android"}`
- Returns `requestId`, then confirm with `verificationCode`
- The `RegistrationApiKey` header value for initial registration is unknown (may be static/empty)

**For a standalone Python client without an InReach device**, the SMS path is architecturally correct.
The SSO path with a fake IMEI may work if the server doesn't validate IMEIs, but this is untested.

---

### Path A (AccountManager) — Additional Endpoints

These are only used in Path A, not Path B:

**SSO requestToken**:
```
POST sso.garmin.com/sso/requestToken
  Content-Type: application/x-www-form-urlencoded
  Headers: Connection: Keep-Alive, Cache-Control: no-cache,
           User-Agent: com.garmin.android.apps.messenger-Android-1.0
  Form fields:
    version=1
    accesstoken={Messenger DI-OAuth2 token}
    customerGUID={garminGUID from /userprofile-service/socialProfile}
    appid=com.garmin.android.apps.messenger
    service=https://hermes.inreachapp.com/
    mfaToken=
  Response: {"logintoken": "...", "username": "...", "service": "..."}
```

**SSO login**:
```
GET sso.garmin.com/sso/login?logintoken={...}&service=https://hermes.inreachapp.com/
  Response: HTML page with embedded JS object (single quotes):
    {serviceUrl:'https://hermes.inreachapp.com/', serviceTicket:'ST-...'}
  Parse: regex {serviceUrl:[^}]+}, replace ' → ", JSON parse
```

---

### Hermes Registration — Other Paths

#### SMS Registration (new users without SSO)
```
POST Registration/App                    → NewAppRegistrationResponse {requestId, validUntil, attemptsRemaining}
  Headers: RegistrationApiKey: {apiKey}
  Body: {smsNumber: "+1234567890", platform: "android"}

[User receives SMS OTP]

POST Registration/App/Confirm            → AppRegistrationResponse {instanceId, accessAndRefreshToken}
  Headers: RegistrationApiKey: {apiKey}
  Body: {requestId, smsNumber, verificationCode, platform: "android",
         pnsHandle: "{FCM token}", pnsEnvironment: "Production", appDescription, optInForSms}
  NOTE: pnsEnvironment = "Production" (PascalCase). "Default" and "fcm" are WRONG (rejected by .NET enum).
```

> **RegistrationApiKey**: For authenticated requests, this header receives the existing Hermes access token. For initial SMS registration (when no existing token exists), this may be a static/well-known key or empty.

### Token Refresh (all paths)
```
POST Registration/App/Refresh            → AppRegistrationResponse {instanceId, accessAndRefreshToken}
  Headers: Api-Version: 1.0
  Body: {refreshToken, instanceId}
```

### AccessAndRefreshToken Structure
```json
{
  "accessToken": "eyJ...",      // JWT (ES256)
  "refreshToken": "...",
  "expiresIn": 3600
}
```

> **Note**: Field is `expiresIn` (not `expiresInSeconds`). No `@SerialName` overrides — all JSON field names match Kotlin property names exactly.

### JWT Structure

**Header**: `{alg: "ES256", kid: "..."}`

**Hermes JWT Payload** (`JwtDecoder$KSerialHermesJwtDecoder$SerializableJwtAuthPayload`):
```
sub: String                    // subject (user ID)
iss: String?                   // issuer
aud: List<String>?             // audience
iat: Long?                     // issued at
exp: Long?                     // expiration
token_use: String?
auth_time: Long?
preferred_username: String?
scope: List<String>?
hermes: {appInstanceId, userId}  // Hermes-specific claims
act: {actor}?                    // delegation/actor info
```

---

## 3. Hermes REST API

**Base URL**: `https://hermes.inreachapp.com/`
**Auth Header**: `AccessToken: {jwt}` (custom header, NOT `Authorization: Bearer`)
**API Version Header**: `Api-Version: 1.0` or `Api-Version: 2.0`
**Serialization**: JSON

### Registration Endpoints

| Method | Path | Request | Response | API Ver |
|--------|------|---------|----------|---------|
| POST | `Registration/App` | `NewAppRegistrationBody` | `NewAppRegistrationResponse` | 1.0 |
| POST | `Registration/App/Confirm` | `ConfirmAppRegistrationBody` | `AppRegistrationResponse` | 1.0 |
| POST | `Registration/App/Reconfirm` | `ReconfirmAppRegistrationBody` | `AppRegistrationResponse` | 1.0 |
| POST | `Registration/App/Refresh` | `RefreshAuthBody` | `AppRegistrationResponse` | 1.0 |
| POST | `Registration/SSO/{imei}` | Headers: AccessToken, ssoBearerToken | `NewInReachRegistrationUsingSsoResponse` | 1.0 |
| GET | `Registration` | — | `GetRegistrationDetailsResponse` | 1.0 |
| DELETE | `Registration/User` | — | void | 1.0 |
| DELETE | `Registration/App/{instanceId}` | — | void | 1.0 |
| PATCH | `Registration/App` | `UpdateAppPnsHandleBody` | void | 1.0 |

### Conversation Endpoints

| Method | Path | Request | Response | API Ver |
|--------|------|---------|----------|---------|
| GET | `Conversation/Updated` | Query: AfterDate, Limit | `GetConversationsModel` | 1.0 |
| GET | `Conversation/Details/{conversationId}` | Query: olderThanId, Limit, newerThanId | `ConversationDetailModel` | 2.0 |
| GET | `Conversation/Members/{conversationId}` | — | `ConversationMembers` (type `a`) | 1.0 |
| GET | `Conversation/Muted` | — | `List<ConversationMuteDetailModel>` | 1.0 |
| POST | `Conversation/{conversationId}/Mute` | `ConversationMuteBody` | void | 1.0 |
| POST | `Conversation/{conversationId}/Unmute` | — | void | 1.0 |

### Message Endpoints

| Method | Path | Request | Response | API Ver |
|--------|------|---------|----------|---------|
| POST | `Message/Send` | `SendMessageRequest` | `SimpleCompoundMessageId` | 1.0 |
| POST | `Message/Send` | `SendMessageRequest` | `SendMessageV2Response` | **2.0** |
| POST | `Message/DeviceMetadata` | `List<SimpleCompoundMessageId>` | `List<MessageDeviceMetadataV2Json>` | 2.0 |
| POST | `Message/UpdateMedia` | `UpdateMediaRequest` | `UpdateMediaResponse` | 2.0 |
| GET | `Message/Media/DownloadUrl` | Query: uuid, mediaType, mediaId, messageId, conversationId | `MediaAttachmentDownloadUrlResponse` | 2.0 |

### Status Endpoints

| Method | Path | Request | Response | API Ver |
|--------|------|---------|----------|---------|
| PUT | `Status/Read/{conversationId}/{messageId}` | — | `UpdateMessageStatusResponseJson` | 1.0 |
| PUT | `Status/Delivered/{conversationId}/{messageId}` | — | `UpdateMessageStatusResponseJson` | 1.0 |
| PUT | `Status/UpdateMessageStatuses` | `List<UpdateMessageStatusRequest>` | `List<UpdateMessageStatusResponseJson>` | 1.0 |
| GET | `Status/Updated` | Query: AfterDate, Limit | `GetUpdatedStatusesResponse` | 1.0 |

### User Info Endpoints

| Method | Path | Request | Response | API Ver |
|--------|------|---------|----------|---------|
| GET | `UserInfo/Capabilities` | — | `UserCapabilitiesResponse` | 1.0 |
| GET | `UserInfo/BlockedUsers` | — | `List<BlockedUser>` | 1.0 |
| GET | `UserInfo/GetSmsOptInStatus` | — | `SmsOptInStatusJson` | 1.0 |
| GET | `UserInfo/GetSmsNotificationPreferences` | — | `SmsNotificationPreferencesJson` | 1.0 |
| POST | `UserInfo/Block` | `BlockUnblockBody` | void | 1.0 |
| POST | `UserInfo/Unblock` | `BlockUnblockBody` | void | 1.0 |
| POST | `UserInfo/OptInForSms` | — | `ResultResponseJson` | 1.0 |
| POST | `UserInfo/SetSmsNotificationPreferences` | `SmsNotificationPreferencesJson` | void | 1.0 |
| POST | `UserInfo/RegisteredUsersByUserIds` | `List<yb9>` | `List<RegisteredUserWithIdentifier>` | 1.0 |

### Network Info Endpoint

| Method | Path | Request | Response | API Ver |
|--------|------|---------|----------|---------|
| GET | `NetworkInfo/Properties` | — | `NetworkPropertiesResponse` | 1.0 |

### Data Models

> **Note on field names**: All JSON field names match Kotlin property names exactly.

#### Enums

**DeviceType**:
```
MESSENGER_APP, INREACH, UNKNOWN, EXTERNAL, GARMIN_OS_APP
```

**MessageStatus**:
```
INITIALIZED, PROCESSING, SENT, DELIVERED, READ, UNDELIVERABLE,
RETRYABLEERROR, DELETED, EXPIRED, UNINITIALIZED
```

**HermesMessageType** (called `MessageType` in wire format):
```
UNKNOWN, MAPSHARE, REFERENCE_POINT
```

**MediaType**:
```
ImageAvif, AudioOgg
```

#### Core Message Models

**MessageModel** (24 fields):
```json
{
  "messageId": "uuid",
  "conversationId": "uuid",
  "parentMessageId": "uuid?",
  "messageBody": "string",
  "to": ["string"],
  "from": "string",
  "sentAt": "datetime",
  "receivedAt": "datetime?",
  "status": [StatusReceipt],
  "userLocation": UserLocation?,
  "referencePoint": UserLocation?,
  "messageType": "HermesMessageType?",
  "mapShareUrl": "string?",
  "mapSharePassword": "string?",
  "liveTrackUrl": "string?",
  "fromDeviceType": "DeviceType?",
  "mediaId": "uuid?",
  "mediaType": "MediaType?",
  "mediaMetadata": MediaMetadata?,
  "uuid": "uuid?",
  "transcription": "string?",
  "otaUuid": "uuid?",
  "fromUnitId": "string?",
  "intendedUnitId": "string?"
}
```

**ConversationMessageModel** (21 fields — same as MessageModel minus `conversationId`, `to`, `mediaMetadata`):
```json
{
  "messageId": "uuid",
  "parentMessageId": "uuid?",
  "messageBody": "string",
  "from": "string",
  "sentAt": "datetime",
  "receivedAt": "datetime?",
  "status": [StatusReceipt],
  "userLocation": UserLocation?,
  "referencePoint": UserLocation?,
  "messageType": "HermesMessageType?",
  "mapShareUrl": "string?",
  "mapSharePassword": "string?",
  "liveTrackUrl": "string?",
  "fromDeviceType": "DeviceType?",
  "mediaId": "uuid?",
  "mediaType": "MediaType?",
  "uuid": "uuid?",
  "transcription": "string?",
  "otaUuid": "uuid?",
  "fromUnitId": "string?",
  "intendedUnitId": "string?"
}
```

**StatusReceipt** (5 fields):
```json
{
  "userId": "string",
  "appOrDeviceInstanceId": "string?",
  "deviceType": "DeviceType?",
  "messageStatus": "MessageStatus",
  "updatedAt": "datetime?"
}
```

**MediaMetadata**:
```json
{
  "width": "int?",
  "height": "int?",
  "durationMs": "long?"
}
```

**UserLocation**:
```json
{
  "latitudeDegrees": "double?",
  "longitudeDegrees": "double?",
  "elevationMeters": "float?",
  "groundVelocityMetersPerSecond": "float?",
  "courseDegrees": "float?"
}
```

#### Conversation Models

**ConversationMetaModel** (6 fields):
```json
{
  "conversationId": "uuid",
  "memberIds": ["string"],
  "updatedDate": "datetime",
  "createdDate": "datetime",
  "isMuted": "boolean",
  "isPost": "boolean"
}
```

**ConversationDetailModel**:
```json
{
  "metadata": ConversationMetaModel,
  "messages": [ConversationMessageModel],
  "limit": "int",
  "lastMessageId": "uuid?"
}
```

**GetConversationsModel**:
```json
{
  "conversations": [ConversationMetaModel],
  "lastConversationId": "uuid?"
}
```

#### Status Models

**UpdateMessageStatusRequest** (single item for batch status update):
```json
{
  "messageId": "uuid",
  "conversationId": "uuid",
  "messageStatus": "MessageStatus"
}
```

**StatusReceiptsForMessage**:
```json
{
  "messageId": "uuid",
  "conversationId": "uuid",
  "statusReceipts": [StatusReceipt]?
}
```

**GetUpdatedStatusesResponse**:
```json
{
  "statusReceiptsForMessages": [StatusReceiptsForMessage],
  "lastMessageId": "uuid?"
}
```

#### Member / Mute Models

**UserInfoModel** (member info within a conversation):
```json
{
  "userIdentifier": "string?",
  "address": "string?",
  "friendlyName": "string?",
  "imageUrl": "string?"
}
```

> **Note**: `GET Conversation/Members/{conversationId}` returns a plain JSON array `[UserInfoModel]`, not a wrapper object.

**ConversationMuteDetailModel**:
```json
{
  "conversationId": "uuid",
  "expires": "datetime?"
}
```

#### Device Metadata / Network Models

**MessageDeviceMetadataV2** (top-level response item from `POST Message/DeviceMetadata`):
```json
{
  "hasAllMtDeviceMetadata": "boolean",
  "deviceMetadata": "DeviceMetadataEntry"
}
```

**DeviceMetadataEntry**:
```json
{
  "userId": "string?",
  "messageId": "SimpleCompoundMessageId?",
  "deviceMessageMetadata": "[DeviceInstanceMetadata]?"
}
```

**DeviceInstanceMetadata** (one physical device):
```json
{
  "deviceInstanceId": "uuid?",
  "imei": "long?",
  "inReachMessageMetadata": "[InReachMessageMetadata]?"
}
```

**InReachMessageMetadata** (satellite message details):
```json
{
  "messageId": "uuid?",
  "mtmsn": "long?",
  "text": "string?",
  "otaUuid": "uuid?"
}
```

**NetworkPropertiesResponse**:
```json
{
  "dataConstrained": "boolean",
  "enablesPremiumMessaging": "boolean"
}
```

#### Request/Response Models

**SendMessageRequest**:
```json
{
  "to": ["string"],
  "messageBody": "string",
  "userLocation": UserLocation?,
  "referencePoint": UserLocation?,
  "messageType": "HermesMessageType?",
  "isPost": "boolean",
  "mediaId": "uuid?",
  "mediaType": "MediaType?",
  "uuid": "uuid?",
  "otaUuid": "uuid"
}
```

**SendMessageV2Response** (API v2):
```json
{
  "messageId": "uuid",
  "conversationId": "uuid",
  "signedUploadUrl": SignedUploadUrl?,
  "imageQuality": "string?"
}
```

#### Auth Models

**AccessAndRefreshToken**:
```json
{
  "accessToken": "string",
  "refreshToken": "string",
  "expiresIn": 3600
}
```

**AppRegistrationResponse**:
```json
{
  "instanceId": "string",
  "accessAndRefreshToken": AccessAndRefreshToken
}
```

**RefreshAuthBody**:
```json
{
  "refreshToken": "string",
  "instanceId": "string"
}
```

**NewInReachRegistrationUsingSsoResponse**:
```json
{
  "instanceId": "string",
  "accessAndRefreshToken": AccessAndRefreshToken
}
```

---

## 4. SignalR Real-Time Layer

### Connection

**Protocol**: Microsoft SignalR (official Java/Kotlin client)
**URL**: Same as Hermes base URL (`hermes.inreachapp.com`)
**Auth**: `Authorization: Bearer {accessToken}` (standard bearer for WebSocket)
**User-Agent**: `Microsoft SignalR/99.99.99-dev (...; Java; ...)`

**Timeouts**:
- Server timeout: 15,000 ms
- Handshake timeout: 30,000 ms
- Keepalive interval: 15,000 ms

**Wire Format**: JSON with `\u001e` (Record Separator) delimiter between messages

### Hub Connection Class

### Server → Client Methods (5 handlers)

| Method | Payload Type | Description |
|--------|-------------|-------------|
| `ReceiveMessage` | `MessageModel` | New incoming message |
| `ReceiveMessageUpdate` | `MessageUpdateJson` (polymorphic) | Status change or device metadata update |
| `ReceiveConversationMuteStatusUpdate` | `ConversationStatusUpdateJson` | Mute/unmute notification |
| `ReceiveUserBlockStatusUpdate` | `UserBlockStatusUpdateJson` | Block/unblock notification |
| `ReceiveServerNotification` | `HermesServerNotificationJson` | Server announcements |

### Client → Server Methods (Invoke)

| Method | Parameters | Response |
|--------|-----------|----------|
| `MarkAsDelivered` | messageId: UUID, conversationId: UUID | `UpdateMessageStatusResponseJson` |
| `MarkAsRead` | messageId: UUID, conversationId: UUID | `UpdateMessageStatusResponseJson` |
| `NetworkProperties` | — | `NetworkPropertiesResponse` |

### Message Update Types (polymorphic `MessageUpdateJson`)

- **MessageStatusUpdateJson**: `{messageId, senderId, targetId, status, statusInfo, timestamp}`
- **MessageDeviceMetadataUpdateJson**: `{deviceMetadata}`

### Reconnection

- Automatic with exponential backoff (1000ms initial)
- Re-authenticates with fresh Bearer token
- Retryable errors: IOException, TimeoutException, GaiException, handshake failures

---

## 5. Media Attachments

- **S3 Bucket**: `certus-media-manager-prod`
- **Upload**: `Message/Send` v2 API returns a `SignedUploadUrl` with AWS signature v4 parameters. Client uploads directly to S3.
- **Download**: `GET Message/Media/DownloadUrl` returns a presigned download URL.

**SignedUploadUrl** (S3 presigned POST parameters):
```json
{
  "uploadUrl": "https://s3.amazonaws.com/certus-media-manager-prod/",
  "key": "media/uploads/{uuid}",
  "x-amz-storage-class": "STANDARD",
  "x-amz-date": "20250115T103000Z",
  "x-amz-signature": "{hex signature}",
  "x-amz-algorithm": "AWS4-HMAC-SHA256",
  "x-amz-credential": "{access-key}/{date}/{region}/s3/aws4_request",
  "policy": "{base64-encoded POST policy}",
  "x-amz-meta-media-quality": "INTERNET",
  "content-type": "image/avif"
}
```
> Note: `content-type` field has multiple case variants in the wild
> (`Content-type`, `content-Type`, `Content-Type`). The client accepts all.

**Upload flow**: POST multipart form data to `uploadUrl` with all signing fields
as form fields and the file as a `file` part.

**UpdateMediaRequest** (POST Message/UpdateMedia):
```json
{
  "mediaType": "ImageAvif",
  "mediaId": "uuid",
  "messageId": "uuid?",
  "conversationId": "uuid?"
}
```

**UpdateMediaResponse**:
```json
{
  "signedUploadUrl": SignedUploadUrl,
  "imageQuality": "INTERNET"
}
```

**MediaAttachmentDownloadUrlResponse** (GET Message/Media/DownloadUrl):
```json
{
  "url": "https://s3.amazonaws.com/certus-media-manager-prod/...?AWSAccessKeyId=...&Signature=...&Expires=..."
}
```

---

## 6. Open Questions

### Needs testing:
1. **Token lifetimes** — exact `expiresIn` values returned by Hermes.
2. **Rate limiting** — headers, limits, backoff requirements.
3. **Error response format** — exact JSON error structure.
4. **NetworkPropertiesResponse** contents — what network properties are returned?
5. **UserCapabilitiesResponse** — full list of capability flags.
6. **Message catch-up on reconnect** — does SignalR replay missed messages or must client poll REST API?
7. **Fake IMEI tolerance** — does `Registration/SSO/{imei}` accept a placeholder IMEI?
8. **RegistrationApiKey for SMS path** — what value does the initial `POST Registration/App` use when no prior Hermes token exists?
