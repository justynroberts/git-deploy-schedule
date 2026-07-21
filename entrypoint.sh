#!/bin/bash
set -e

# Configure git credentials if GITHUB_TOKEN is set
if [ -n "$GITHUB_TOKEN" ]; then
    echo "Configuring git credentials..."
    git config --global credential.helper store
    echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials
    # Write token file for git_operations.py token-in-URL auth
    mkdir -p /app/database
    echo "$GITHUB_TOKEN" > /app/database/.github_token
    chmod 600 /app/database/.github_token
fi

# Configure git user (required for commits)
git config --global user.email "scheduler@git-deploy.local"
git config --global user.name "Git Deploy Scheduler"

# Mark mounted repo as safe (fixes dubious ownership error)
git config --global --add safe.directory /repo

# Clone target repo if /repo is empty or not a git repo
if [ -n "$REPO_REMOTE_URL" ] && [ ! -d /repo/.git ]; then
    echo "Cloning $REPO_REMOTE_URL into /repo..."
    git clone "$REPO_REMOTE_URL" /tmp/repo-clone
    cp -a /tmp/repo-clone/. /repo/
    rm -rf /tmp/repo-clone
    echo "Clone complete"
elif [ -n "$REPO_REMOTE_URL" ] && [ -d /repo/.git ]; then
    git -C /repo remote set-url origin "$REPO_REMOTE_URL"
fi

exec "$@"
