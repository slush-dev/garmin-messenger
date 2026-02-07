package cmd

import (
	"context"
	"fmt"
	"os"
	"os/signal"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/slush-dev/garmin-messenger/fcm"
	"github.com/spf13/cobra"
)

var fcmRegisterCmd = &cobra.Command{
	Use:   "fcm-register",
	Short: "Register for FCM push notifications (debug helper)",
	Long:  "Performs only the FCM registration step, useful for debugging push notification issues. Does not require an active Hermes session.",
	RunE: func(cmd *cobra.Command, args []string) error {
		updatePns, _ := cmd.Flags().GetBool("update-pns")

		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()

		fcmClient := fcm.NewClient(sessionDir)

		fmt.Fprintln(os.Stderr, "Registering with FCM...")
		token, err := fcmClient.Register(ctx)
		if err != nil {
			return fmt.Errorf("FCM registration failed: %w", err)
		}

		if useYAML {
			yamlOut(map[string]string{"fcm_token": token})
		} else {
			fmt.Printf("FCM token: %s\n", token)
		}

		if updatePns {
			auth := gm.NewHermesAuth(gm.WithSessionDir(sessionDir))
			if err := auth.Resume(ctx); err != nil {
				return fmt.Errorf("no active session to update PNS handle: %w", err)
			}
			if err := auth.UpdatePnsHandle(ctx, token); err != nil {
				return fmt.Errorf("failed to update PNS handle: %w", err)
			}
			fmt.Fprintln(os.Stderr, "PNS handle updated on server.")
		}

		return nil
	},
}

func init() {
	fcmRegisterCmd.Flags().Bool("update-pns", false, "Also update the PNS handle on the Hermes server (requires active session)")
	rootCmd.AddCommand(fcmRegisterCmd)
}
