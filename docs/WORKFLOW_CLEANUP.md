# Workflow Cleanup Guide

This guide explains how to clear all prior GitHub Actions workflow runs from your repository.

## Overview

The `clear-workflow-runs.sh` script helps you delete all workflow run history from your GitHub repository. This is useful for:

- Cleaning up a large number of old workflow runs
- Starting fresh after testing or debugging workflows
- Reducing clutter in the Actions tab
- Freeing up storage space (workflow artifacts count towards storage limits)

## Prerequisites

### GitHub CLI (gh)

The script requires the GitHub CLI (`gh`) to be installed and authenticated.

#### Installation

**macOS:**
```bash
brew install gh
```

**Linux (Debian/Ubuntu):**
```bash
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh
```

**Windows:**
```powershell
winget install --id GitHub.cli
```

For other installation methods, see: https://cli.github.com/

#### Authentication

After installation, authenticate with GitHub:

```bash
gh auth login
```

Follow the prompts to complete authentication.

## Usage

### Basic Usage

1. Navigate to your repository directory:
   ```bash
   cd /path/to/kahani
   ```

2. Run the cleanup script:
   ```bash
   ./clear-workflow-runs.sh
   ```

3. Confirm when prompted:
   ```
   WARNING: This will delete ALL workflow runs from this repository.
   This action cannot be undone!
   
   Are you sure you want to continue? (yes/no): yes
   ```

4. Wait for the script to complete:
   ```
   Found 150 workflow runs to delete.
   
   Deleting run 1/150 (ID: 1234567890)... ✓
   Deleting run 2/150 (ID: 1234567891)... ✓
   ...
   
   Successfully deleted all 150 workflow runs!
   ```

## What Gets Deleted

The script will delete:
- ✅ All workflow run records
- ✅ All workflow run logs
- ✅ All workflow run artifacts
- ✅ All workflow run annotations

The script will NOT delete:
- ❌ Workflow definition files (`.github/workflows/*.yml`)
- ❌ Any code or repository contents
- ❌ Git history

## Important Notes

1. **This action is irreversible**: Once workflow runs are deleted, they cannot be recovered.

2. **Rate Limiting**: The script includes a 0.3 second delay between deletions to avoid GitHub API rate limits. For repositories with many workflow runs, this may take some time. GitHub's rate limit typically allows 5000 API requests per hour for authenticated users.

3. **Pagination**: The script automatically handles pagination for repositories with large numbers of workflow runs (using GitHub CLI's `--paginate` flag), so all runs will be fetched regardless of quantity.

4. **Permissions**: You need appropriate permissions on the repository to delete workflow runs. Typically, this means you need to be:
   - A repository owner
   - A repository admin
   - A user with write access to the repository

5. **Future Runs**: This script only deletes past workflow runs. New workflows will continue to run normally according to your workflow configuration.

## Troubleshooting

### "gh: command not found"

**Problem**: GitHub CLI is not installed.

**Solution**: Install the GitHub CLI following the installation instructions above.

### "Not authenticated with GitHub CLI"

**Problem**: You haven't logged in to GitHub CLI.

**Solution**: Run `gh auth login` and follow the authentication prompts.

### "Could not determine repository name"

**Problem**: You're not in a git repository directory, or the repository doesn't have a GitHub remote.

**Solution**: Navigate to your repository directory and ensure it's a valid git repository with a GitHub remote:
```bash
cd /path/to/kahani
git remote -v
```

### "Failed to delete X workflow runs"

**Problem**: Some workflow runs couldn't be deleted, possibly due to:
- API rate limiting
- Permission issues
- Network problems

**Solution**: 
- Wait a few minutes and run the script again
- Check your GitHub permissions
- Verify your network connection

### "Failed to fetch workflow runs from GitHub API"

**Problem**: The script couldn't retrieve workflow runs from GitHub.

**Possible causes**:
- Network connectivity issues
- GitHub API is temporarily unavailable
- Rate limiting on API requests
- Insufficient repository permissions

**Solution**:
1. Check your internet connection
2. Verify you have appropriate permissions on the repository
3. Check GitHub's status page: https://www.githubstatus.com/
4. Wait a few minutes and try again
5. If the problem persists, try authenticating again: `gh auth login`

### Rate Limiting Issues

If you encounter rate limiting errors:

1. The script includes a 0.3 second delay between deletions, but for very large numbers of runs, you might still hit limits.

2. Wait 5-10 minutes and run the script again - it will continue with any remaining runs.

3. GitHub's rate limit typically allows 5000 API requests per hour for authenticated users.

## Alternative: Manual Deletion

If you prefer to delete workflow runs manually:

1. Go to your repository on GitHub
2. Click the "Actions" tab
3. Select a workflow from the sidebar
4. For each run:
   - Click the "..." menu
   - Select "Delete workflow run"

Note: This is tedious for large numbers of runs, which is why this script exists!

## Alternative: Delete Specific Workflows

If you want to delete runs for a specific workflow only (not implemented in this script), you can modify the script or use:

```bash
# List all workflows
gh api /repos/OWNER/REPO/actions/workflows --paginate -q '.workflows[] | .name, .id'

# Get runs for a specific workflow
gh api /repos/OWNER/REPO/actions/workflows/WORKFLOW_ID/runs --paginate -q '.workflow_runs[].id'

# Delete specific runs
gh api -X DELETE /repos/OWNER/REPO/actions/runs/RUN_ID
```

## See Also

- [GitHub CLI Documentation](https://cli.github.com/manual/)
- [GitHub Actions API Documentation](https://docs.github.com/en/rest/actions)
- [Managing Workflow Runs](https://docs.github.com/en/actions/managing-workflow-runs)
