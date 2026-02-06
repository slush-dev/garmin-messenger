package cmd

import (
	"fmt"
	"os"
	"strings"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/google/uuid"
	"gopkg.in/yaml.v3"
)

// yamlOut prints data as a YAML document to stdout.
func yamlOut(data any) {
	enc := yaml.NewEncoder(os.Stdout)
	enc.SetIndent(2)
	enc.Encode(data)
	enc.Close()
}

// formatLocation formats a UserLocation as '@ lat, lon[, elevM]' or empty string.
func formatLocation(loc *gm.UserLocation) string {
	if loc == nil || loc.LatitudeDegrees == nil || loc.LongitudeDegrees == nil {
		return ""
	}
	parts := fmt.Sprintf("%v, %v", *loc.LatitudeDegrees, *loc.LongitudeDegrees)
	if loc.ElevationMeters != nil {
		parts += fmt.Sprintf(", %vm", *loc.ElevationMeters)
	}
	return fmt.Sprintf("  [@ %s]", parts)
}

// hasMedia returns true if the media ID is non-nil and non-zero.
func hasMedia(mediaID *uuid.UUID) bool {
	return mediaID != nil && *mediaID != uuid.Nil
}

// formatMediaCmd returns a copy-pasteable download command for a media attachment.
// Returns "" if mediaID is nil or zero.
func formatMediaCmd(conversationID, messageID uuid.UUID, mediaID *uuid.UUID, mediaType *gm.MediaType) string {
	if !hasMedia(mediaID) {
		return ""
	}
	mt := ""
	if mediaType != nil {
		mt = string(*mediaType)
	}
	return fmt.Sprintf("garmin-messenger media %s %s --media-id %s --media-type %s",
		conversationID, messageID, *mediaID, mt)
}

// mediaExtension returns the file extension (with dot) for a MediaType.
func mediaExtension(mt gm.MediaType) string {
	switch mt {
	case gm.MediaTypeImageAvif:
		return ".avif"
	case gm.MediaTypeAudioOgg:
		return ".ogg"
	default:
		return ".bin"
	}
}

// printTable prints a simple formatted table header with separator.
func printTable(format string, width int, columns ...any) {
	fmt.Printf(format+"\n", columns...)
	fmt.Println(strings.Repeat("-", width))
}
