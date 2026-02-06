package cmd

import (
	"context"
	"fmt"
	"path/filepath"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var syncContactsCmd = &cobra.Command{
	Use:   "sync-contacts",
	Short: "Sync contacts from the server into local contacts.yaml",
	Long: `Sync contacts from the server into local contacts.yaml.

Fetches conversations and their members, then merges into the local
contacts file. Existing non-empty names are preserved; run this to
discover new contacts, then edit ~/.garmin-messenger/contacts.yaml
to assign friendly names.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		limit, _ := cmd.Flags().GetInt("limit")
		auth := getAuth()
		contacts := LoadContacts(sessionDir)

		api := gm.NewHermesAPI(auth)
		defer api.Close()

		ctx := context.Background()
		convos, err := api.GetConversations(ctx, gm.WithLimit(limit))
		if err != nil {
			return err
		}

		var apiMembers []struct{ Key, Name string }
		var apiAddresses []struct{ UUID, Phone string }
		var convIDs []string

		for _, c := range convos.Conversations {
			cid := c.ConversationID.String()
			convIDs = append(convIDs, cid)
			membersList, err := api.GetConversationMembers(ctx, c.ConversationID)
			if err != nil {
				return err
			}
			for _, m := range membersList {
				uid := derefStr(m.UserIdentifier)
				if uid == "" {
					continue
				}
				suggested := ""
				fn := derefStr(m.FriendlyName)
				if fn != "" && fn != "?" {
					suggested = fn
				} else if addr := derefStr(m.Address); addr != "" {
					suggested = addr
				}
				apiMembers = append(apiMembers, struct{ Key, Name string }{uid, suggested})
				if addr := derefStr(m.Address); addr != "" {
					apiAddresses = append(apiAddresses, struct{ UUID, Phone string }{uid, addr})
				}
			}
		}

		contacts.Members = MergeMembers(contacts.Members, apiMembers)
		contacts.Conversations = MergeConversations(contacts.Conversations, convIDs)
		if err := SaveContacts(sessionDir, contacts); err != nil {
			return fmt.Errorf("saving contacts: %w", err)
		}

		existingAddresses := LoadAddresses(sessionDir)
		mergedAddresses := MergeAddresses(existingAddresses, apiAddresses)
		if err := SaveAddresses(sessionDir, mergedAddresses); err != nil {
			return fmt.Errorf("saving addresses: %w", err)
		}

		if useYAML {
			yamlOut(map[string]any{
				"members":       len(contacts.Members),
				"conversations": len(contacts.Conversations),
				"contacts_file": filepath.Join(sessionDir, "contacts.yaml"),
			})
		} else {
			fmt.Printf("Synced %d members, %d conversations.\n", len(contacts.Members), len(contacts.Conversations))
			fmt.Printf("Edit %s to set friendly names.\n", filepath.Join(sessionDir, "contacts.yaml"))
		}
		return nil
	},
}

func init() {
	syncContactsCmd.Flags().IntP("limit", "n", 100, "Max conversations to fetch")
	rootCmd.AddCommand(syncContactsCmd)
}
