#!/bin/bash

# Script to delete all GitHub Actions workflow runs
# This helps clean up workflow run history from the repository

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "  GitHub Actions Workflow Run Cleanup Script"
echo "=================================================="
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: GitHub CLI (gh) is not installed.${NC}"
    echo "Please install it from: https://cli.github.com/"
    echo ""
    echo "Installation instructions:"
    echo "  - macOS: brew install gh"
    echo "  - Linux: See https://github.com/cli/cli/blob/trunk/docs/install_linux.md"
    echo "  - Windows: See https://github.com/cli/cli#installation"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: Not authenticated with GitHub CLI.${NC}"
    echo "Please run: gh auth login"
    exit 1
fi

# Get the repository name
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
if [ -z "$REPO" ]; then
    echo -e "${RED}Error: Could not determine repository name.${NC}"
    echo "Make sure you're in a git repository directory."
    exit 1
fi

echo -e "${GREEN}Repository: $REPO${NC}"
echo ""

# Confirm with user
echo -e "${YELLOW}WARNING: This will delete ALL workflow runs from this repository.${NC}"
echo "This action cannot be undone!"
echo ""
read -rp "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Operation cancelled."
    exit 0
fi

echo ""
echo "Fetching workflow runs..."

# Get all workflow runs
RUNS=$(gh api "/repos/$REPO/actions/runs" --paginate -q '.workflow_runs[].id' 2>/dev/null)

if [ -z "$RUNS" ]; then
    echo -e "${GREEN}No workflow runs found. Nothing to delete.${NC}"
    exit 0
fi

# Count total runs
TOTAL=$(echo "$RUNS" | wc -l)
echo "Found $TOTAL workflow runs to delete."
echo ""

# Delete each run
COUNTER=0
FAILED=0

# Save IFS and use while read with process substitution to avoid subshell
while IFS= read -r RUN_ID; do
    COUNTER=$((COUNTER + 1))
    echo -ne "Deleting run $COUNTER/$TOTAL (ID: $RUN_ID)..."
    
    if gh api -X DELETE "/repos/$REPO/actions/runs/$RUN_ID" &> /dev/null; then
        echo -e " ${GREEN}✓${NC}"
    else
        echo -e " ${RED}✗${NC}"
        FAILED=$((FAILED + 1))
    fi
    
    # Add a delay to avoid rate limiting (increased for better rate limit handling)
    sleep 0.3
done < <(echo "$RUNS")

echo ""
echo "=================================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}Successfully deleted all $TOTAL workflow runs!${NC}"
else
    echo -e "${YELLOW}Deleted $((TOTAL - FAILED)) out of $TOTAL workflow runs.${NC}"
    echo -e "${RED}Failed to delete $FAILED workflow runs.${NC}"
fi
echo "=================================================="
