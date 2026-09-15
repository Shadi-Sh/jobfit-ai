#!/usr/bin/env bash
# Creates a clean copy of the project for the Claude Code dev sandbox to
# bind-mount, deliberately SEPARATE from the live repository directory.
#
# Why a copy instead of bind-mounting the repo directly: the live repo
# directory also contains real local secrets/generated data that must never
# be visible inside the sandbox (.env, the SQLite database, .venv,
# node_modules, build output). This script copies exactly the set of files
# that are tracked by git OR untracked-but-not-gitignored (i.e. legitimate
# project source that just hasn't been committed yet) — the same file set
# `git add -A` would stage. Anything matched by .gitignore (.env, *.db,
# .venv/, node_modules, frontend/dist, evaluation/results/*.json, etc.) is
# excluded by construction, not by a manually maintained exclude list.
#
# This is a plain file copy, not a git clone — the destination does NOT
# contain .git history. Treat it as a working copy for the agent to edit;
# commit from the real repository on the host once you're happy with a
# change (e.g. copy the changed files back, or diff the two directories).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="${1:-$REPO_ROOT/../jobfit-ai-sandbox-workspace}"

if [ "$WORKSPACE_DIR" = "$REPO_ROOT" ]; then
  echo "Refusing to use the live repository directory as the sandbox workspace." >&2
  exit 1
fi

mkdir -p "$WORKSPACE_DIR"

cd "$REPO_ROOT"
{ git ls-files --cached; git ls-files --others --exclude-standard; } | sort -u > /tmp/jobfit_sandbox_filelist.$$

rsync -a --files-from=/tmp/jobfit_sandbox_filelist.$$ "$REPO_ROOT/" "$WORKSPACE_DIR/"
rm -f /tmp/jobfit_sandbox_filelist.$$

echo "Clean sandbox workspace created at: $WORKSPACE_DIR"
echo "File count: $(find "$WORKSPACE_DIR" -type f | wc -l)"
echo
echo "Verify no secrets made it in:"
echo "  find \"$WORKSPACE_DIR\" -name '.env' -o -name '*.db'"
