#!/bin/bash
set -e

REPO_DIR="/tmp/agents-repo"
GIT_REMOTE="git@github.com:dzianisv/agents.git"

echo "=== Agent Config Backup ==="

# Create repo dir
mkdir -p "$REPO_DIR"
cd "$REPO_DIR"

# Initialize git if needed
if [ ! -d .git ]; then
    git init
    git remote add origin "$GIT_REMOTE"
    git checkout -b main
fi

# Copy configs (excluding large/transient files)
echo "Copying configs..."
rsync -av --progress \
    --exclude 'node_modules' \
    --exclude '*.sqlite' \
    --exclude '*.sqlite3' \
    --exclude '.git' \
    --exclude '*.log' \
    --exclude '.venv' \
    --exclude '*.jsonl' \
    ~/.config/opencode/ "$REPO_DIR/opencode/"

rsync -av --progress \
    --exclude '*.sqlite' \
    --exclude '*.sqlite3' \
    --exclude '.git' \
    --exclude '*.log' \
    ~/.codex/ "$REPO_DIR/codex/"

echo "Copying OpenClaw config..."
rsync -av --progress \
    --exclude 'node_modules' \
    --exclude '*.sqlite' \
    --exclude '*.sqlite3' \
    --exclude '.git' \
    --exclude '*.log' \
    --exclude '*.jsonl' \
    --exclude 'media' \
    ~/.openclaw/ "$REPO_DIR/openclaw/"

# Create .gitignore if missing
if [ ! -f .gitignore ]; then
    cat > .gitignore << 'EOF'
*.log
*.sqlite
*.sqlite3
.DS_Store
node_modules
__pycache__
*.pyc
EOF
fi

# Commit and push
echo "Committing..."
git add -A
git commit -m "Backup $(date '+%Y-%m-%d %H:%M')" || echo "No changes to commit"

echo "Pushing..."
git push -u origin main

echo "Done! Backup at https://github.com/dzianisv/agents"
