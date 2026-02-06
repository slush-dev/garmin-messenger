package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var listenCmd = &cobra.Command{
	Use:   "listen",
	Short: "Listen for incoming messages in real time (Ctrl+C to stop)",
	RunE: func(cmd *cobra.Command, args []string) error {
		showUUID, _ := cmd.Flags().GetBool("uuid")
		auth := getAuth()
		contacts := LoadContacts(sessionDir)
		addresses := LoadAddresses(sessionDir)

		sr := gm.NewHermesSignalR(auth)

		sr.OnMessage(func(msg gm.MessageModel) {
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
			} else {
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
			fmt.Println("SignalR connected.")
		})
		sr.OnClose(func() {
			fmt.Println("SignalR disconnected.")
		})
		sr.OnError(func(err error) {
			fmt.Fprintf(os.Stderr, "SignalR error: %v\n", err)
		})

		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()

		if err := sr.Start(ctx); err != nil {
			return err
		}

		fmt.Println("Listening for messages (Ctrl+C to stop) ...")

		<-ctx.Done()
		fmt.Println("\nShutting down ...")
		sr.Stop()
		return nil
	},
}

func init() {
	listenCmd.Flags().Bool("uuid", false, "Show conversation_id, message_id, and sender_id in output")
	rootCmd.AddCommand(listenCmd)
}

func derefStatus(s *gm.MessageStatus) string {
	if s == nil {
		return "?"
	}
	return string(*s)
}
