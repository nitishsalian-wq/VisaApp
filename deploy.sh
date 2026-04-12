#!/bin/bash
# VisaDesk Quick Deploy Script
# Run from ~/Desktop/visadesk on your Mac

set -e
echo "🚀 VisaDesk Deploy"

# Step 1: Remove stale lock if it exists
rm -f .git/index.lock 2>/dev/null || true

# Step 2: Commit and push
echo "📦 Committing and pushing..."
git add -A
git commit -m "Fix extraction: validate pdfplumber results, merge OCR+pdfplumber, clean field noise" || echo "Nothing to commit"
git push origin main

# Step 3: Deploy to Droplet
echo "🌐 Deploying to Droplet..."
ssh root@168.144.76.150 << 'REMOTE'
cd /home/visadesk/app
git config --global --add safe.directory /home/visadesk/app
git stash 2>/dev/null || true
git pull origin main

# Restart the app
supervisorctl restart visadesk
sleep 2

# Recreate user if DB was reset
source venv/bin/activate
python3 -c "
from app import create_app
from extensions import db
from models import User
app = create_app()
with app.app_context():
    if not User.query.filter_by(username='nitish').first():
        u = User(username='nitish', email='nitish@uniglobebit.com', full_name='Nitish Salian', role='admin')
        u.set_password('visa2024')
        db.session.add(u)
        db.session.commit()
        print('✅ User nitish created')
    else:
        print('✅ User nitish exists')

    if not User.query.filter_by(username='exec1').first():
        u = User(username='exec1', email='exec1@uniglobebit.com', full_name='Visa Executive 1', role='executive')
        u.set_password('exec2024')
        db.session.add(u)
        db.session.commit()
        print('✅ User exec1 created')
    else:
        print('✅ User exec1 exists')
"

echo "🎉 Deployment complete!"
supervisorctl status visadesk
REMOTE

echo "✅ Done! Visit http://168.144.76.150"
