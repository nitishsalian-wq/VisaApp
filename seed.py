"""
Seed script to create default admin user
"""
import os
import sys
from app import create_app
from extensions import db
from models import User

app = create_app()

with app.app_context():
    # Check if admin already exists
    admin = User.query.filter_by(username='admin').first()
    if admin:
        print("Admin user already exists")
        sys.exit(0)

    # Create admin user
    admin = User(
        username='admin',
        email='admin@visadesk.local',
        full_name='Administrator',
        role='admin',
        is_active=True
    )
    admin.set_password('admin123')

    db.session.add(admin)
    db.session.commit()

    print("Admin user created successfully")
    print("Username: admin")
    print("Password: admin123")
    print("Please change the password after first login!")
