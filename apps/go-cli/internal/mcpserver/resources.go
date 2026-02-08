package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"strconv"
	"strings"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func (g *GarminMCPServer) registerResources() {
	g.server.AddResource(&mcp.Resource{
		URI:         "garmin://status",
		Name:        "Server Status",
		Description: "Current login and listening state",
		MIMEType:    "application/json",
	}, g.handleStatusResource)

	g.server.AddResource(&mcp.Resource{
		URI:         "garmin://contacts",
		Name:        "Contacts",
		Description: "Local contacts and address book",
		MIMEType:    "application/json",
	}, g.handleContactsResource)

	g.server.AddResource(&mcp.Resource{
		URI:         "garmin://conversations",
		Name:        "Conversations",
		Description: "List of conversations",
		MIMEType:    "application/json",
	}, g.handleConversationsResource)

	g.server.AddResourceTemplate(&mcp.ResourceTemplate{
		URITemplate: "garmin://conversations/{id}/messages",
		Name:        "Conversation Messages",
		Description: "Messages in a conversation. Query params: ?limit=N&older_than=UUID&newer_than=UUID",
		MIMEType:    "application/json",
	}, g.handleMessagesResource)

	g.server.AddResourceTemplate(&mcp.ResourceTemplate{
		URITemplate: "garmin://conversations/{id}/members",
		Name:        "Conversation Members",
		Description: "Members of a conversation",
		MIMEType:    "application/json",
	}, g.handleMembersResource)
}

func (g *GarminMCPServer) handleStatusResource(_ context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
	g.mu.RLock()
	loggedIn := g.auth != nil
	g.mu.RUnlock()

	g.listenMu.Lock()
	listening := g.listening
	g.listenMu.Unlock()

	status := map[string]any{
		"logged_in": loggedIn,
		"listening": listening,
	}
	return jsonResource(req.Params.URI, status)
}

func (g *GarminMCPServer) handleContactsResource(_ context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
	g.mu.RLock()
	c := g.contacts
	addrs := g.addresses
	g.mu.RUnlock()

	result := map[string]any{
		"members":       c.Members,
		"conversations": c.Conversations,
		"addresses":     addrs,
	}
	return jsonResource(req.Params.URI, result)
}

func (g *GarminMCPServer) handleConversationsResource(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return nil, err
	}
	convos, err := api.GetConversations(ctx)
	if err != nil {
		return nil, fmt.Errorf("fetching conversations: %w", err)
	}
	return jsonResource(req.Params.URI, convos)
}

func (g *GarminMCPServer) handleMessagesResource(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return nil, err
	}

	convID, opts, err := parseMessagesURI(req.Params.URI)
	if err != nil {
		return nil, err
	}

	detail, err := api.GetConversationDetail(ctx, convID, opts...)
	if err != nil {
		return nil, fmt.Errorf("fetching messages: %w", err)
	}
	return jsonResource(req.Params.URI, detail)
}

func (g *GarminMCPServer) handleMembersResource(ctx context.Context, req *mcp.ReadResourceRequest) (*mcp.ReadResourceResult, error) {
	_, api, err := g.ensureAuth()
	if err != nil {
		return nil, err
	}

	convID, err := parseMembersURI(req.Params.URI)
	if err != nil {
		return nil, err
	}

	members, err := api.GetConversationMembers(ctx, convID)
	if err != nil {
		return nil, fmt.Errorf("fetching members: %w", err)
	}
	return jsonResource(req.Params.URI, members)
}

// jsonResource marshals v to JSON and wraps it in a ReadResourceResult.
func jsonResource(uri string, v any) (*mcp.ReadResourceResult, error) {
	data, err := json.Marshal(v)
	if err != nil {
		return nil, fmt.Errorf("marshaling resource: %w", err)
	}
	return &mcp.ReadResourceResult{
		Contents: []*mcp.ResourceContents{{
			URI:      uri,
			MIMEType: "application/json",
			Text:     string(data),
		}},
	}, nil
}

// parseMessagesURI parses "garmin://conversations/{id}/messages?limit=N&older_than=UUID&newer_than=UUID"
func parseMessagesURI(rawURI string) (uuid.UUID, []gm.GetConversationDetailOption, error) {
	// garmin://conversations/{id}/messages → scheme=garmin, host=conversations, path=/{id}/messages
	u, err := url.Parse(rawURI)
	if err != nil {
		return uuid.Nil, nil, fmt.Errorf("invalid URI: %w", err)
	}

	// Path is "/{id}/messages"
	parts := strings.Split(strings.TrimPrefix(u.Path, "/"), "/")
	if len(parts) < 2 || parts[1] != "messages" {
		return uuid.Nil, nil, fmt.Errorf("invalid messages URI: %s", rawURI)
	}

	convID, err := uuid.Parse(parts[0])
	if err != nil {
		return uuid.Nil, nil, fmt.Errorf("invalid conversation ID in URI: %w", err)
	}

	var opts []gm.GetConversationDetailOption
	q := u.Query()
	if v := q.Get("limit"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return uuid.Nil, nil, fmt.Errorf("invalid limit: %w", err)
		}
		opts = append(opts, gm.WithDetailLimit(n))
	}
	if v := q.Get("older_than"); v != "" {
		id, err := uuid.Parse(v)
		if err != nil {
			return uuid.Nil, nil, fmt.Errorf("invalid older_than UUID: %w", err)
		}
		opts = append(opts, gm.WithOlderThanID(id))
	}
	if v := q.Get("newer_than"); v != "" {
		id, err := uuid.Parse(v)
		if err != nil {
			return uuid.Nil, nil, fmt.Errorf("invalid newer_than UUID: %w", err)
		}
		opts = append(opts, gm.WithNewerThanID(id))
	}

	return convID, opts, nil
}

// parseMembersURI parses "garmin://conversations/{id}/members"
func parseMembersURI(rawURI string) (uuid.UUID, error) {
	u, err := url.Parse(rawURI)
	if err != nil {
		return uuid.Nil, fmt.Errorf("invalid URI: %w", err)
	}

	parts := strings.Split(strings.TrimPrefix(u.Path, "/"), "/")
	if len(parts) < 2 || parts[1] != "members" {
		return uuid.Nil, fmt.Errorf("invalid members URI: %s", rawURI)
	}

	convID, err := uuid.Parse(parts[0])
	if err != nil {
		return uuid.Nil, fmt.Errorf("invalid conversation ID in URI: %w", err)
	}

	return convID, nil
}
