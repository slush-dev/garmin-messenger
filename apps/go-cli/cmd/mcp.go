package cmd

import (
	"log/slog"
	"os"

	"github.com/slush-dev/garmin-messenger/apps/go-cli/internal/mcpserver"
	"github.com/spf13/cobra"
)

var mcpCmd = &cobra.Command{
	Use:   "mcp",
	Short: "Start an MCP (Model Context Protocol) server on stdio",
	Long: `Start an MCP server that exposes Garmin Messenger as tools and resources
for LLM integration (Claude Desktop, Claude Code, etc.).

The server communicates via JSON-RPC over stdin/stdout.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		level := slog.LevelInfo
		if verbose {
			level = slog.LevelDebug
		}
		logger := slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level}))

		s := mcpserver.New(sessionDir, rootCmd.Version, logger)
		return s.Run(cmd.Context())
	},
}

func init() {
	rootCmd.AddCommand(mcpCmd)
}
