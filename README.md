# VisaDesk - Visa Application Management Platform

A production-ready Flask web application for managing visa applications and performing QC checks. Built for Uniglobe BIT travel consulting firm.

## Features

- **Applicant Management**: Create, edit, and track visa applicants with comprehensive profiles
- **Document Management**: Upload and organize visa application documents and supporting files
- **QC Engine**: Automated quality checks on visa applications using PDF extraction and validation
- **Dashboard**: Real-time statistics and performance metrics for executives and admins
- **User Management**: Role-based access control (Admin and Executive roles)
- **QC Reports**: Detailed reports with check results, pass rates, and recommendations
- **Charts & Analytics**: Visual dashboards with Chart.js for data visualization

## Project Structure

```
visadesk/
├── app.py                      # Application factory
├── config.py                   # Configuration settings
├── models.py                   # SQLAlchemy models
├── extensions.py              # Flask extensions
├── seed.py                     # Database seeding script
├── requirements.txt            # Python dependencies
├── qc/                        # QC engine package
│   ├── extractor.py           # PDF field extraction
│   ├── qc_engine.py           # QC logic and rules
│   ├── gdrive_upload.py       # Google Drive integration
│   └── routes.py              # QC routes
├── auth/                      # Authentication module
│   └── routes.py              # Login/logout routes
├── applicants/                # Applicant management
│   └── routes.py              # Applicant CRUD routes
├── dashboard/                 # Dashboard module
│   └── routes.py              # Dashboard routes
├── admin/                     # Admin module
│   └── routes.py              # User management routes
├── static/                    # Static files
│   ├── css/style.css         # Custom styles
│   └── js/app.js             # Custom JavaScript
├── templates/                 # Jinja2 templates
│   ├── base.html             # Base template
│   ├── auth/                 # Auth templates
│   ├── applicants/           # Applicant templates
│   ├── qc/                   # QC templates
│   ├── dashboard/            # Dashboard templates
│   └── admin/                # Admin templates
├── uploads/                  # User uploaded files
└── visadesk.db              # SQLite database
```

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup Instructions

1. **Clone or navigate to the project directory**
   ```bash
   cd visadesk
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create default admin user**
   ```bash
   python seed.py
   ```
   This creates an admin user with:
   - Username: `admin`
   - Password: `admin123`
   - **Important**: Change this password after first login!

5. **Run the application**
   ```bash
   python app.py
   ```
   The app will start at `http://localhost:5000`

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Flask settings
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=sqlite:///visadesk.db

# Google Drive (optional)
GOOGLE_CREDENTIALS_FILE=path/to/credentials.json
```

### config.py

Main configuration file with settings for:
- Database URI
- Upload folder and file limits
- Session timeout
- CSRF protection

## Usage

### Admin Dashboard
- Navigate to `/dashboard` when logged in as admin
- Manage all users and applicants
- View team-wide statistics and performance metrics
- Create new executive users

### Executive Dashboard
- Personal applicant list and status tracking
- Upload documents for visa applications
- Run QC checks on applicants
- View QC reports and results

### Creating an Applicant

1. Click "New Applicant" in the navigation
2. Fill in applicant details (name, passport, visa type, etc.)
3. View applicant in the list
4. Upload visa application and supporting documents
5. Run QC check when documents are ready

### Running QC Checks

1. Go to applicant detail page
2. Switch to "Documents" tab
3. Upload all required documents (visa form, passport, bank statements, etc.)
4. Click "Run QC Check"
5. View results in the QC Report

## Database Models

### User
- Username, email, password (hashed)
- Full name and role (admin/executive)
- Account status and last login timestamp

### Applicant
- Full name, passport number, nationality
- Date of birth, visa type, destination
- Status tracking (draft, qc_passed, qc_failed, approved, rejected, etc.)
- Notes and timestamps

### Document
- Filename and file path
- Document type classification
- Uploader information
- Optional Google Drive link

### QCReport
- Applicant reference
- Check results and pass/fail counts
- Overall status (pass/fail/warning)
- Full report data as JSON

## Key Features Explained

### QC Engine
The QC engine uses the existing `extractor.py` and `qc_engine.py` modules to:
- Extract data from PDF visa applications (Schengen, UK)
- Cross-reference against supporting documents
- Validate required fields and document presence
- Generate detailed reports with pass/fail results

### File Uploads
- Files are stored in `uploads/{applicant_id}/` subdirectories
- Automatic document type detection for PDFs
- Secure filename handling
- 50MB file size limit

### Role-Based Access Control
- **Admin**: Full system access, user management, team statistics
- **Executive**: Manage own applicants, run QC checks, view personal dashboard

### Dashboard Charts
- Status distribution pie chart
- Weekly processing volume bar chart
- Executive performance metrics
- Real-time pass/fail rates

## API Endpoints

### Authentication
- `GET/POST /auth/login` - User login
- `GET /auth/logout` - Logout
- `GET/POST /auth/change-password` - Change password

### Applicants
- `GET /applicants` - List applicants (with search/filter)
- `GET/POST /applicants/new` - Create applicant
- `GET /applicants/<id>` - View applicant details
- `GET/POST /applicants/<id>/edit` - Edit applicant
- `POST /applicants/<id>/upload` - Upload document
- `GET /applicants/<id>/documents/<doc_id>/download` - Download file
- `POST /applicants/<id>/documents/<doc_id>/delete` - Delete document

### QC Checks
- `GET/POST /qc/run/<applicant_id>` - Run QC check
- `GET /qc/report/<report_id>` - View QC report
- `GET /qc/history/<applicant_id>` - Get QC history (JSON)

### Dashboard
- `GET /dashboard` - Main dashboard
- `GET /dashboard/executives` - Team performance (admin only)
- `GET /dashboard/data/status-distribution` - Chart data (JSON)
- `GET /dashboard/data/weekly-volume` - Chart data (JSON)

### Admin
- `GET /admin/users` - List users
- `GET/POST /admin/users/new` - Create user
- `GET/POST /admin/users/<id>/edit` - Edit user
- `POST /admin/users/<id>/deactivate` - Deactivate user
- `POST /admin/users/<id>/activate` - Activate user

## Security Features

- **Password Hashing**: Using werkzeug.security for password hashing
- **CSRF Protection**: Flask-WTF CSRF tokens on all forms
- **Authentication**: Flask-Login session management
- **Authorization**: Role-based access control on all routes
- **File Security**: Secure filename handling with werkzeug
- **Session Security**: HTTP-only, SameSite cookies

## Performance Considerations

- SQLAlchemy ORM with proper indexing
- Pagination on list views
- Lazy loading of relationships
- Chart data served as JSON (not rendering large tables in HTML)
- File storage with relative paths for portability

## Troubleshooting

### Database Issues
- Delete `visadesk.db` and re-run `seed.py` to reset database
- Check `SQLALCHEMY_DATABASE_URI` in config.py

### Upload Issues
- Ensure `uploads/` directory exists (created automatically)
- Check file permissions
- Verify MAX_CONTENT_LENGTH setting for large files

### QC Check Errors
- Verify PDF files are valid and readable
- Check that visa application document is marked as `visa_application` type
- Review console logs for extraction errors

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Database Migrations
To add new fields to models, update `models.py` and delete `visadesk.db`, then run `seed.py` again.

### Adding New Routes
1. Create new blueprint module in appropriate folder
2. Import and register in `app.py`
3. Create templates in `templates/` with matching structure

## Production Deployment

### Before Going Live
1. Change `SECRET_KEY` to a secure random value
2. Set `FLASK_ENV=production`
3. Set `SESSION_COOKIE_SECURE=True` (requires HTTPS)
4. Use a production database (PostgreSQL recommended)
5. Configure proper logging
6. Set up HTTPS with proper certificates
7. Use a production WSGI server (Gunicorn, uWSGI)

### Example Production Run
```bash
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

## Support and Maintenance

### Common Tasks
- **Reset admin password**: Delete user from database and run `seed.py` again
- **Backup database**: Use SQLite3 CLI or Python's sqlite3 module
- **Export data**: Use QCReport.query.all() to export results as JSON

## License

Internal use for Uniglobe BIT Travel Consulting

## Contact

For issues, questions, or feature requests, contact the development team.

---

**Last Updated**: April 2026
**Version**: 1.0.0
