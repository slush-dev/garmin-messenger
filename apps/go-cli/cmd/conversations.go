package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var conversationsCmd = &cobra.Command{
	Use:   "conversations",
	Short: "List recent conversations",
	RunE: func(cmd *cobra.Command, args []string) error {
		limit, _ := cmd.Flags().GetInt("limit")
		auth := getAuth()
		contacts := LoadContacts(sessionDir)

		api := gm.NewHermesAPI(auth)
		defer api.Close()

		convos, err := api.GetConversations(context.Background(), gm.WithLimit(limit))
		if err != nil {
			return err
		}

		if len(convos.Conversations) == 0 {
			if useYAML {
				yamlOut([]any{})
			} else {
				fmt.Println("No conversations found.")
			}
			return nil
		}

		if useYAML {
			var rows []map[string]any
			for _, c := range convos.Conversations {
				cid := c.ConversationID.String()
				members := make([]string, len(c.MemberIDs))
				for i, mid := range c.MemberIDs {
					if name := resolveMember(contacts, mid); name != "" {
						members[i] = name
					} else {
						members[i] = mid
					}
				}
				var updated *string
				if !c.UpdatedDate.IsZero() {
					s := c.UpdatedDate.Format("2006-01-02T15:04:05Z07:00")
					updated = &s
				}
				rows = append(rows, map[string]any{
					"conversation_id": cid,
					"name":            contacts.ResolveConversation(cid),
					"members":         members,
					"updated":         updated,
					"muted":           c.IsMuted,
				})
			}
			yamlOut(rows)
		} else {
			fmt.Printf("%-38s %-20s %-40s %-26s %s\n", "CONVERSATION ID", "NAME", "MEMBERS", "UPDATED", "MUTED")
			fmt.Println(repeat("-", 130))
			for _, c := range convos.Conversations {
				cid := c.ConversationID.String()
				convName := contacts.ResolveConversation(cid)
				var memberNames []string
				for _, mid := range c.MemberIDs {
					if name := resolveMember(contacts, mid); name != "" {
						memberNames = append(memberNames, name)
					} else {
						memberNames = append(memberNames, mid)
					}
				}
				members := joinStrings(memberNames, ", ")
				updated := "?"
				if !c.UpdatedDate.IsZero() {
					updated = c.UpdatedDate.Format("2006-01-02 15:04:05")
				}
				muted := "no"
				if c.IsMuted {
					muted = "yes"
				}
				fmt.Printf("%-38s %-20s %-40s %-26s %s\n", cid, convName, members, updated, muted)
			}
		}
		return nil
	},
}

func init() {
	conversationsCmd.Flags().IntP("limit", "n", 20, "Max conversations to fetch")
	rootCmd.AddCommand(conversationsCmd)
}

func resolveMember(contacts *Contacts, memberID string) string {
	name := contacts.ResolveMember(memberID)
	if name != "" {
		return name
	}
	if len(memberID) > 0 && memberID[0] == '+' {
		return contacts.ResolveMember(gm.PhoneToHermesUserID(memberID))
	}
	return ""
}

func joinStrings(ss []string, sep string) string {
	result := ""
	for i, s := range ss {
		if i > 0 {
			result += sep
		}
		result += s
	}
	return result
}

func repeat(s string, count int) string {
	result := ""
	for i := 0; i < count; i++ {
		result += s
	}
	return result
}
