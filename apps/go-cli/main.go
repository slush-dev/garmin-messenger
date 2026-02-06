package main

import "github.com/slush-dev/garmin-messenger/apps/go-cli/cmd"

// version is set at build time via -ldflags "-X main.version=..."
var version = "dev"

func main() {
	cmd.SetVersion(version)
	cmd.Execute()
}
