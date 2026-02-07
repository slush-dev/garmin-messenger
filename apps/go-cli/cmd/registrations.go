package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"text/tabwriter"

	"github.com/spf13/cobra"
)

var registrationsCmd = &cobra.Command{
	Use:   "registrations",
	Short: "Manage device/app registrations",
}

var registrationsListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all registered devices and apps",
	Long: `List all devices and apps registered to your Hermes account.
This includes mobile apps, InReach devices, and Garmin OS apps.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		auth := getAuth()
		ctx := context.Background()

		registrations, err := auth.GetRegistrations(ctx)
		if err != nil {
			return fmt.Errorf("getting registrations: %w", err)
		}

		if useYAML {
			yamlOut(registrations)
			return nil
		}

		// Extract app registrations
		apps, ok := registrations["apps"].([]interface{})
		if !ok || len(apps) == 0 {
			fmt.Println("No app registrations found.")
		} else {
			fmt.Printf("App Registrations (%d):\n\n", len(apps))
			w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
			fmt.Fprintln(w, "INSTANCE ID\tPLATFORM\tFIRST REGISTERED\tLAST SEEN\tPNS HANDLE")
			fmt.Fprintln(w, strings.Repeat("-", 140))

			for _, app := range apps {
				appMap, _ := app.(map[string]interface{})
				instanceID, _ := appMap["instanceId"].(string)
				platform, _ := appMap["platform"].(string)
				firstRegistered, _ := appMap["firstRegistered"].(string)
				lastSeen, _ := appMap["lastSeen"].(string)
				pnsHandle, _ := appMap["pnsHandle"].(string)

				// Truncate long values
				if len(instanceID) > 36 {
					instanceID = instanceID[:36]
				}
				if len(pnsHandle) > 50 {
					pnsHandle = pnsHandle[:47] + "..."
				}
				if len(firstRegistered) > 19 {
					firstRegistered = firstRegistered[:19]
				}
				if len(lastSeen) > 19 {
					lastSeen = lastSeen[:19]
				}

				fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n",
					instanceID, platform, firstRegistered, lastSeen, pnsHandle)
			}
			w.Flush()
			fmt.Println()
		}

		// Extract InReach devices
		devices, ok := registrations["inReach"].([]interface{})
		if ok && len(devices) > 0 {
			fmt.Printf("InReach Devices (%d):\n\n", len(devices))
			data, _ := json.MarshalIndent(devices, "", "  ")
			fmt.Println(string(data))
			fmt.Println()
		}

		// Extract Garmin OS apps
		osApps, ok := registrations["garminOSApps"].([]interface{})
		if ok && len(osApps) > 0 {
			fmt.Printf("Garmin OS Apps (%d):\n\n", len(osApps))
			data, _ := json.MarshalIndent(osApps, "", "  ")
			fmt.Println(string(data))
			fmt.Println()
		}

		return nil
	},
}

var registrationsDeleteCmd = &cobra.Command{
	Use:   "delete <instance-id>",
	Short: "Delete a specific app registration",
	Long: `Delete a specific app registration by instance ID.
Use 'garmin-messenger registrations list' to see available instance IDs.

This is useful for cleaning up stale FCM tokens that may interfere with
push notification delivery.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		instanceID := args[0]
		auth := getAuth()
		ctx := context.Background()

		confirm, _ := cmd.Flags().GetBool("yes")
		if !confirm {
			fmt.Printf("Delete registration %s? (y/N): ", instanceID)
			var response string
			fmt.Scanln(&response)
			if response != "y" && response != "yes" {
				fmt.Println("Cancelled.")
				return nil
			}
		}

		if err := auth.DeleteAppRegistration(ctx, instanceID); err != nil {
			return fmt.Errorf("deleting registration: %w", err)
		}

		fmt.Printf("Deleted registration: %s\n", instanceID)
		return nil
	},
}

var registrationsCleanupCmd = &cobra.Command{
	Use:   "cleanup",
	Short: "Delete ALL app registrations",
	Long: `Delete ALL app registrations for the current account.
This is useful for cleaning up multiple stale FCM tokens.

WARNING: This will delete all app registrations. You will need to run
'garmin-messenger login' to re-register after cleanup.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		auth := getAuth()
		ctx := context.Background()

		// Get all registrations
		registrations, err := auth.GetRegistrations(ctx)
		if err != nil {
			return fmt.Errorf("getting registrations: %w", err)
		}

		apps, ok := registrations["apps"].([]interface{})
		if !ok || len(apps) == 0 {
			fmt.Println("No app registrations found.")
			return nil
		}

		// Extract instance IDs
		var instanceIDs []string
		for _, app := range apps {
			appMap, _ := app.(map[string]interface{})
			if instanceID, ok := appMap["instanceId"].(string); ok {
				instanceIDs = append(instanceIDs, instanceID)
			}
		}

		if len(instanceIDs) == 0 {
			fmt.Println("No instance IDs found.")
			return nil
		}

		fmt.Printf("Found %d app registration(s) to delete:\n", len(instanceIDs))
		for i, id := range instanceIDs {
			fmt.Printf("  [%d] %s\n", i+1, id)
		}
		fmt.Println()

		confirm, _ := cmd.Flags().GetBool("yes")
		if !confirm {
			fmt.Print("Delete ALL registrations? (yes/no): ")
			var response string
			fmt.Scanln(&response)
			if response != "yes" {
				fmt.Println("Cancelled.")
				return nil
			}
		}

		// Delete each registration
		fmt.Println("Deleting registrations...")
		for _, id := range instanceIDs {
			fmt.Printf("  Deleting %s...", id)
			if err := auth.DeleteAppRegistration(ctx, id); err != nil {
				fmt.Printf(" FAILED: %v\n", err)
			} else {
				fmt.Printf(" OK\n")
			}
		}

		fmt.Println("\nDone. Re-register with: garmin-messenger login")
		return nil
	},
}

func init() {
	rootCmd.AddCommand(registrationsCmd)
	registrationsCmd.AddCommand(registrationsListCmd)
	registrationsCmd.AddCommand(registrationsDeleteCmd)
	registrationsCmd.AddCommand(registrationsCleanupCmd)

	registrationsDeleteCmd.Flags().BoolP("yes", "y", false, "Skip confirmation prompt")
	registrationsCleanupCmd.Flags().BoolP("yes", "y", false, "Skip confirmation prompt")
}
