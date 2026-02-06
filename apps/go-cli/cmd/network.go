package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var networkCmd = &cobra.Command{
	Use:   "network",
	Short: "Show network properties",
	RunE: func(cmd *cobra.Command, args []string) error {
		auth := getAuth()
		api := gm.NewHermesAPI(auth)
		defer api.Close()

		props, err := api.GetNetworkProperties(context.Background())
		if err != nil {
			return err
		}

		if useYAML {
			yamlOut(map[string]any{
				"data_constrained":   props.DataConstrained,
				"premium_messaging":  props.EnablesPremiumMessaging,
			})
		} else {
			fmt.Printf("Data constrained: %v\n", props.DataConstrained)
			fmt.Printf("Premium messaging: %v\n", props.EnablesPremiumMessaging)
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(networkCmd)
}
