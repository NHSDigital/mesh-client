#!/usr/bin/env bash

PWD="$(pwd)"

message_file="${1}"

commit_message="$(tr '[:upper:]' '[:lower:]' < "${message_file}")"

if [[ "${commit_message}" =~ ^(((mesh|spinecore)?\-[0-9]+\:?\ )|(merge\ branch)).* ]]; then
  exit 0
else
  echo ""
  echo "commit message should start with <jira-ref>:"
  echo "e.g.  git commit -m \"mesh-123: fix some problem with an issue\""
  echo ""
  exit 1
fi
