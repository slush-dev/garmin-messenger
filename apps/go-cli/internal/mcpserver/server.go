package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/slush-dev/garmin-messenger/apps/go-cli/internal/contacts"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// GarminMCPServer wraps an MCP server exposing Garmin Messenger as tools and resources.
type GarminMCPServer struct {
	server     *mcp.Server
	sessionDir string
	logger     *slog.Logger

	mu   sync.RWMutex
	auth *gm.HermesAuth
	api  *gm.HermesAPI

	contacts  *contacts.Contacts
	addresses map[string]string

	pendingOTP *gm.OtpRequest // stored between login_request_otp and login_confirm_otp

	listenMu     sync.RWMutex
	listening     bool
	listenCancel  context.CancelFunc
	sr            *gm.HermesSignalR

}

// New creates a new GarminMCPServer. It attempts non-fatal auth resume
// so already-logged-in users can use resources immediately.
func New(sessionDir, version string, logger *slog.Logger) *GarminMCPServer {
	s := mcp.NewServer(&mcp.Implementation{
		Name:    "garmin-messenger",
		Version: version,
	}, &mcp.ServerOptions{
		SubscribeHandler:   func(context.Context, *mcp.SubscribeRequest) error { return nil },
		UnsubscribeHandler: func(context.Context, *mcp.UnsubscribeRequest) error { return nil },
	})

	g := &GarminMCPServer{
		server:     s,
		sessionDir: sessionDir,
		logger:     logger,
		contacts:   contacts.LoadContacts(sessionDir),
		addresses:  contacts.LoadAddresses(sessionDir),
	}

	// Attempt non-fatal session resume
	auth := gm.NewHermesAuth(gm.WithSessionDir(sessionDir))
	if err := auth.Resume(context.Background()); err == nil {
		g.auth = auth
		g.api = gm.NewHermesAPI(auth)
		logger.Debug("resumed existing session")
	} else {
		logger.Debug("no existing session", "error", err)
	}

	g.registerResources()
	g.registerTools()

	return g
}

// Run starts the MCP server on the given transport and blocks until done.
func (g *GarminMCPServer) Run(ctx context.Context) error {
	return g.server.Run(ctx, &mcp.StdioTransport{})
}

// RunWithTransport starts the MCP server on a custom transport (for testing).
func (g *GarminMCPServer) RunWithTransport(ctx context.Context, t mcp.Transport) error {
	_, err := g.server.Connect(ctx, t, nil)
	return err
}

// ensureAuth returns the current auth and API clients, or an error if not logged in.
func (g *GarminMCPServer) ensureAuth() (*gm.HermesAuth, *gm.HermesAPI, error) {
	g.mu.RLock()
	defer g.mu.RUnlock()
	if g.auth == nil || g.api == nil {
		return nil, nil, fmt.Errorf("not logged in — use login_request_otp and login_confirm_otp tools first")
	}
	return g.auth, g.api, nil
}

// reloadContacts reloads contacts and addresses from disk.
func (g *GarminMCPServer) reloadContacts() {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.contacts = contacts.LoadContacts(g.sessionDir)
	g.addresses = contacts.LoadAddresses(g.sessionDir)
}

// jsonResult marshals v to JSON and returns it as a text CallToolResult.
func jsonResult(v any) (*mcp.CallToolResult, error) {
	data, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("marshaling result: %w", err)
	}
	return &mcp.CallToolResult{
		Content: []mcp.Content{
			&mcp.TextContent{Text: string(data)},
		},
	}, nil
}

// errorResult returns a CallToolResult with IsError=true.
func errorResult(msg string) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		Content: []mcp.Content{
			&mcp.TextContent{Text: msg},
		},
		IsError: true,
	}
}
