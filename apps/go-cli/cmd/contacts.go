package cmd

import "github.com/slush-dev/garmin-messenger/apps/go-cli/internal/contacts"

// Type aliases so cmd/*.go files can use the short name.
type Contacts = contacts.Contacts

// Re-export contacts functions for use within the cmd package.
var (
	LoadContacts     = contacts.LoadContacts
	SaveContacts     = contacts.SaveContacts
	LoadAddresses    = contacts.LoadAddresses
	SaveAddresses    = contacts.SaveAddresses
	MergeMembers     = contacts.MergeMembers
	MergeConversations = contacts.MergeConversations
	MergeAddresses   = contacts.MergeAddresses
)
