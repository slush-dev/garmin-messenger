package cmd

import (
	"context"
	"fmt"
	"os"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"github.com/spf13/cobra"
)

var mediaCmd = &cobra.Command{
	Use:   "media CONVERSATION_ID MESSAGE_ID",
	Short: "Download a media attachment from a message",
	Long:  "Download a media attachment. If --media-id and --media-type are provided, skips fetching message details.",
	Args:  cobra.ExactArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		convID, err := uuid.Parse(args[0])
		if err != nil {
			return fmt.Errorf("invalid conversation ID: %w", err)
		}
		messageID, err := uuid.Parse(args[1])
		if err != nil {
			return fmt.Errorf("invalid message ID: %w", err)
		}

		output, _ := cmd.Flags().GetString("output")
		mediaIDStr, _ := cmd.Flags().GetString("media-id")
		mediaTypeStr, _ := cmd.Flags().GetString("media-type")

		auth := getAuth()
		api := gm.NewHermesAPI(auth)
		defer api.Close()

		ctx := context.Background()

		var msgUUID uuid.UUID
		var mediaID uuid.UUID
		var mediaType gm.MediaType

		if mediaIDStr != "" && mediaTypeStr != "" {
			// Use provided values directly — skip fetch
			mediaID, err = uuid.Parse(mediaIDStr)
			if err != nil {
				return fmt.Errorf("invalid --media-id: %w", err)
			}
			mediaType = gm.MediaType(mediaTypeStr)
			// uuid is the same as messageID in practice
			msgUUID = messageID
		} else {
			// Fetch conversation detail to find the message
			detail, err := api.GetConversationDetail(ctx, convID)
			if err != nil {
				return fmt.Errorf("fetching conversation: %w", err)
			}
			found := false
			for _, m := range detail.Messages {
				if m.MessageID == messageID {
					if m.MediaID == nil {
						return fmt.Errorf("message %s has no media attachment", messageID)
					}
					mediaID = *m.MediaID
					if m.MediaType != nil {
						mediaType = *m.MediaType
					}
					// Use UUID field if available, fall back to MessageID
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
				return fmt.Errorf("message %s not found in conversation %s", messageID, convID)
			}
		}

		data, err := api.DownloadMedia(ctx, msgUUID, mediaID, messageID, convID, mediaType)
		if err != nil {
			return err
		}

		// Determine output filename
		if output == "" {
			output = mediaID.String() + mediaExtension(mediaType)
		}

		if err := os.WriteFile(output, data, 0o644); err != nil {
			return fmt.Errorf("writing file: %w", err)
		}

		if useYAML {
			yamlOut(map[string]any{
				"file":       output,
				"bytes":      len(data),
				"media_type": string(mediaType),
			})
		} else {
			fmt.Printf("Downloaded %d bytes → %s\n", len(data), output)
		}
		return nil
	},
}

func init() {
	mediaCmd.Flags().StringP("output", "o", "", "Output file path (default: {media_id}.{ext})")
	mediaCmd.Flags().String("media-id", "", "Media ID (skip fetching message details)")
	mediaCmd.Flags().String("media-type", "", "Media type: ImageAvif or AudioOgg (skip fetching message details)")
	rootCmd.AddCommand(mediaCmd)
}
