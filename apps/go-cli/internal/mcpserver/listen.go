package mcpserver

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/slush-dev/garmin-messenger/fcm"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func listenTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "listen",
		Description: "Start listening for incoming messages in real time via SignalR (and optionally FCM catch-up). Returns immediately; messages arrive as resource updates.",
		InputSchema: json.RawMessage(`{
			"type": "object",
			"properties": {
				"no_catchup": {"type": "boolean", "description": "Skip FCM catch-up, use SignalR only (default: false)"},
				"catchup_timeout": {"type": "integer", "description": "Seconds to wait for FCM catch-up (default: 15)"}
			}
		}`),
	}
}

func (g *GarminMCPServer) handleListen(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	auth, _, err := g.ensureAuth()
	if err != nil {
		return errorResult(err.Error()), nil
	}

	g.listenMu.Lock()
	if g.listening {
		g.listenMu.Unlock()
		return jsonResult(map[string]any{"listening": true, "message": "already listening"})
	}
	g.listening = true
	g.listenMu.Unlock()

	var args struct {
		NoCatchup      bool `json:"no_catchup"`
		CatchupTimeout int  `json:"catchup_timeout"`
	}
	if req.Params.Arguments != nil {
		if err := json.Unmarshal(req.Params.Arguments, &args); err != nil {
			return errorResult(fmt.Sprintf("invalid arguments: %v", err)), nil
		}
	}
	if args.CatchupTimeout <= 0 {
		args.CatchupTimeout = 15
	}

	listenCtx, cancel := context.WithCancel(context.Background())
	g.listenMu.Lock()
	g.listenCancel = cancel
	g.listenMu.Unlock()

	go g.runListenLoop(listenCtx, auth, args.NoCatchup, args.CatchupTimeout)

	g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{URI: "garmin://status"})

	return jsonResult(map[string]any{"listening": true})
}

func stopTool() *mcp.Tool {
	return &mcp.Tool{
		Name:        "stop",
		Description: "Stop listening for incoming messages.",
		InputSchema: json.RawMessage(`{"type": "object"}`),
	}
}

func (g *GarminMCPServer) handleStop(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	g.listenMu.Lock()
	if !g.listening {
		g.listenMu.Unlock()
		return jsonResult(map[string]any{"listening": false, "message": "not listening"})
	}
	if g.listenCancel != nil {
		g.listenCancel()
	}
	if g.sr != nil {
		g.sr.Stop()
	}
	g.listening = false
	g.listenMu.Unlock()

	g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{URI: "garmin://status"})

	return jsonResult(map[string]any{"listening": false})
}

func (g *GarminMCPServer) runListenLoop(ctx context.Context, auth *gm.HermesAuth, noCatchup bool, catchupTimeout int) {
	defer func() {
		g.listenMu.Lock()
		g.listening = false
		g.listenMu.Unlock()
		g.server.ResourceUpdated(context.Background(), &mcp.ResourceUpdatedNotificationParams{URI: "garmin://status"})
	}()

	sr := gm.NewHermesSignalR(auth)
	g.listenMu.Lock()
	g.sr = sr
	g.listenMu.Unlock()

	isDuplicate, clearDedup := newMessageDeduper()
	var dedupStateMu sync.RWMutex
	dedupEnabled := false
	setDedupEnabled := func(enabled bool) {
		dedupStateMu.Lock()
		dedupEnabled = enabled
		dedupStateMu.Unlock()
	}
	shouldDedup := func() bool {
		dedupStateMu.RLock()
		defer dedupStateMu.RUnlock()
		return dedupEnabled
	}

	sr.OnMessage(func(msg gm.MessageModel) {
		if !shouldDedup() || !isDuplicate(msg.MessageID.String()) {
			meta := mcp.Meta{
				"type":            "message",
				"conversation_id": msg.ConversationID.String(),
			}
			if msgJSON, err := json.Marshal(msg); err == nil {
				meta["message"] = json.RawMessage(msgJSON)
			}
			g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{
				URI:  "garmin://messages",
				Meta: meta,
			})
		}
		sr.MarkAsDelivered(msg.ConversationID, msg.MessageID)
	})

	sr.OnStatusUpdate(func(update gm.MessageStatusUpdate) {
		meta := mcp.Meta{
			"type":            "status_update",
			"conversation_id": update.MessageID.ConversationID.String(),
		}
		if updateJSON, err := json.Marshal(update); err == nil {
			meta["status_update"] = json.RawMessage(updateJSON)
		}
		g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{
			URI:  "garmin://messages",
			Meta: meta,
		})
	})

	sr.OnError(func(err error) {
		g.logger.Error("SignalR error", "error", err)
	})

	signalRStarted := false
	startSignalR := func() error {
		if signalRStarted {
			return nil
		}
		if err := sr.Start(ctx); err != nil {
			return err
		}
		signalRStarted = true
		return nil
	}

	// FCM catch-up
	if !noCatchup {
		fcmCredentialsPath := filepath.Join(g.sessionDir, "fcm_credentials.json")
		if _, err := os.Stat(fcmCredentialsPath); err == nil {
			fcmClient := fcm.NewClient(g.sessionDir)
			if _, err := fcmClient.Register(ctx); err == nil {
				g.logger.Debug("starting FCM catch-up")
				setDedupEnabled(true)

				var catchupCount atomic.Int32
				fcmClient.OnMessage(func(msg fcm.NewMessage) {
					if !isDuplicate(msg.MessageID.String()) {
						meta := mcp.Meta{
							"type":            "message",
							"conversation_id": msg.ConversationID.String(),
						}
						if msgJSON, err := json.Marshal(msg.MessageModel); err == nil {
							meta["message"] = json.RawMessage(msgJSON)
						}
						g.server.ResourceUpdated(ctx, &mcp.ResourceUpdatedNotificationParams{
							URI:  "garmin://messages",
							Meta: meta,
						})
						catchupCount.Add(1)
					}
				})

				mcsCtx, mcsCancel := context.WithCancel(ctx)
				mcsDone := make(chan struct{})
				go func() {
					defer close(mcsDone)
					if err := fcmClient.Listen(mcsCtx); err != nil {
						g.logger.Error("MCS listener error", "error", err)
					}
				}()

				if err := startSignalR(); err != nil {
					mcsCancel()
					<-mcsDone
					setDedupEnabled(false)
					clearDedup()
					g.logger.Error("SignalR start failed during catch-up", "error", err)
					return
				}

				select {
				case <-time.After(time.Duration(catchupTimeout) * time.Second):
				case <-ctx.Done():
					mcsCancel()
					<-mcsDone
					setDedupEnabled(false)
					clearDedup()
					if signalRStarted {
						sr.Stop()
					}
					return
				case <-mcsDone:
				}

				mcsCancel()
				<-mcsDone
				setDedupEnabled(false)
				clearDedup()
				g.logger.Debug("FCM catch-up complete", "count", catchupCount.Load())
			} else {
				g.logger.Warn("FCM catch-up unavailable", "error", err)
			}
		}
	}

	if err := startSignalR(); err != nil {
		g.logger.Error("SignalR start failed", "error", err)
		return
	}

	g.logger.Debug("listening for messages")
	<-ctx.Done()
	sr.Stop()
}

const maxDedupEntries = 1000

func newMessageDeduper() (func(string) bool, func()) {
	var mu sync.Mutex
	dedup := make(map[string]struct{})

	isDuplicate := func(msgID string) bool {
		if msgID == "" {
			return false
		}
		mu.Lock()
		defer mu.Unlock()
		if _, exists := dedup[msgID]; exists {
			return true
		}
		if len(dedup) >= maxDedupEntries {
			dedup = make(map[string]struct{})
		}
		dedup[msgID] = struct{}{}
		return false
	}

	clear := func() {
		mu.Lock()
		dedup = make(map[string]struct{})
		mu.Unlock()
	}

	return isDuplicate, clear
}
