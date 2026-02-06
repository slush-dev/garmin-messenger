# Garmin Messenger — Go Client

Go library for the Garmin Messenger (Hermes) protocol. Send and receive messages to Garmin InReach satellite devices programmatically.

For protocol documentation and API reference, see the [root README](../../README.md) and [docs/api-reference.md](../../docs/api-reference.md). For the CLI tool, see [apps/go-cli/](../../apps/go-cli/).

[![Go 1.24+](https://img.shields.io/badge/go-1.24+-00ADD8.svg)](https://go.dev/dl/)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/slush-dev/garmin-messenger.git
cd garmin-messenger/clients/go

# Run tests
go test ./... -v
```

## Installation

```go
import gm "github.com/slush-dev/garmin-messenger"
```

### Dependencies

| Package | Purpose |
|---|---|
| `github.com/google/uuid` | UUID generation and parsing |
| `github.com/philippseith/signalr` | Microsoft SignalR WebSocket client |

## Library Usage

### Authentication

```go
package main

import (
    "context"
    "fmt"

    gm "github.com/slush-dev/garmin-messenger"
)

func main() {
    ctx := context.Background()

    auth := gm.NewHermesAuth(
        gm.WithSessionDir("~/.garmin-messenger"),
    )

    // First time: two-step SMS OTP registration
    otpReq, err := auth.RequestOTP(ctx, "+1234567890", "My App")
    // ... collect OTP code from the user ...
    err = auth.ConfirmOTP(ctx, otpReq, "123456")

    // Subsequent runs: resume saved session
    err = auth.Resume(ctx)
}
```

Credentials are saved to `~/.garmin-messenger/hermes_credentials.json` and automatically refreshed when expired.

### Sending Messages

```go
api := gm.NewHermesAPI(auth)
defer api.Close()

lat, lon, alt := 48.8566, 2.3522, 35.0
result, err := api.SendMessage(ctx, []string{"+1234567890"}, "Hello from Go!",
    // Optional: attach your location
    gm.WithUserLocation(gm.UserLocation{
        LatitudeDegrees:  &lat,
        LongitudeDegrees: &lon,
        ElevationMeters:  &alt,
    }),
)
fmt.Printf("Sent! Message ID: %s\n", result.MessageID)
fmt.Printf("Conversation ID: %s\n", result.ConversationID)
```

### Listing Conversations and Messages

```go
api := gm.NewHermesAPI(auth)
defer api.Close()

// Get recent conversations
convs, err := api.GetConversations(ctx, gm.WithLimit(20))
for _, conv := range convs.Conversations {
    fmt.Printf("Conversation %s\n", conv.ConversationID)
    fmt.Printf("  Members: %v\n", conv.MemberIDs)
    fmt.Printf("  Updated: %s\n", conv.UpdatedDate)
}

// Get messages from a specific conversation
detail, err := api.GetConversationDetail(ctx, conv.ConversationID, gm.WithDetailLimit(50))
for _, msg := range detail.Messages {
    fmt.Printf("  [%s] %s: %s\n", msg.SentAt, deref(msg.From), deref(msg.MessageBody))
}
```

### Real-Time Message Receiving (WebSocket)

```go
sr := gm.NewHermesSignalR(auth)

// Listen for incoming messages
sr.OnMessage(func(msg gm.MessageModel) {
    fmt.Printf("New message from %s: %s\n", deref(msg.From), deref(msg.MessageBody))
})

// Listen for delivery status updates
sr.OnStatusUpdate(func(upd gm.MessageStatusUpdate) {
    fmt.Printf("Message %s -> %s\n", upd.MessageID.MessageID, deref(upd.MessageStatus))
})

// Connection lifecycle
sr.OnOpen(func() { fmt.Println("Connected to Garmin Messenger") })
sr.OnClose(func() { fmt.Println("Disconnected") })

// Start listening (blocks until context is cancelled)
err := sr.Start(ctx)
<-ctx.Done()
sr.Stop()
```

The WebSocket client handles Azure SignalR Service negotiate/redirect and supports automatic token refresh.

### Marking Messages as Read/Delivered

```go
// Via REST API
api.MarkAsDelivered(ctx, conversationID, messageID)
api.MarkAsRead(ctx, conversationID, messageID)

// Via SignalR (real-time)
sr.MarkAsDelivered(conversationID, messageID)
sr.MarkAsRead(conversationID, messageID)
```

### Sending Media Attachments

```go
// Send a message with an image (AVIF) or audio (OGG)
fileData, _ := os.ReadFile("photo.avif")

result, err := api.SendMediaMessage(ctx, []string{"+1234567890"},
    "Photo from camp", fileData, gm.MediaTypeImageAvif,
)

// Download a media attachment from a received message
data, err := api.DownloadMedia(ctx,
    *msg.UUID, *msg.MediaID, msg.MessageID, msg.ConversationID,
    gm.MediaType(*msg.MediaType),
)
os.WriteFile("downloaded.avif", data, 0o644)
```

### Managing Conversations

```go
api := gm.NewHermesAPI(auth)
defer api.Close()

// Get conversation members with phone numbers
members, err := api.GetConversationMembers(ctx, conversationID)
for _, m := range members {
    fmt.Printf("  %s: %s\n", deref(m.FriendlyName), deref(m.Address))
}

// Mute / unmute a conversation
api.MuteConversation(ctx, conversationID, true)
api.MuteConversation(ctx, conversationID, false)

// List muted conversations
muted, err := api.GetMutedConversations(ctx)

// Block / unblock a user
api.BlockUser(ctx, userID)
api.UnblockUser(ctx, userID)
blocked, err := api.GetBlockedUsers(ctx)

// Get account capabilities
caps, err := api.GetCapabilities(ctx)
```

### Device Metadata and Network

```go
// Get satellite device metadata for messages (IMEI, device type, etc.)
ids := []gm.SimpleCompoundMessageId{
    {MessageID: msgID, ConversationID: convID},
}
metadata, err := api.GetMessageDeviceMetadata(ctx, ids)
for _, entry := range metadata {
    if entry.DeviceMetadata != nil {
        for _, dev := range entry.DeviceMetadata.DeviceMessageMetadata {
            fmt.Printf("  Device IMEI: %d\n", *dev.IMEI)
        }
    }
}

// Get Iridium network status
network, err := api.GetNetworkProperties(ctx)
```

### Batch Status Updates

```go
// Update multiple message statuses at once
updates := []gm.UpdateMessageStatusRequest{
    {MessageID: msgID, ConversationID: convID, MessageStatus: gm.MessageStatusDelivered},
}
results, err := api.UpdateMessageStatuses(ctx, updates)

// Get statuses updated since a timestamp
updated, err := api.GetUpdatedStatuses(ctx, since, gm.WithStatusLimit(100))
```

### Phone Number to User ID

```go
// Convert a phone number to a Hermes UUID-v5 (used as memberIds, from, etc.)
userID := gm.PhoneToHermesUserID("+1234567890")
```

## Data Models

All API responses are parsed into typed Go structs. See [`models.go`](models.go) for full definitions.

| Model | Description |
|---|---|
| `MessageModel` | Full message with body, sender, timestamps, location, media, status |
| `ConversationMetaModel` | Conversation metadata: members, dates, mute status |
| `ConversationDetailModel` | Conversation with message history |
| `UserInfoModel` | Conversation member with phone number and display name |
| `UserLocation` | GPS coordinates, elevation, speed, heading |
| `SendMessageV2Response` | Response after sending (message ID, conversation ID, signed upload URL) |
| `MessageStatusUpdate` | Real-time delivery/read status change |
| `MessageDeviceMetadataV2` | Satellite device info (IMEI, device type, satellite message details) |
| `NetworkPropertiesResponse` | Iridium satellite network status |
| `DeviceType` | Enum: `MessengerApp`, `inReach`, `GarminOSApp`, etc. |
| `MessageStatus` | Enum: `Sent`, `Delivered`, `Read`, `Processing`, etc. |
| `MediaType` | Enum: `ImageAvif`, `AudioOgg` |
| `HermesMessageType` | Enum: `Unknown`, `MapShare`, `ReferencePoint` |

## API Reference

| Method | Description |
|---|---|
| **Messaging** | |
| `SendMessage()` | Send a text message to one or more recipients |
| `SendMediaMessage()` | Send a message with a media attachment (convenience) |
| **Conversations** | |
| `GetConversations()` | List recent conversations |
| `GetConversationDetail()` | Get messages from a conversation |
| `GetConversationMembers()` | Get members with phone numbers and names |
| `MuteConversation()` | Mute or unmute a conversation |
| `GetMutedConversations()` | List muted conversations |
| **Status** | |
| `MarkAsRead()` | Mark a message as read |
| `MarkAsDelivered()` | Mark a message as delivered |
| `UpdateMessageStatuses()` | Batch update message statuses |
| `GetUpdatedStatuses()` | Get statuses changed since a timestamp |
| **Media** | |
| `UploadMedia()` | Upload file to S3 via presigned POST |
| `DownloadMedia()` | Download a media attachment |
| `GetMediaDownloadURL()` | Get presigned S3 download URL |
| `UpdateMedia()` | Confirm upload or request new signed URL |
| **Users** | |
| `BlockUser()` / `UnblockUser()` | Block or unblock a user |
| `GetBlockedUsers()` | List blocked users |
| `GetCapabilities()` | Get account capabilities |
| **Device & Network** | |
| `GetMessageDeviceMetadata()` | Get satellite device info for messages |
| `GetNetworkProperties()` | Get Iridium network status |

## Project Structure

```
clients/go/
├── go.mod            # Module: github.com/slush-dev/garmin-messenger
├── doc.go            # Package documentation
├── models.go         # All structs, enums, and JSON deserialization (42 types)
├── auth.go           # SMS OTP authentication and token management
├── api.go            # REST API client (net/http)
├── signalr.go        # Real-time WebSocket client (SignalR)
├── otauuid.go        # Garmin OTA UUID generator (custom bit layout)
└── *_test.go         # 94 unit tests across 5 test files
```

## Testing

```bash
cd clients/go
go test ./... -v
```

94 tests across 5 test files covering models, API, SignalR, authentication, and OTA UUID generation.

## Requirements

- Go 1.24+
- A Garmin Messenger account (see [root README](../../README.md#requirements))
