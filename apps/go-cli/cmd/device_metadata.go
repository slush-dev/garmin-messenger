package cmd

import (
	"context"
	"fmt"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"github.com/spf13/cobra"
)

var deviceMetadataCmd = &cobra.Command{
	Use:   "device-metadata CONVERSATION_ID MSG_ID [MSG_ID ...]",
	Short: "Show satellite device metadata for messages",
	Args:  cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		convID, err := uuid.Parse(args[0])
		if err != nil {
			return fmt.Errorf("invalid conversation ID: %w", err)
		}
		messageIDs := args[1:]

		var ids []gm.SimpleCompoundMessageId
		for _, mid := range messageIDs {
			msgID, err := uuid.Parse(mid)
			if err != nil {
				return fmt.Errorf("invalid message ID %q: %w", mid, err)
			}
			ids = append(ids, gm.SimpleCompoundMessageId{
				MessageID:      msgID,
				ConversationID: convID,
			})
		}

		auth := getAuth()
		api := gm.NewHermesAPI(auth)
		defer api.Close()

		result, err := api.GetMessageDeviceMetadata(context.Background(), ids)
		if err != nil {
			return err
		}

		if len(result) == 0 {
			if useYAML {
				yamlOut([]any{})
			} else {
				fmt.Println("No device metadata found.")
			}
			return nil
		}

		if useYAML {
			var rows []map[string]any
			for i, md := range result {
				entry := md.DeviceMetadata
				msgLabel := messageIDs[i]
				if entry != nil && entry.MessageID != nil {
					msgLabel = entry.MessageID.MessageID.String()
				}
				var devList []map[string]any
				devices := []gm.DeviceInstanceMetadata{}
				if entry != nil && entry.DeviceMessageMetadata != nil {
					devices = entry.DeviceMessageMetadata
				}
				for _, dev := range devices {
					devDict := map[string]any{
						"device_instance_id": uuidToStr(dev.DeviceInstanceID),
						"imei":               dev.IMEI,
					}
					var sats []map[string]any
					for _, sat := range dev.InReachMessageMetadata {
						satDict := map[string]any{"text": derefStr(sat.Text)}
						if sat.Mtmsn != nil {
							satDict["mtmsn"] = *sat.Mtmsn
						}
						if sat.OtaUuid != nil {
							satDict["ota_uuid"] = sat.OtaUuid.String()
						}
						sats = append(sats, satDict)
					}
					if len(sats) > 0 {
						devDict["inreach_metadata"] = sats
					}
					devList = append(devList, devDict)
				}
				rows = append(rows, map[string]any{
					"message_id": msgLabel,
					"devices":    devList,
				})
			}
			yamlOut(rows)
		} else {
			for i, md := range result {
				entry := md.DeviceMetadata
				msgLabel := messageIDs[i]
				if entry != nil && entry.MessageID != nil {
					msgLabel = entry.MessageID.MessageID.String()
				}
				devices := []gm.DeviceInstanceMetadata{}
				if entry != nil && entry.DeviceMessageMetadata != nil {
					devices = entry.DeviceMessageMetadata
				}
				if len(devices) == 0 {
					fmt.Printf("Message:  %s  — no satellite device info\n", msgLabel)
					continue
				}
				fmt.Printf("Message:  %s\n", msgLabel)
				for _, dev := range devices {
					imeiStr := "?"
					if dev.IMEI != nil {
						imeiStr = fmt.Sprintf("%015d", *dev.IMEI)
					}
					fmt.Printf("  Device: %s\n", uuidToStr(dev.DeviceInstanceID))
					fmt.Printf("  IMEI:   %s\n", imeiStr)
					for _, sat := range dev.InReachMessageMetadata {
						fmt.Printf("    Text:  %s\n", stringOr(derefStr(sat.Text), "?"))
						if sat.Mtmsn != nil {
							fmt.Printf("    MTMSN: %d\n", *sat.Mtmsn)
						}
						if sat.OtaUuid != nil {
							fmt.Printf("    OTA:   %s\n", sat.OtaUuid.String())
						}
					}
				}
			}
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(deviceMetadataCmd)
}

func uuidToStr(u *uuid.UUID) string {
	if u == nil {
		return "?"
	}
	return u.String()
}
