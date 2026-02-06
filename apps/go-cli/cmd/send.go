package cmd

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var sendCmd = &cobra.Command{
	Use:   "send",
	Short: "Send a message to a recipient",
	Long:  "Send a message to a recipient. Use --file / -f to attach a media file (AVIF image or OGG audio).",
	RunE: func(cmd *cobra.Command, args []string) error {
		recipient, _ := cmd.Flags().GetString("to")
		messageBody, _ := cmd.Flags().GetString("message")
		lat, _ := cmd.Flags().GetFloat64("lat")
		lon, _ := cmd.Flags().GetFloat64("lon")
		elevation, _ := cmd.Flags().GetFloat64("elevation")
		filePath, _ := cmd.Flags().GetString("file")
		latSet := cmd.Flags().Changed("lat")
		lonSet := cmd.Flags().Changed("lon")
		elevSet := cmd.Flags().Changed("elevation")

		// Validate lat/lon pairing
		if latSet != lonSet {
			fmt.Fprintln(os.Stderr, "Error: --lat and --lon must both be provided.")
			os.Exit(2)
		}
		if elevSet && !latSet {
			fmt.Fprintln(os.Stderr, "Error: --elevation requires --lat and --lon.")
			os.Exit(2)
		}

		var opts []gm.SendMessageOption
		if latSet {
			opts = append(opts, gm.WithUserLocation(gm.UserLocation{
				LatitudeDegrees:  &lat,
				LongitudeDegrees: &lon,
				ElevationMeters:  ptrIf(elevSet, elevation),
			}))
		}

		auth := getAuth()
		api := gm.NewHermesAPI(auth)
		defer api.Close()

		ctx := context.Background()
		var result *gm.SendMessageV2Response
		var err error

		if filePath != "" {
			ext := strings.ToLower(filepath.Ext(filePath))
			extMap := map[string]gm.MediaType{
				".avif": gm.MediaTypeImageAvif,
				".ogg":  gm.MediaTypeAudioOgg,
				".oga":  gm.MediaTypeAudioOgg,
			}
			mediaType, ok := extMap[ext]
			if !ok {
				fmt.Fprintf(os.Stderr, "Error: Unsupported file extension '%s'. Supported: .avif, .ogg, .oga\n", ext)
				os.Exit(2)
			}
			fileData, err := os.ReadFile(filePath)
			if err != nil {
				return fmt.Errorf("reading file: %w", err)
			}
			result, err = api.SendMediaMessage(ctx, []string{recipient}, messageBody, fileData, mediaType, opts...)
			if err != nil {
				return err
			}
		} else {
			result, err = api.SendMessage(ctx, []string{recipient}, messageBody, opts...)
			if err != nil {
				return err
			}
		}

		if useYAML {
			yamlOut(map[string]string{
				"message_id":      result.MessageID.String(),
				"conversation_id": result.ConversationID.String(),
			})
		} else {
			fmt.Printf("Sent! messageId=%s conversationId=%s\n", result.MessageID, result.ConversationID)
		}
		return nil
	},
}

func init() {
	sendCmd.Flags().StringP("to", "t", "", "Recipient address (phone or user ID)")
	sendCmd.Flags().StringP("message", "m", "", "Message body to send")
	sendCmd.Flags().Float64("lat", 0, "GPS latitude in degrees")
	sendCmd.Flags().Float64("lon", 0, "GPS longitude in degrees")
	sendCmd.Flags().Float64("elevation", 0, "Elevation in meters")
	sendCmd.Flags().StringP("file", "f", "", "Path to a media file to attach (AVIF image or OGG audio)")
	sendCmd.MarkFlagRequired("to")
	sendCmd.MarkFlagRequired("message")
	rootCmd.AddCommand(sendCmd)
}

func ptrIf(cond bool, v float64) *float64 {
	if cond {
		return &v
	}
	return nil
}
