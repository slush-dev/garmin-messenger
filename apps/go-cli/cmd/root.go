package cmd

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	gm "github.com/slush-dev/garmin-messenger"
	"github.com/spf13/cobra"
)

var (
	sessionDir string
	verbose    bool
	useYAML    bool
)

func defaultSessionDir() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".garmin-messenger")
}

var rootCmd = &cobra.Command{
	Use:   "garmin-messenger",
	Short: "Unofficial Garmin Messenger (Hermes) CLI client",
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		if verbose {
			slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelDebug})))
		}
	},
}

func init() {
	rootCmd.PersistentFlags().StringVar(&sessionDir, "session-dir", defaultSessionDir(), "Directory for saving/resuming session tokens")
	rootCmd.PersistentFlags().BoolVarP(&verbose, "verbose", "v", false, "Enable debug logging")
	rootCmd.PersistentFlags().BoolVar(&useYAML, "yaml", false, "Print output in YAML format instead of tables")

	// Allow env override
	if envDir := os.Getenv("GARMIN_SESSION_DIR"); envDir != "" {
		sessionDir = envDir
	}
}

// SetVersion sets the version string shown by --version.
func SetVersion(v string) {
	rootCmd.Version = v
}

// Execute runs the root command.
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

// getAuth resumes a saved session or exits with a helpful message.
func getAuth() *gm.HermesAuth {
	auth := gm.NewHermesAuth(
		gm.WithSessionDir(sessionDir),
	)
	if err := auth.Resume(rootCmd.Context()); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		fmt.Fprintln(os.Stderr, "Run 'garmin-messenger login' first to authenticate.")
		os.Exit(1)
	}
	return auth
}
