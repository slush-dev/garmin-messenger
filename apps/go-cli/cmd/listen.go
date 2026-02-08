package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/slush-dev/garmin-messenger/fcm"
	"github.com/spf13/cobra"
)

var listenCmd = &cobra.Command{
	Use:   "listen",
	Short: "Listen for incoming messages in real time (Ctrl+C to stop)",
	RunE: func(cmd *cobra.Command, args []string) error {
		showUUID, _ := cmd.Flags().GetBool("uuid")
		noCatchup, _ := cmd.Flags().GetBool("no-catchup")
		auth := getAuth()
		contacts := LoadContacts(sessionDir)
		addresses := LoadAddresses(sessionDir)

		sr := gm.NewHermesSignalR(auth)
		displayMessage := func(msg gm.MessageModel) {
			printListenMessage(msg, showUUID, contacts, addresses, useYAML)
		}

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
				displayMessage(msg)
			}
			sr.MarkAsDelivered(msg.ConversationID, msg.MessageID)
		})

		sr.OnStatusUpdate(func(update gm.MessageStatusUpdate) {
			convID := update.MessageID.ConversationID.String()
			convLabel := contacts.ResolveConversation(convID)
			if convLabel == "" {
				convLabel = convID
			}
			if useYAML {
				row := map[string]any{
					"event":        "status",
					"conversation": convLabel,
					"status":       update.MessageStatus,
				}
				if showUUID {
					row["message_id"] = update.MessageID.MessageID.String()
					row["conversation_id"] = convID
				}
				fmt.Println("---")
				yamlOut(row)
			} else {
				if showUUID {
					fmt.Printf(">> STATUS conv=%s msg=%s status=%v\n",
						convID, update.MessageID.MessageID, derefStatus(update.MessageStatus))
				} else {
					fmt.Printf(">> STATUS [%s] status=%v\n",
						convLabel, derefStatus(update.MessageStatus))
				}
			}
		})

		sr.OnNonconversationalMessage(func(imei string) {
			if useYAML {
				fmt.Println("---")
				yamlOut(map[string]any{
					"event": "device",
					"imei":  imei,
				})
			} else {
				fmt.Printf(">> DEVICE imei=%s\n", imei)
			}
		})

		sr.OnOpen(func() {
			fmt.Fprintln(os.Stderr, "SignalR connected.")
		})
		sr.OnClose(func() {
			fmt.Fprintln(os.Stderr, "SignalR disconnected.")
		})
		sr.OnError(func(err error) {
			fmt.Fprintf(os.Stderr, "SignalR error: %v\n", err)
		})

		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()

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

		if !noCatchup {
			fcmCredentialsPath := filepath.Join(sessionDir, "fcm_credentials.json")
			if _, err := os.Stat(fcmCredentialsPath); err == nil {
				fcmClient := fcm.NewClient(sessionDir)
				if _, err := fcmClient.Register(ctx); err == nil {
					fmt.Fprintln(os.Stderr, "Catching up on missed messages via FCM...")
					setDedupEnabled(true)

					var catchupCount atomic.Int32
					fcmClient.OnMessage(func(msg fcm.NewMessage) {
						if !isDuplicate(msg.MessageID.String()) {
							displayMessage(msg.MessageModel)
							catchupCount.Add(1)
						}
					})
					fcmClient.OnConnected(func() {
						fmt.Fprintln(os.Stderr, "MCS connected.")
					})
					fcmClient.OnError(func(err error) {
						fmt.Fprintf(os.Stderr, "FCM error: %v\n", err)
					})

					mcsCtx, mcsCancel := context.WithCancel(ctx)
					mcsDone := make(chan struct{})
					go func() {
						defer close(mcsDone)
						if err := fcmClient.Listen(mcsCtx); err != nil {
							fmt.Fprintf(os.Stderr, "MCS listener error: %v\n", err)
						}
					}()

					if err := startSignalR(); err != nil {
						mcsCancel()
						<-mcsDone
						setDedupEnabled(false)
						clearDedup()
						return err
					}

					catchupTimeout, _ := cmd.Flags().GetInt("catchup-timeout")
					select {
					case <-time.After(time.Duration(catchupTimeout) * time.Second):
					case <-ctx.Done():
						mcsCancel()
						<-mcsDone
						setDedupEnabled(false)
						clearDedup()
						if signalRStarted {
							fmt.Fprintln(os.Stderr, "\nShutting down ...")
							sr.Stop()
						}
						return nil
					case <-mcsDone:
						// MCS listener exited early.
					}

					mcsCancel()
					<-mcsDone
					setDedupEnabled(false)
					clearDedup()
					fmt.Fprintf(os.Stderr, "Caught up on %d missed message(s).\n", catchupCount.Load())
				} else {
					fmt.Fprintf(os.Stderr, "FCM catch-up unavailable: %v\n", err)
				}
			} else if os.IsNotExist(err) {
				fmt.Fprintln(os.Stderr, "No FCM credentials found. Catch-up unavailable. Run 'garmin-messenger login' to register.")
			} else {
				fmt.Fprintf(os.Stderr, "FCM catch-up unavailable: %v\n", err)
			}
		}

		if err := startSignalR(); err != nil {
			return err
		}

		fmt.Fprintln(os.Stderr, "Listening for messages (Ctrl+C to stop) ...")
		<-ctx.Done()
		fmt.Fprintln(os.Stderr, "\nShutting down ...")
		sr.Stop()
		return nil
	},
}

func init() {
	listenCmd.Flags().Bool("uuid", false, "Show conversation_id, message_id, and sender_id in output")
	listenCmd.Flags().Bool("no-catchup", false, "Skip FCM catch-up, connect SignalR only")
	listenCmd.Flags().Int("catchup-timeout", 15, "Seconds to wait for FCM catch-up messages")
	rootCmd.AddCommand(listenCmd)
}

func printListenMessage(msg gm.MessageModel, showUUID bool, contacts *Contacts, addresses map[string]string, useYAML bool) {
	if useYAML {
		convID := msg.ConversationID.String()
		convName := contacts.ResolveConversation(convID)
		if convName == "" {
			convName = convID
		}
		row := map[string]any{
			"event":        "message",
			"conversation": convName,
		}
		if showUUID {
			row["conversation_id"] = convID
			row["message_id"] = msg.MessageID.String()
		}
		fields := senderFields(contacts, derefStr(msg.From), addresses)
		row["sender"] = fields["sender"]
		if showUUID {
			if id, ok := fields["sender_id"]; ok {
				row["sender_id"] = id
			}
		}
		if phone, ok := fields["sender_phone"]; ok {
			row["sender_phone"] = phone
		}
		row["body"] = derefStr(msg.MessageBody)
		if msg.UserLocation != nil && msg.UserLocation.LatitudeDegrees != nil {
			row["location"] = map[string]any{
				"latitude":  *msg.UserLocation.LatitudeDegrees,
				"longitude": *msg.UserLocation.LongitudeDegrees,
				"elevation": derefFloat(msg.UserLocation.ElevationMeters),
			}
		}
		if msg.ReferencePoint != nil && msg.ReferencePoint.LatitudeDegrees != nil {
			row["reference_point"] = map[string]any{
				"latitude":  *msg.ReferencePoint.LatitudeDegrees,
				"longitude": *msg.ReferencePoint.LongitudeDegrees,
				"elevation": derefFloat(msg.ReferencePoint.ElevationMeters),
			}
		}
		if msg.MapShareUrl != nil {
			row["map_share_url"] = *msg.MapShareUrl
		}
		if msg.LiveTrackUrl != nil {
			row["live_track_url"] = *msg.LiveTrackUrl
		}
		if hasMedia(msg.MediaID) {
			if !showUUID {
				row["conversation_id"] = convID
				row["message_id"] = msg.MessageID.String()
			}
			row["media_id"] = msg.MediaID.String()
			if msg.MediaType != nil {
				row["media_type"] = string(*msg.MediaType)
			}
			if msg.MediaMetadata != nil {
				meta := map[string]any{}
				if msg.MediaMetadata.Width != nil {
					meta["width"] = *msg.MediaMetadata.Width
				}
				if msg.MediaMetadata.Height != nil {
					meta["height"] = *msg.MediaMetadata.Height
				}
				if msg.MediaMetadata.DurationMs != nil {
					meta["duration_ms"] = *msg.MediaMetadata.DurationMs
				}
				if len(meta) > 0 {
					row["media_metadata"] = meta
				}
			}
		}
		fmt.Println("---")
		yamlOut(row)
		return
	}

	convID := msg.ConversationID.String()
	convLabel := contacts.ResolveConversation(convID)
	if convLabel == "" {
		convLabel = convID
	}
	fields := senderFields(contacts, derefStr(msg.From), addresses)
	sender := stringOr(fields["sender"], "?")
	body := truncateStr(derefStr(msg.MessageBody), 120)
	fmt.Printf(">> [%s] %s: %s%s\n", convLabel, sender, body, formatLocation(msg.UserLocation))
	if msg.ReferencePoint != nil && msg.ReferencePoint.LatitudeDegrees != nil {
		fmt.Printf("   REF%s\n", formatLocation(msg.ReferencePoint))
	}
	if msg.MapShareUrl != nil {
		fmt.Printf("   MapShare: %s\n", *msg.MapShareUrl)
	}
	if msg.LiveTrackUrl != nil {
		fmt.Printf("   LiveTrack: %s\n", *msg.LiveTrackUrl)
	}
	if mediaCmd := formatMediaCmd(msg.ConversationID, msg.MessageID, msg.MediaID, msg.MediaType); mediaCmd != "" {
		fmt.Printf("   %s\n", mediaCmd)
	}
}

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

func derefStatus(s *gm.MessageStatus) string {
	if s == nil {
		return "?"
	}
	return string(*s)
}
