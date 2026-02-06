package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"github.com/spf13/cobra"
)

var muteCmd = &cobra.Command{
	Use:   "mute CONVERSATION_ID",
	Short: "Mute a conversation (suppress notifications). Use --off to unmute.",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		convID, err := uuid.Parse(args[0])
		if err != nil {
			return fmt.Errorf("invalid conversation ID: %w", err)
		}
		unmute, _ := cmd.Flags().GetBool("off")
		muted := !unmute

		auth := getAuth()
		api := gm.NewHermesAPI(auth)
		defer api.Close()

		if err := api.MuteConversation(context.Background(), convID, muted); err != nil {
			return err
		}

		if useYAML {
			yamlOut(map[string]any{
				"conversation_id": args[0],
				"muted":           muted,
			})
		} else {
			action := "Muted"
			if unmute {
				action = "Unmuted"
			}
			fmt.Printf("%s conversation %s.\n", action, args[0])
		}
		return nil
	},
}

func init() {
	muteCmd.Flags().Bool("off", false, "Unmute instead of mute")
	rootCmd.AddCommand(muteCmd)
}
