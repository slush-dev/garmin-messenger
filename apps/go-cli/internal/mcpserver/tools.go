package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/slush-dev/garmin-messenger/apps/go-cli/internal/contacts"
	"github.com/slush-dev/garmin-messenger/fcm"
	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func (g *GarminMCPServer) registerTools() {
	// Login tools
	g.server.AddTool(loginRequestOTPTool(), g.handleLoginRequestOTP)
	g.server.AddTool(loginConfirmOTPTool(), g.handleLoginConfirmOTP)

	// Core tools
	g.server.AddTool(sendMessageTool(), g.handleSendMessage)
	g.server.AddTool(sendMediaMessageTool(), g.handleSendMediaMessage)
	g.server.AddTool(markAsReadTool(), g.handleMarkAsRead)
	g.server.AddTool(downloadMediaTool(), g.handleDownloadMedia)
	g.server.AddTool(syncContactsTool(), g.handleSyncContacts)

	// Listen tools
	g.server.AddTool(listenTool(), g.handleListen)
	g.server.AddTool(stopTool(), g.handleStop)
}

// --- Login tools ---

func loginRequestOTPTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "login_request_otp",
		Description: "Request an SMS OTP code for login. Returns a request_id needed by login_confirm_otp.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"phone": {"type": "string", "description": "Phone number with country code, e.g. +1234567890"},
				"device_name": {"type": "string", "description": "Device identifier (default: garmin-messenger)"}
			},
			"required": ["phone"]
		}`),
	}
}

func (g *GarminMCPServer) handleLoginRequestOTP(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	var args struct {
		Phone      string `json:"phone"`
		DeviceName string `json:"device_name"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}
	if args.Phone == "" {
		return errorResult("phone is required"), nil
	}
	if args.DeviceName == "" {
		args.DeviceName = "garmin-messenger"
	}

	auth := gm.NewHermesAuth(gm.WithSessionDir(g.sessionDir))
	otpReq, err := auth.RequestOTP(ctx, args.Phone, args.DeviceName)
	if err != nil {
		return errorResult(fmt.Sprintf("requesting OTP: %v", err)), nil
	}

	g.mu.Lock()
	g.pendingOTP = otpReq
	// Store partial auth for later use in confirm
	g.auth = auth
	g.mu.Unlock()

	result := map[string]any{
		"request_id":         otpReq.RequestID,
		"valid_until":        otpReq.ValidUntil,
		"attempts_remaining": otpReq.AttemptsRemaining,
	}
	return jsonResult(result)
}

func loginConfirmOTPTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "login_confirm_otp",
		Description: "Confirm an SMS OTP code to complete login. Use the request_id from login_request_otp.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"request_id": {"type": "string", "description": "The request_id from login_request_otp"},
				"phone": {"type": "string", "description": "Same phone number used in login_request_otp"},
				"otp_code": {"type": "string", "description": "The SMS OTP code received"}
			},
			"required": ["request_id", "phone", "otp_code"]
		}`),
	}
}

func (g *GarminMCPServer) handleLoginConfirmOTP(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	var args struct {
		RequestID string `json:"request_id"`
		Phone     string `json:"phone"`
		OTPCode   string `json:"otp_code"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}
	if args.RequestID == "" || args.Phone == "" || args.OTPCode == "" {
		return errorResult("request_id, phone, and otp_code are all required"), nil
	}

	g.mu.Lock()
	auth := g.auth
	pendingOTP := g.pendingOTP
	g.mu.Unlock()

	if auth == nil {
		return errorResult("no pending login — call login_request_otp first"), nil
	}

	// Reconstruct OtpRequest from args, using pendingOTP if matching
	var otpReq *gm.OtpRequest
	if pendingOTP != nil && pendingOTP.RequestID == args.RequestID {
		otpReq = pendingOTP
	} else {
		otpReq = &gm.OtpRequest{
			RequestID:   args.RequestID,
			PhoneNumber: args.Phone,
		}
	}

	if err := auth.ConfirmOTP(ctx, otpReq, args.OTPCode); err != nil {
		return errorResult(fmt.Sprintf("confirming OTP: %v", err)), nil
	}

	if auth.AccessToken == "" {
		return errorResult("authentication failed — no access token"), nil
	}

	// Non-fatal FCM registration (mirrors cmd/login.go)
	fcmMsg := ""
	fcmClient := fcm.NewClient(g.sessionDir)
	fcmToken, fcmErr := fcmClient.Register(ctx)
	if fcmErr != nil {
		fcmMsg = fmt.Sprintf("FCM registration failed: %v (push notifications unavailable)", fcmErr)
		g.logger.Warn("FCM registration failed", "error", fcmErr)
	} else {
		if err := auth.UpdatePnsHandle(ctx, fcmToken); err != nil {
			fcmMsg = fmt.Sprintf("FCM token update failed: %v", err)
			g.logger.Warn("PNS handle update failed", "error", err)
		} else {
			fcmMsg = "FCM push notifications registered"
		}
	}

	api := gm.NewHermesAPI(auth)

	g.mu.Lock()
	g.auth = auth
	g.api = api
	g.pendingOTP = nil
	g.mu.Unlock()

	g.reloadContacts()

	// Notify resource update
	g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{URI: "garmin://status"})

	result := map[string]any{
		"success":     true,
		"instance_id": auth.InstanceID,
		"fcm":         fcmMsg,
	}
	return jsonResult(result)
}

// --- Core tools ---

func sendMessageTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "send_message",
		Description: "Send a text message to one or more recipients.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"to": {"type": "array", "items": {"type": "string"}, "description": "Recipient addresses (phone numbers or user IDs)"},
				"body": {"type": "string", "description": "Message body text"},
				"latitude": {"type": "number", "description": "GPS latitude in degrees (optional, requires longitude)"},
				"longitude": {"type": "number", "description": "GPS longitude in degrees (optional, requires latitude)"},
				"elevation": {"type": "number", "description": "Elevation in meters (optional, requires lat/lon)"}
			},
			"required": ["to", "body"]
		}`),
	}
}

func (g *GarminMCPServer) handleSendMessage(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return errorResult(err.Error()), nil
	}

	var args struct {
		To        []string `json:"to"`
		Body      string   `json:"body"`
		Latitude  *float64 `json:"latitude"`
		Longitude *float64 `json:"longitude"`
		Elevation *float64 `json:"elevation"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}
	if len(args.To) == 0 || args.Body == "" {
		return errorResult("to and body are required"), nil
	}

	var opts []gm.SendMessageOption
	if args.Latitude != nil && args.Longitude != nil {
		opts = append(opts, gm.WithUserLocation(gm.UserLocation{
			LatitudeDegrees:  args.Latitude,
			LongitudeDegrees: args.Longitude,
			ElevationMeters:  args.Elevation,
		}))
	}

	result, err := api.SendMessage(ctx, args.To, args.Body, opts...)
	if err != nil {
		return errorResult(fmt.Sprintf("sending message: %v", err)), nil
	}

	return jsonResult(map[string]string{
		"message_id":      result.MessageID.String(),
		"conversation_id": result.ConversationID.String(),
	})
}

func sendMediaMessageTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "send_media_message",
		Description: "Send a message with a media attachment (image or audio file).",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"to": {"type": "array", "items": {"type": "string"}, "description": "Recipient addresses (phone numbers or user IDs)"},
				"body": {"type": "string", "description": "Message body text"},
				"file_path": {"type": "string", "description": "Path to media file (.avif image or .ogg/.oga audio)"},
				"media_type": {"type": "string", "enum": ["ImageAvif", "AudioOgg"], "description": "Media type (auto-detected from extension if omitted)"}
			},
			"required": ["to", "body", "file_path"]
		}`),
	}
}

func (g *GarminMCPServer) handleSendMediaMessage(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return errorResult(err.Error()), nil
	}

	var args struct {
		To        []string `json:"to"`
		Body      string   `json:"body"`
		FilePath  string   `json:"file_path"`
		MediaType string   `json:"media_type"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}
	if len(args.To) == 0 || args.Body == "" || args.FilePath == "" {
		return errorResult("to, body, and file_path are required"), nil
	}

	// Determine media type
	var mediaType gm.MediaType
	if args.MediaType != "" {
		mediaType = gm.MediaType(args.MediaType)
	} else {
		ext := strings.ToLower(filepath.Ext(args.FilePath))
		switch ext {
		case ".avif":
			mediaType = gm.MediaTypeImageAvif
		case ".ogg", ".oga":
			mediaType = gm.MediaTypeAudioOgg
		default:
			return errorResult(fmt.Sprintf("unsupported file extension '%s' — supported: .avif, .ogg, .oga", ext)), nil
		}
	}

	fileData, err := os.ReadFile(args.FilePath)
	if err != nil {
		return errorResult(fmt.Sprintf("reading file: %v", err)), nil
	}

	result, err := api.SendMediaMessage(ctx, args.To, args.Body, fileData, mediaType)
	if err != nil {
		return errorResult(fmt.Sprintf("sending media message: %v", err)), nil
	}

	return jsonResult(map[string]string{
		"message_id":      result.MessageID.String(),
		"conversation_id": result.ConversationID.String(),
	})
}

func markAsReadTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "mark_as_read",
		Description: "Mark a message as read.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"conversation_id": {"type": "string", "description": "Conversation UUID"},
				"message_id": {"type": "string", "description": "Message UUID"}
			},
			"required": ["conversation_id", "message_id"]
		}`),
	}
}

func (g *GarminMCPServer) handleMarkAsRead(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return errorResult(err.Error()), nil
	}

	var args struct {
		ConversationID string `json:"conversation_id"`
		MessageID      string `json:"message_id"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}

	convID, err := uuid.Parse(args.ConversationID)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid conversation_id: %v", err)), nil
	}
	msgID, err := uuid.Parse(args.MessageID)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid message_id: %v", err)), nil
	}

	if _, err := api.MarkAsRead(ctx, convID, msgID); err != nil {
		return errorResult(fmt.Sprintf("marking as read: %v", err)), nil
	}

	return jsonResult(map[string]bool{"success": true})
}

func downloadMediaTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "download_media",
		Description: "Download a media attachment from a message.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"conversation_id": {"type": "string", "description": "Conversation UUID"},
				"message_id": {"type": "string", "description": "Message UUID"},
				"output_path": {"type": "string", "description": "Output file path (default: {media_id}.{ext} in current directory)"}
			},
			"required": ["conversation_id", "message_id"]
		}`),
	}
}

func (g *GarminMCPServer) handleDownloadMedia(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return errorResult(err.Error()), nil
	}

	var args struct {
		ConversationID string `json:"conversation_id"`
		MessageID      string `json:"message_id"`
		OutputPath     string `json:"output_path"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}

	convID, err := uuid.Parse(args.ConversationID)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid conversation_id: %v", err)), nil
	}
	messageID, err := uuid.Parse(args.MessageID)
	if err != nil {
		return errorResult(fmt.Sprintf("invalid message_id: %v", err)), nil
	}

	// Fetch conversation detail to find the message
	detail, err := api.GetConversationDetail(ctx, convID)
	if err != nil {
		return errorResult(fmt.Sprintf("fetching conversation: %v", err)), nil
	}

	var mediaID uuid.UUID
	var mediaType gm.MediaType
	var msgUUID uuid.UUID
	found := false
	for _, m := range detail.Messages {
		if m.MessageID == messageID {
			if m.MediaID == nil {
				return errorResult(fmt.Sprintf("message %s has no media attachment", messageID)), nil
			}
			mediaID = *m.MediaID
			if m.MediaType != nil {
				mediaType = *m.MediaType
			}
			if m.UUID != nil {
				msgUUID = *m.UUID
			} else {
				msgUUID = m.MessageID
			}
			found = true
			break
		}
	}
	if !found {
		return errorResult(fmt.Sprintf("message %s not found in conversation %s", messageID, convID)), nil
	}

	data, err := api.DownloadMedia(ctx, msgUUID, mediaID, messageID, convID, mediaType)
	if err != nil {
		return errorResult(fmt.Sprintf("downloading media: %v", err)), nil
	}

	output := args.OutputPath
	if output == "" {
		ext := ".bin"
		switch mediaType {
		case gm.MediaTypeImageAvif:
			ext = ".avif"
		case gm.MediaTypeAudioOgg:
			ext = ".ogg"
		}
		output = mediaID.String() + ext
	}

	if err := os.WriteFile(output, data, 0o644); err != nil {
		return errorResult(fmt.Sprintf("writing file: %v", err)), nil
	}

	return jsonResult(map[string]any{
		"file_path":  output,
		"bytes":      len(data),
		"media_type": string(mediaType),
	})
}

func syncContactsTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "sync_contacts",
		Description: "Sync contacts from the server into local contacts file. Discovers new conversations and members.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"limit": {"type": "integer", "description": "Max conversations to fetch (default: 100)"}
			}
		}`),
	}
}

func (g *GarminMCPServer) handleSyncContacts(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return errorResult(err.Error()), nil
	}

	var args struct {
		Limit int `json:"limit"`
	}
	if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
		return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
	}
	if args.Limit <= 0 {
		args.Limit = 100
	}

	convos, err := api.GetConversations(ctx, gm.WithLimit(args.Limit))
	if err != nil {
		return errorResult(fmt.Sprintf("fetching conversations: %v", err)), nil
	}

	var apiMembers []struct{ Key, Name string }
	var apiAddresses []struct{ UUID, Phone string }
	var convIDs []string

	for _, c := range convos.Conversations {
		cid := c.ConversationID.String()
		convIDs = append(convIDs, cid)
		membersList, err := api.GetConversationMembers(ctx, c.ConversationID)
		if err != nil {
			return errorResult(fmt.Sprintf("fetching members for %s: %v", cid, err)), nil
		}
		for _, m := range membersList {
			uid := derefStr(m.UserIdentifier)
			if uid == "" {
				continue
			}
			suggested := ""
			fn := derefStr(m.FriendlyName)
			if fn != "" && fn != "?" {
				suggested = fn
			} else if addr := derefStr(m.Address); addr != "" {
				suggested = addr
			}
			apiMembers = append(apiMembers, struct{ Key, Name string }{uid, suggested})
			if addr := derefStr(m.Address); addr != "" {
				apiAddresses = append(apiAddresses, struct{ UUID, Phone string }{uid, addr})
			}
		}
	}

	g.mu.RLock()
	c := g.contacts
	g.mu.RUnlock()

	c.Members = contacts.MergeMembers(c.Members, apiMembers)
	c.Conversations = contacts.MergeConversations(c.Conversations, convIDs)
	if err := contacts.SaveContacts(g.sessionDir, c); err != nil {
		return errorResult(fmt.Sprintf("saving contacts: %v", err)), nil
	}

	existingAddresses := contacts.LoadAddresses(g.sessionDir)
	mergedAddresses := contacts.MergeAddresses(existingAddresses, apiAddresses)
	if err := contacts.SaveAddresses(g.sessionDir, mergedAddresses); err != nil {
		return errorResult(fmt.Sprintf("saving addresses: %v", err)), nil
	}

	g.reloadContacts()
	g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{URI: "garmin://contacts"})

	return jsonResult(map[string]any{
		"members":       len(c.Members),
		"conversations": len(c.Conversations),
	})
}

func derefStr(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
