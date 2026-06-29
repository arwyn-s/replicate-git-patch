package main

import (
	"context"
	"os"

	"github.com/urfave/cli/v3"
)

/**
 * Three stages of workflows
 * 1. Checkout from develop branch, make changes, and commit and push
 * 2. Checkout from other release branch, and apply the same changes and push
 * 3. Create a pull request to merge all the changes into corresponding base branches
 */

func main() {
	app := &cli.Command{
		Name:  "newfix",
		Usage: "A tool to fix bugs across multiple release branches",
		Commands: []*cli.Command{
			{
				Name:  "show",
				Usage: "Show the current state of the bug fix",
				Action: func(ctx context.Context, cmd *cli.Command) error {
					state, err := LoadState(cmd.Args().First())
					if err != nil {
						return cli.Exit("Error loading state: "+err.Error(), 1)
					}
					state.Show()
					return nil
				},
			},
			{
				Name:   "newfix",
				Usage:  "Initialize a new bug fix",
				Action: Newfix,
			},
		},
	}

	if err := app.Run(context.Background(), os.Args); err != nil {
		panic(err)
	}
}
