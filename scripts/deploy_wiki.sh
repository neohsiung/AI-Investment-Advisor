#!/bin/bash
set -e

REPO_URL="https://github.com/neohsiung/AI-Investment-Advisor.wiki.git"
TEMP_DIR="wiki_temp_deploy"

echo "🚀 Deploying Wiki to $REPO_URL..."

# 1. Clean up previous valid run if exists
rm -rf $TEMP_DIR

# 2. Clone the wiki repo
git clone $REPO_URL $TEMP_DIR

# 3. Copy files (Home.md and others)
echo "📂 Copying files..."
cp wiki/*.md $TEMP_DIR/

# 4. Commit and Push
cd $TEMP_DIR
git config user.email "deploy@bot"
git config user.name "Wiki Deploy Bot"
git add .
git commit -m "docs: Update Wiki content from main repo" || echo "No changes to commit"
git push

# 5. Cleanup
cd ..
rm -rf $TEMP_DIR

echo "✅ Wiki Deployed Successfully!"
