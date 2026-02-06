package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"github.com/spf13/cobra"
)

var messagesCmd = &cobra.Command{
	Use:   "messages CONVERSATION_ID",
	Short: "Show messages from a conversation",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		convIDStr := args[0]
		convID, err := uuid.Parse(convIDStr)
		if err != nil {
			return fmt.Errorf("invalid conversation ID: %w", err)
		}
		limit, _ := cmd.Flags().GetInt("limit")
		showUUID, _ := cmd.Flags().GetBool("uuid")

		auth := getAuth()
		contacts := LoadContacts(sessionDir)
		addresses := LoadAddresses(sessionDir)

		api := gm.NewHermesAPI(auth)
		defer api.Close()

		detail, err := api.GetConversationDetail(context.Background(), convID, gm.WithDetailLimit(limit))
		if err != nil {
			return err
		}

		if len(detail.Messages) == 0 {
			if useYAML {
				yamlOut([]any{})
			} else {
				fmt.Println("No messages found.")
			}
			return nil
		}

		if useYAML {
			var rows []map[string]any
			for _, m := range detail.Messages {
				row := make(map[string]any)
				if showUUID {
					row["message_id"] = m.MessageID.String()
				}
				fields := senderFields(contacts, derefStr(m.From), addresses)
				row["sender"] = fields["sender"]
				if showUUID {
					if id, ok := fields["sender_id"]; ok {
						row["sender_id"] = id
					}
				}
				if phone, ok := fields["sender_phone"]; ok {
					row["sender_phone"] = phone
				}
				row["body"] = derefStr(m.MessageBody)
				if m.SentAt != nil {
					row["sent_at"] = m.SentAt.Format("2006-01-02T15:04:05Z07:00")
				}
				if m.UserLocation != nil && m.UserLocation.LatitudeDegrees != nil {
					row["location"] = map[string]any{
						"latitude":  *m.UserLocation.LatitudeDegrees,
						"longitude": *m.UserLocation.LongitudeDegrees,
						"elevation": derefFloat(m.UserLocation.ElevationMeters),
					}
				}
				if m.ReferencePoint != nil && m.ReferencePoint.LatitudeDegrees != nil {
					row["reference_point"] = map[string]any{
						"latitude":  *m.ReferencePoint.LatitudeDegrees,
						"longitude": *m.ReferencePoint.LongitudeDegrees,
						"elevation": derefFloat(m.ReferencePoint.ElevationMeters),
					}
				}
				if m.MapShareUrl != nil {
					row["map_share_url"] = *m.MapShareUrl
				}
				if m.LiveTrackUrl != nil {
					row["live_track_url"] = *m.LiveTrackUrl
				}
				if hasMedia(m.MediaID) {
					if !showUUID {
						row["message_id"] = m.MessageID.String()
					}
					row["conversation_id"] = convID.String()
					row["media_id"] = m.MediaID.String()
					if m.MediaType != nil {
						row["media_type"] = string(*m.MediaType)
					}
				}
				rows = append(rows, row)
			}
			yamlOut(rows)
		} else {
			convLabel := contacts.ResolveConversation(convIDStr)
			if convLabel == "" {
				convLabel = convIDStr
			}
			fmt.Printf("Messages in %s (showing up to %d):\n\n", convLabel, limit)
			for _, m := range detail.Messages {
				fields := senderFields(contacts, derefStr(m.From), addresses)
				sender := stringOr(fields["sender"], "?")
				body := truncateStr(derefStr(m.MessageBody), 120)
				sent := "?"
				if m.SentAt != nil {
					sent = m.SentAt.Format("2006-01-02 15:04:05")
				}
				loc := formatLocation(m.UserLocation)
				if showUUID {
					fmt.Printf("  [%s] (%s) %s: %s%s\n", sent, m.MessageID, sender, body, loc)
				} else {
					fmt.Printf("  [%s] %s: %s%s\n", sent, sender, body, loc)
				}
				if m.ReferencePoint != nil && m.ReferencePoint.LatitudeDegrees != nil {
					fmt.Printf("    REF%s\n", formatLocation(m.ReferencePoint))
				}
				if m.MapShareUrl != nil {
					fmt.Printf("    MapShare: %s\n", *m.MapShareUrl)
				}
				if m.LiveTrackUrl != nil {
					fmt.Printf("    LiveTrack: %s\n", *m.LiveTrackUrl)
				}
				if mediaCmd := formatMediaCmd(convID, m.MessageID, m.MediaID, m.MediaType); mediaCmd != "" {
					fmt.Printf("    %s\n", mediaCmd)
				}
			}
		}
		return nil
	},
}

func init() {
	messagesCmd.Flags().IntP("limit", "n", 20, "Max messages to fetch")
	messagesCmd.Flags().Bool("uuid", false, "Show message_id and sender_id in output")
	rootCmd.AddCommand(messagesCmd)
}

func senderFields(contacts *Contacts, from string, addresses map[string]string) map[string]string {
	fields := make(map[string]string)
	if from == "" {
		return fields
	}
	if len(from) > 0 && from[0] == '+' {
		uid := gm.PhoneToHermesUserID(from)
		name := contacts.ResolveMember(uid)
		if name == "" {
			name = contacts.ResolveMember(from)
		}
		if name == "" {
			name = from
		}
		fields["sender"] = name
		fields["sender_id"] = uid
		fields["sender_phone"] = from
	} else {
		name := contacts.ResolveMember(from)
		if name == "" {
			name = from
		}
		fields["sender"] = name
		fields["sender_id"] = from
		if phone, ok := addresses[from]; ok && phone != "" {
			fields["sender_phone"] = phone
		}
	}
	return fields
}

func derefStr(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}

func derefFloat(f *float64) any {
	if f == nil {
		return nil
	}
	return *f
}

func stringOr(s string, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}

func truncateStr(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}
