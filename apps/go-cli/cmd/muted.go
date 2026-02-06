package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var mutedCmd = &cobra.Command{
	Use:   "muted",
	Short: "List muted conversations with expiry",
	RunE: func(cmd *cobra.Command, args []string) error {
		auth := getAuth()
		api := gm.NewHermesAPI(auth)
		defer api.Close()

		result, err := api.GetMutedConversations(context.Background())
		if err != nil {
			return err
		}

		if len(result) == 0 {
			if useYAML {
				yamlOut([]any{})
			} else {
				fmt.Println("No muted conversations.")
			}
			return nil
		}

		if useYAML {
			var rows []map[string]any
			for _, c := range result {
				var expires *string
				if c.Expires != nil {
					s := c.Expires.Format("2006-01-02T15:04:05Z07:00")
					expires = &s
				}
				rows = append(rows, map[string]any{
					"conversation_id": c.ConversationID.String(),
					"expires":         expires,
				})
			}
			yamlOut(rows)
		} else {
			fmt.Printf("%-38s %s\n", "CONVERSATION ID", "EXPIRES")
			fmt.Println(repeat("-", 65))
			for _, c := range result {
				expires := "never"
				if c.Expires != nil {
					expires = c.Expires.Format("2006-01-02 15:04:05")
				}
				fmt.Printf("%-38s %s\n", c.ConversationID, expires)
			}
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(mutedCmd)
}
