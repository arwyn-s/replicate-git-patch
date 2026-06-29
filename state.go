package main

import (
	"encoding/gob"
	"fmt"
	"os"
)

type State struct {
	Name           string
	Main           string
	Branches       []string
	LastCommits    map[string]string // map of branch name to last commit hash
	ActualChanges  []string
	AppliedChanges map[string][]string // map of branch name to applied changes
	RemotesInSync  map[string]bool     // map of branch name to whether remote is in sync
	PRCreated      []string
}

func (s *State) Save() error {
	file, err := os.Create(".git/fix_wf/" + s.Name + ".state")
	if err != nil {
		return err
	}
	defer file.Close()
	encoder := gob.NewEncoder(file)
	err = encoder.Encode(s)
	if err != nil {
		return err
	}
	return nil
}

func LoadState(name string) (*State, error) {
	file, err := os.Open(".git/fix_wf/" + name + ".state")
	if err != nil {
		return nil, err
	}
	defer file.Close()
	decoder := gob.NewDecoder(file)
	var state State
	err = decoder.Decode(&state)
	if err != nil {
		return nil, err
	}
	return &state, nil
}

func (s *State) Show() {
	for _, branch := range s.Branches {
		lastCommit, exists := s.LastCommits[branch]
		if !exists {
			lastCommit = "No commits yet"
		}
		fmt.Println("Branch:", branch, "Last Commit:", lastCommit)
	}

	fmt.Println("Actual Changes:")
	for _, change := range s.ActualChanges {
		fmt.Println("-", change)
	}

	fmt.Println("Applied Changes:")
	for branch, change := range s.AppliedChanges {
		fmt.Println("Branch:", branch, "Change:", change)
	}

	fmt.Println("Remotes In Sync:")
	for branch, inSync := range s.RemotesInSync {
		status := "In Sync"
		if !inSync {
			status = "Not In Sync"
		}
		fmt.Println("Branch:", branch, status)
	}
}

func NewState(name string, branches []string) *State {
	err := os.Mkdir(".git/fix_wf", 0755)
	if err != nil && !os.IsExist(err) {
		fmt.Println("[ERROR] Failed to create directory .git/fix_wf:", err)
		return nil
	}
	AppliedChanges := make(map[string][]string)
	for _, branch := range branches {
		AppliedChanges[branch] = []string{}
	}
	state := &State{
		Name:           name,
		Main:           "develop",
		Branches:       branches,
		LastCommits:    make(map[string]string),
		ActualChanges:  []string{},
		AppliedChanges: AppliedChanges,
		RemotesInSync:  make(map[string]bool),
	}
	return state
}
