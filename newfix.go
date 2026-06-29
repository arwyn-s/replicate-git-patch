package main

import (
	"context"
	"fmt"

	"github.com/urfave/cli/v3"
)

func Newfix(ctx context.Context, cmd *cli.Command) error {
	// Initialize a new bug fix
	// This function will set up the necessary state for a new bug fix
	// For example, it might create a new branch, initialize state, etc.
	if cmd.Args().Len() < 1 {
		return cli.Exit("Usage: newfix new <name> [branches...]", 1)
	}

	name := cmd.Args().Get(0)
	if name == "" {
		return cli.Exit("Please provide a name for the new bug fix", 1)
	}

	state, err := LoadState(name)
	if err == nil {
		fmt.Println("[WARN] State already exists, loading existing state.")
		state.Show()
		return nil
	}

	var branches []string
	for i := 1; i < cmd.Args().Len(); i++ {
		branches = append(branches, cmd.Args().Get(i))
	}
	if len(branches) == 0 {
		fmt.Println("[WARN] Patch will be applied to base branch only.")
	}
	state = NewState(name, branches)
	err = state.Save()
	return err
	// Return nil to indicate success
}
