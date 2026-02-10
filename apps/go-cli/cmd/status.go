package cmd

import (
	"context"
	"fmt"
	"time"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show current account login and registration status",
	RunE: func(cmd *cobra.Command, args []string) error {
		ctx := context.Background()

		auth := gm.NewHermesAuth(gm.WithSessionDir(sessionDir))
		resumeErr := auth.Resume(ctx)

		loggedIn := resumeErr == nil
		var appCount, deviceCount int
		var serverErr error

		// If we have a valid session, verify it against the server.
		if loggedIn {
			var regs map[string]interface{}
			regs, serverErr = auth.GetRegistrations(ctx)
			if serverErr == nil {
				if apps, ok := regs["apps"].([]interface{}); ok {
					appCount = len(apps)
				}
				if devices, ok := regs["inReach"].([]interface{}); ok {
					deviceCount = len(devices)
				}
			}
		}

		if useYAML {
			status := map[string]any{
				"logged_in":   loggedIn,
				"session_dir": sessionDir,
			}
			if loggedIn {
				status["instance_id"] = auth.InstanceID
				status["token_expires_at"] = time.Unix(int64(auth.ExpiresAt), 0).UTC().Format(time.RFC3339)
				if serverErr != nil {
					status["server_error"] = serverErr.Error()
				} else {
					status["app_registrations"] = appCount
					status["inreach_devices"] = deviceCount
				}
			} else {
				status["error"] = resumeErr.Error()
			}
			yamlOut(status)
		} else {
			fmt.Printf("Session dir:     %s\n", sessionDir)
			if !loggedIn {
				fmt.Printf("Logged in:       no (%v)\n", resumeErr)
				return nil
			}
			fmt.Printf("Logged in:       yes\n")
			fmt.Printf("Instance ID:     %s\n", auth.InstanceID)
			fmt.Printf("Token expires:   %s\n", formatExpiry(auth.ExpiresAt))
			if serverErr != nil {
				fmt.Printf("Server:          error (%v)\n", serverErr)
			} else {
				fmt.Printf("Registrations:   %d app(s), %d device(s)\n", appCount, deviceCount)
			}
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(statusCmd)
}

func formatExpiry(expiresAt float64) string {
	t := time.Unix(int64(expiresAt), 0)
	remaining := time.Until(t).Truncate(time.Second)
	if remaining <= 0 {
		return t.Local().Format("2006-01-02 15:04:05") + " (expired)"
	}
	return t.Local().Format("2006-01-02 15:04:05") + fmt.Sprintf(" (%s remaining)", remaining)
}

