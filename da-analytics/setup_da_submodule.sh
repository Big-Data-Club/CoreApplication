#!/bin/bash
# setup_da_submodule.sh
# ---------------------
# Converts the da-analytics/ folder (currently tracked by CoreApplication)
# into a proper Git submodule pointing to its own GitHub repository.
#
# Prerequisites:
#   1. Create a new GitHub repo: https://github.com/Big-Data-Club/DA-Analytics
#      (initialize it as empty, do NOT add README or .gitignore from GitHub UI)
#   2. Run this script from the CoreApplication root directory.
#
# Usage:
#   bash da-analytics/setup_da_submodule.sh

set -euo pipefail

SUBMODULE_REPO_URL="${1:-git@github.com:Big-Data-Club/DA-Analytics.git}"
PARENT_DIR="$(git rev-parse --show-toplevel)"
SUBMODULE_DIR="$PARENT_DIR/da-analytics"
TEMP_DIR="$(mktemp -d)"

echo "==> CoreApplication root: $PARENT_DIR"
echo "==> Target submodule repo: $SUBMODULE_REPO_URL"
echo ""

# Step 1: Copy da-analytics content to a temp directory
echo "[1/6] Copying da-analytics content to temp location..."
cp -r "$SUBMODULE_DIR/." "$TEMP_DIR/"

# Step 2: Remove da-analytics from parent git tracking
echo "[2/6] Removing da-analytics from parent repo tracking..."
cd "$PARENT_DIR"
git rm -r --cached da-analytics/
git rm -r da-analytics/ 2>/dev/null || rm -rf da-analytics/
git commit -m "refactor: remove da-analytics from parent repo (converting to submodule)"

# Step 3: Initialize da-analytics as standalone git repo from temp copy
echo "[3/6] Initializing standalone git repo from temp copy..."
mkdir -p "$SUBMODULE_DIR"
cp -r "$TEMP_DIR/." "$SUBMODULE_DIR/"
cd "$SUBMODULE_DIR"
git init
git config user.email "phucnhan289@gmail.com"
git config user.name "nhan2892005"
git add .
git commit -m "feat: initial commit - BDC DA Analytics workspace"

# Step 4: Add remote and push
echo "[4/6] Adding remote and pushing to $SUBMODULE_REPO_URL..."
git remote add origin "$SUBMODULE_REPO_URL"
git branch -M main
git push -u origin main

# Step 5: Add as submodule in parent repo
echo "[5/6] Adding da-analytics as a git submodule to CoreApplication..."
cd "$PARENT_DIR"
git submodule add "$SUBMODULE_REPO_URL" da-analytics
git submodule update --init --recursive

# Step 6: Commit submodule reference
echo "[6/6] Committing submodule reference to CoreApplication..."
git add .gitmodules da-analytics
git commit -m "feat(da): add DA-Analytics as a git submodule"

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "==> Done! da-analytics is now a git submodule."
echo "==> Submodule URL: $SUBMODULE_REPO_URL"
echo ""
echo "Next steps:"
echo "  1. Push the CoreApplication parent changes:  git push origin main"
echo "  2. Team members clone with:  git clone --recurse-submodules <repo>"
echo "  3. Or initialize after clone: git submodule update --init --recursive"
