# VisaDesk - Quick Start Guide

Get VisaDesk up and running in 5 minutes!

## Step 1: Install Dependencies

```bash
cd visadesk
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Step 2: Create Database and Admin User

```bash
python seed.py
```

Output:
```
Admin user created successfully
Username: admin
Password: admin123
Please change the password after first login!
```

## Step 3: Run the Application

```bash
python app.py
```

Open your browser to: **http://localhost:5000**

## Step 4: Login

- **Username**: admin
- **Password**: admin123

## Next Steps

### As an Admin:
1. Go to Admin → Users to create more users (Executive role)
2. View Dashboard to see system-wide statistics
3. Create applicants manually or have executives create them

### As an Executive:
1. Click "New Applicant" to create a visa applicant
2. Fill in applicant details (name, passport, visa type, etc.)
3. Go to applicant detail → Documents tab
4. Upload visa application form and supporting docs
5. Click "Run QC Check" to validate documents
6. View detailed QC Report with results

## Directory Structure

```
visadesk/
├── app.py                 # Main application entry point
├── config.py              # Configuration (SECRET_KEY, DATABASE_URI)
├── models.py              # Database models
├── seed.py                # Create default admin user
├── auth/                  # Login/Logout routes
├── applicants/            # Applicant management
├── qc/                    # QC engine and routes
├── dashboard/             # Dashboard and analytics
├── admin/                 # User management
├── static/                # CSS, JavaScript
├── templates/             # HTML templates
├── uploads/               # Uploaded files
└── requirements.txt       # Python packages
```

## Default Routes

| Path | Purpose |
|------|---------|
| `/` | Home (redirects to dashboard or login) |
| `/auth/login` | Login page |
| `/dashboard` | Main dashboard |
| `/applicants` | List all applicants |
| `/applicants/new` | Create new applicant |
| `/applicants/<id>` | View applicant details |
| `/qc/run/<id>` | Run QC check |
| `/admin/users` | Manage users (admin only) |

## Passwords

**IMPORTANT**: Change the default admin password immediately after first login!

1. Login with admin/admin123
2. Click username → "Change Password"
3. Enter new secure password

## File Uploads

- Supported: PDF, JPG, PNG, DOC, DOCX, TXT
- Max size: 50MB per file
- Auto-saves to: `uploads/{applicant_id}/`

## Database

- Type: SQLite (visadesk.db)
- Created automatically on first run
- Reset with: `rm visadesk.db && python seed.py`

## Troubleshooting

**Port 5000 already in use?**
```bash
python app.py --port 5001
```

**Database locked error?**
```bash
rm visadesk.db
python seed.py
python app.py
```

**Missing dependencies?**
```bash
pip install -r requirements.txt --upgrade
```

## Development Mode

The app runs in development mode by default with:
- Auto-reload on code changes
- Debug toolbar enabled
- Detailed error messages

For production, set:
```bash
export FLASK_ENV=production
export SECRET_KEY="your-secure-key"
```

## Support

- Check README.md for detailed documentation
- Review models.py for database schema
- Inspect routes.py files for endpoint details

---

**Ready to go!** Start creating applicants and managing visa applications.
