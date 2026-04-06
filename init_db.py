#!/usr/bin/env python3
"""
Initialize database and create admin user for VisaDesk
Run this during deployment on DigitalOcean
"""
import os
from app import create_app
from extensions import db
from models import User

app = create_app(os.environ.get('FLASK_ENV', 'production'))

with app.app_context():
    db.create_all()

    # Create admin if doesn't exist
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@visadesk.local',
            full_name='Administrator',
            role='admin',
            is_active=True
        )
        admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully")
    else:
        print("Admin user already exists")

    print("Database initialized successfully!")
