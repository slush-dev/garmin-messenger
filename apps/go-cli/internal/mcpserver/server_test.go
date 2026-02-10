package mcpserver

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"testing"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// testServer creates a GarminMCPServer with a temp session dir and connects
// an MCP client for testing. Returns the client session and a cleanup function.
func testServer(t *testing.T) (*mcp.ClientSession, *GarminMCPServer) {
	t.Helper()
	dir := t.TempDir()
	logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelDebug}))

	g := New(dir, "test", logger)

	t1, t2 := mcp.NewInMemoryTransports()
	ctx := context.Background()

	_, err := g.server.Connect(ctx, t1, nil)
	if err != nil {
		t.Fatalf("server connect: %v", err)
	}

	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "1.0"}, nil)
	cs, err := client.Connect(ctx, t2, nil)
	if err != nil {
		t.Fatalf("client connect: %v", err)
	}

	return cs, g
}

func TestStatusResource_WithInstanceID(t *testing.T) {
	cs, g := testServer(t)
	ctx := context.Background()

	// Simulate a logged-in state with an instance ID
	g.mu.Lock()
	g.auth = &gm.HermesAuth{}
	g.auth.InstanceID = "test-instance-123"
	g.mu.Unlock()

	result, err := cs.ReadResource(ctx, &mcp.ReadResourceParams{URI: "garmin://status"})
	if err != nil {
		t.Fatalf("read status: %v", err)
	}

	var status map[string]any
	if err := json.Unmarshal([]byte(result.Contents[0].Text), &status); err != nil {
		t.Fatalf("unmarshal status: %v", err)
	}

	if status["logged_in"] != true {
		t.Errorf("expected logged_in=true, got %v", status["logged_in"])
	}
	if status["instance_id"] != "test-instance-123" {
		t.Errorf("expected instance_id=test-instance-123, got %v", status["instance_id"])
	}
}

func TestStatusResource_NotLoggedIn(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	result, err := cs.ReadResource(ctx, &mcp.ReadResourceParams{URI: "garmin://status"})
	if err != nil {
		t.Fatalf("read status: %v", err)
	}

	if len(result.Contents) != 1 {
		t.Fatalf("expected 1 content, got %d", len(result.Contents))
	}

	var status map[string]any
	if err := json.Unmarshal([]byte(result.Contents[0].Text), &status); err != nil {
		t.Fatalf("unmarshal status: %v", err)
	}

	if status["logged_in"] != false {
		t.Errorf("expected logged_in=false, got %v", status["logged_in"])
	}
	if status["listening"] != false {
		t.Errorf("expected listening=false, got %v", status["listening"])
	}
	if _, ok := status["instance_id"]; ok {
		t.Errorf("expected no instance_id when not logged in, got %v", status["instance_id"])
	}
}

func TestContactsResource_Empty(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	result, err := cs.ReadResource(ctx, &mcp.ReadResourceParams{URI: "garmin://contacts"})
	if err != nil {
		t.Fatalf("read contacts: %v", err)
	}

	var data map[string]any
	if err := json.Unmarshal([]byte(result.Contents[0].Text), &data); err != nil {
		t.Fatalf("unmarshal contacts: %v", err)
	}

	// Should have empty maps
	members, ok := data["members"].(map[string]any)
	if !ok {
		t.Fatalf("expected members to be a map, got %T", data["members"])
	}
	if len(members) != 0 {
		t.Errorf("expected 0 members, got %d", len(members))
	}
}

func TestToolsRegistered(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	expectedTools := map[string]bool{
		"login_request_otp":  false,
		"login_confirm_otp":  false,
		"send_message":       false,
		"send_media_message": false,
		"mark_as_read":       false,
		"download_media":     false,
		"sync_contacts":      false,
		"listen":             false,
		"stop":               false,
	}

	for tool, err := range cs.Tools(ctx, nil) {
		if err != nil {
			t.Fatalf("listing tools: %v", err)
		}
		if _, ok := expectedTools[tool.Name]; ok {
			expectedTools[tool.Name] = true
		}
	}

	for name, found := range expectedTools {
		if !found {
			t.Errorf("tool %q not registered", name)
		}
	}
}

func TestResourcesRegistered(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	expectedResources := map[string]bool{
		"garmin://status":        false,
		"garmin://contacts":      false,
		"garmin://conversations": false,
	}

	for res, err := range cs.Resources(ctx, nil) {
		if err != nil {
			t.Fatalf("listing resources: %v", err)
		}
		if _, ok := expectedResources[res.URI]; ok {
			expectedResources[res.URI] = true
		}
	}

	for uri, found := range expectedResources {
		if !found {
			t.Errorf("resource %q not registered", uri)
		}
	}

	// Check templates
	expectedTemplates := map[string]bool{
		"garmin://conversations/{id}/messages": false,
		"garmin://conversations/{id}/members":  false,
	}

	for tmpl, err := range cs.ResourceTemplates(ctx, nil) {
		if err != nil {
			t.Fatalf("listing resource templates: %v", err)
		}
		if _, ok := expectedTemplates[tmpl.URITemplate]; ok {
			expectedTemplates[tmpl.URITemplate] = true
		}
	}

	for uri, found := range expectedTemplates {
		if !found {
			t.Errorf("resource template %q not registered", uri)
		}
	}
}

func TestSendMessageTool_NotLoggedIn(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	result, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name:      "send_message",
		Arguments: map[string]any{"to": []string{"+1234567890"}, "body": "test"},
	})
	if err != nil {
		t.Fatalf("call tool: %v", err)
	}

	if !result.IsError {
		t.Error("expected IsError=true for unauthenticated call")
	}
}

func TestListenTool_NotLoggedIn(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	result, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name: "listen",
	})
	if err != nil {
		t.Fatalf("call tool: %v", err)
	}

	if !result.IsError {
		t.Error("expected IsError=true for unauthenticated listen")
	}
}

func TestStopTool_NotListening(t *testing.T) {
	cs, _ := testServer(t)
	ctx := context.Background()

	result, err := cs.CallTool(ctx, &mcp.CallToolParams{
		Name: "stop",
	})
	if err != nil {
		t.Fatalf("call tool: %v", err)
	}

	if result.IsError {
		t.Error("stop when not listening should not be an error")
	}

	var data map[string]any
	text := result.Content[0].(*mcp.TextContent).Text
	if err := json.Unmarshal([]byte(text), &data); err != nil {
		t.Fatalf("unmarshal result: %v", err)
	}
	if data["listening"] != false {
		t.Errorf("expected listening=false, got %v", data["listening"])
	}
}

func TestParseMessagesURI(t *testing.T) {
	tests := []struct {
		name    string
		uri     string
		wantErr bool
	}{
		{
			name: "basic",
			uri:  "garmin://conversations/12345678-1234-1234-1234-123456789012/messages",
		},
		{
			name: "with limit",
			uri:  "garmin://conversations/12345678-1234-1234-1234-123456789012/messages?limit=50",
		},
		{
			name: "with pagination",
			uri:  "garmin://conversations/12345678-1234-1234-1234-123456789012/messages?older_than=12345678-1234-1234-1234-123456789012",
		},
		{
			name:    "invalid conv id",
			uri:     "garmin://conversations/not-a-uuid/messages",
			wantErr: true,
		},
		{
			name:    "wrong path",
			uri:     "garmin://conversations/12345678-1234-1234-1234-123456789012/wrong",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, _, err := parseMessagesURI(tt.uri)
			if (err != nil) != tt.wantErr {
				t.Errorf("parseMessagesURI(%q) error = %v, wantErr %v", tt.uri, err, tt.wantErr)
			}
		})
	}
}

func TestParseMembersURI(t *testing.T) {
	tests := []struct {
		name    string
		uri     string
		wantErr bool
	}{
		{
			name: "valid",
			uri:  "garmin://conversations/12345678-1234-1234-1234-123456789012/members",
		},
		{
			name:    "invalid conv id",
			uri:     "garmin://conversations/bad/members",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := parseMembersURI(tt.uri)
			if (err != nil) != tt.wantErr {
				t.Errorf("parseMembersURI(%q) error = %v, wantErr %v", tt.uri, err, tt.wantErr)
			}
		})
	}
}
