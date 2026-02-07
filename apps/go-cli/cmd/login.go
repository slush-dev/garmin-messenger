package cmd

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"strings"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/slush-dev/garmin-messenger/fcm"
	"github.com/spf13/cobra"
)

type loginPNSUpdater interface {
	UpdatePnsHandle(ctx context.Context, pnsHandle string) error
}

type loginFCMClient interface {
	Register(ctx context.Context) (string, error)
}

var newLoginFCMClient = func(sessionDir string) loginFCMClient {
	return fcm.NewClient(sessionDir)
}

func registerFCMForLogin(ctx context.Context, auth loginPNSUpdater, sessionDir string, useYAML bool, stdout, stderr io.Writer) {
	// FCM registration — non-fatal; falls back to dummy token on failure
	fcm := newLoginFCMClient(sessionDir)
	fcmToken, fcmErr := fcm.Register(ctx)
	if fcmErr != nil {
		fmt.Fprintf(stderr, "Warning: FCM registration failed: %v\n", fcmErr)
		fmt.Fprintln(stderr, "Push notifications will not work. SignalR real-time still available.")
	} else {
		if err := auth.UpdatePnsHandle(ctx, fcmToken); err != nil {
			fmt.Fprintf(stderr, "Warning: Failed to update push notification token: %v\n", err)
		} else if !useYAML {
			fmt.Fprintln(stdout, "FCM push notifications registered.")
		}
	}
}

var loginCmd = &cobra.Command{
	Use:   "login",
	Short: "Authenticate via SMS OTP and save the session",
	RunE: func(cmd *cobra.Command, args []string) error {
		phone, _ := cmd.Flags().GetString("phone")
		deviceName, _ := cmd.Flags().GetString("device-name")

		auth := gm.NewHermesAuth(gm.WithSessionDir(sessionDir))
		ctx := context.Background()

		if phone == "" {
			fmt.Print("Phone number (with country code, e.g. +1234567890): ")
			scanner := bufio.NewScanner(os.Stdin)
			if scanner.Scan() {
				phone = strings.TrimSpace(scanner.Text())
			}
		}

		if !useYAML {
			fmt.Printf("Requesting SMS OTP for %s ...\n", phone)
		}

		otpReq, err := auth.RequestOTP(ctx, phone, deviceName)
		if err != nil {
			return fmt.Errorf("requesting OTP: %w", err)
		}

		fmt.Print("Enter SMS OTP code: ")
		scanner := bufio.NewScanner(os.Stdin)
		var otpCode string
		if scanner.Scan() {
			otpCode = strings.TrimSpace(scanner.Text())
		}

		if err := auth.ConfirmOTP(ctx, otpReq, otpCode); err != nil {
			return fmt.Errorf("confirming OTP: %w", err)
		}

		if auth.AccessToken == "" {
			fmt.Fprintln(os.Stderr, "Authentication failed — no access token.")
			os.Exit(1)
		}

		registerFCMForLogin(ctx, auth, sessionDir, useYAML, os.Stdout, os.Stderr)

		if useYAML {
			yamlOut(map[string]string{
				"instance_id": auth.InstanceID,
				"session_dir": sessionDir,
			})
		} else {
			fmt.Printf("Authenticated! instance=%s\n", auth.InstanceID)
			fmt.Printf("Session saved to %s\n", sessionDir)
		}
		return nil
	},
}

func init() {
	loginCmd.Flags().String("phone", "", `Phone number with country code (e.g. "+1234567890")`)
	loginCmd.Flags().String("device-name", "garmin-messenger", "Device identifier shown on the account")
	rootCmd.AddCommand(loginCmd)
}
