package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"github.com/spf13/cobra"
)

var membersCmd = &cobra.Command{
	Use:   "members CONVERSATION_ID",
	Short: "Show members of a conversation",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		convID, err := uuid.Parse(args[0])
		if err != nil {
			return fmt.Errorf("invalid conversation ID: %w", err)
		}

		auth := getAuth()
		contacts := LoadContacts(sessionDir)

		api := gm.NewHermesAPI(auth)
		defer api.Close()

		result, err := api.GetConversationMembers(context.Background(), convID)
		if err != nil {
			return err
		}

		if len(result) == 0 {
			if useYAML {
				yamlOut([]any{})
			} else {
				fmt.Println("No members found.")
			}
			return nil
		}

		if useYAML {
			var rows []map[string]any
			for _, m := range result {
				rows = append(rows, map[string]any{
					"user_id":    derefStr(m.UserIdentifier),
					"name":       derefStr(m.FriendlyName),
					"local_name": contacts.ResolveMember(derefStr(m.UserIdentifier)),
					"address":    derefStr(m.Address),
				})
			}
			yamlOut(rows)
		} else {
			fmt.Printf("%-38s %-20s %-20s %s\n", "USER ID", "NAME", "LOCAL NAME", "ADDRESS")
			fmt.Println(repeat("-", 100))
			for _, m := range result {
				uid := stringOr(derefStr(m.UserIdentifier), "?")
				name := stringOr(derefStr(m.FriendlyName), "?")
				localName := contacts.ResolveMember(derefStr(m.UserIdentifier))
				addr := stringOr(derefStr(m.Address), "?")
				fmt.Printf("%-38s %-20s %-20s %s\n", uid, name, localName, addr)
			}
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(membersCmd)
}
