#!/usr/bin/env bash
set -euo pipefail

./git-secrets --register-aws
./git-secrets --add-provider -- cat .gitdisallowed 2>/dev/null || true

scan_type=${1-_}
if { [ "${scan_type}" == "unstaged" ]; } ; then
  echo "Scanning staged and unstaged files for secrets"
  ./git-secrets --scan --recursive
  echo "Scanning untracked files for secrets"
  ./git-secrets --scan --untracked
else
  echo "Scanning for secrets"
  # if staged files exist, this will scan staged files only, otherwise normal scan
  ./git-secrets --pre_commit_hook
fi
