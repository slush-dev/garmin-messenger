package cmd

import (
	"fmt"
	"os"
	"strings"

	gm "github.com/slush-dev/garmin-messenger"
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

// printTable prints a simple formatted table header with separator.
func printTable(format string, width int, columns ...any) {
	fmt.Printf(format+"\n", columns...)
	fmt.Println(strings.Repeat("-", width))
}
