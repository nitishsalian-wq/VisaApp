# VisaDesk Architecture & Implementation Guide

## Overview

VisaDesk is a production-ready Flask web application for managing visa applications with integrated QC (Quality Check) capabilities. It's built for Uniglobe BIT travel consulting firm to streamline visa application management and ensure document quality.

## Technology Stack

- **Framework**: Flask 3.0+
- **Database**: SQLAlchemy ORM with SQLite (can be changed to PostgreSQL)
- **Authentication**: Flask-Login with password hashing
- **Frontend**: Bootstrap 5, Chart.js, Vanilla JavaScript
- **PDF Processing**: pdfplumber, PyPDF
- **File Handling**: werkzeug for secure uploads
- **Cloud Integration**: Google Drive API support

## Core Architecture

### 1. Application Factory Pattern (app.py)

```python
def create_app(config_name=None):
    app = Flask(__name__)
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    # Register blueprints
    # Create database tables
    return app
```

**Benefits**:
- Multiple app instances for testing
- Configuration flexibility
- Clean separation of concerns

### 2. Database Layer (models.py)

Four main models implement the core business logic:

#### User Model
- Stores user credentials with bcrypt hashing
- Role-based access control (admin/executive)
- Tracks authentication history
- One-to-many relationships with Applicant and QCReport

#### Applicant Model
- Core entity for visa applicants
- Tracks application lifecycle (draft → approved/rejected)
- Links to uploaded documents and QC reports
- Full audit trail with created_at/updated_at timestamps

#### Document Model
- Stores uploaded file metadata
- Automatic document type detection (visa form, passport, etc.)
- File path management for secure storage
- Optional Google Drive integration

#### QCReport Model
- Records QC check results
- Stores check-by-check results as JSON
- Tracks which user ran the check and when
- Links to overall applicant status

### 3. Blueprint-Based Routing

Five separate blueprints handle different domains:

#### auth/ - Authentication
- Login page with remember-me functionality
- Password change capability
- Session management

#### applicants/ - Document Management
- Full CRUD operations for applicants
- File upload with drag-and-drop
- Document download and deletion
- Automatic status updates

#### qc/ - Quality Checks
- Integration with legacy extractor.py and qc_engine.py
- Runs checks on applicant documents
- Generates detailed reports
- Updates applicant status based on results

#### dashboard/ - Analytics
- Executive personal dashboard (own applicants only)
- Admin team-wide dashboard
- Real-time statistics and charts
- JSON API endpoints for dynamic charts

#### admin/ - User Management
- Create/edit/deactivate users
- Role assignment
- Only accessible by admins

## Data Flow

### Creating and Checking an Applicant

```
User Login
    ↓
Create Applicant (applicants/routes.py)
    ↓ Save to Database (models.Applicant)
    ↓
Upload Documents (applicants/routes.py)
    ↓ Detect type (qc/extractor.py) + Save (models.Document)
    ↓
Run QC Check (qc/routes.py)
    ↓ Extract PDF fields (qc/extractor.py)
    ↓ Run validation rules (qc/qc_engine.py)
    ↓ Generate report (models.QCReport)
    ↓ Update status (models.Applicant)
    ↓
View QC Report (qc/routes.py)
    ↓ Display results in template (templates/qc/report.html)
```

## Key Design Patterns

### 1. Model-View-Controller (MVC)

**Models** (models.py)
- Define database schema
- Implement business logic methods
- Handle relationships

**Views** (templates/)
- Render HTML using Jinja2
- Receive data from routes
- Submit forms back to routes

**Controllers** (*/routes.py)
- Handle HTTP requests/responses
- Call model methods
- Pass data to templates

### 2. Separation of Concerns

Each blueprint handles a specific domain:
- auth: Only authentication
- applicants: Only document/applicant management
- qc: Only QC checking
- dashboard: Only reporting/analytics
- admin: Only user administration

This makes code:
- Easy to test
- Simple to maintain
- Clear where to add features

### 3. Role-Based Access Control

```python
@admin_required  # Decorator
def list_users():
    # Only admin can access
```

Applied to sensitive operations:
- User management (admin only)
- QC checks (staff only)
- Dashboard (authenticated users)

### 4. DRY (Don't Repeat Yourself)

- Base template for consistent UI
- CSS for reusable styles
- Helper functions for common operations
- Database models for single source of truth

## File Upload Architecture

### Security Strategy

```
/uploads/
└── {applicant_id}/
    ├── 20240401_153000_visa_application.pdf
    ├── 20240401_153045_passport_copy.jpg
    └── 20240401_153120_bank_statement.pdf
```

**Security Measures**:
- Subdirectories by applicant (isolation)
- Timestamp prefix (unique naming)
- Secure filename sanitization
- File type validation
- Size limit enforcement
- Path traversal protection

## QC Engine Integration

The QC engine consists of three legacy modules:

### extractor.py (1,054 lines)
- Extracts structured data from PDFs
- Detects document type (Schengen, UK, passport, etc.)
- Parses personal data, dates, passport info
- Returns clean field dictionary

### qc_engine.py (1,244 lines)
- Implements QC business rules
- Cross-references documents
- Validates required fields
- Generates detailed check results
- Returns JSON report with pass/fail/warning status

### gdrive_upload.py (248 lines)
- Google Drive API integration
- Uploads documents to Google Drive
- Returns shareable links
- Optional feature for backup

### Integration in routes.py
```python
# Extract fields from visa application
visa_fields = extract_schengen_fields(pages)

# Run QC rules
qc_result = run_qc(
    visa_fields=visa_fields,
    supporting_docs=doc_paths,
    visa_purpose=applicant.visa_purpose,
    visa_type=applicant.visa_type
)

# Save report
report = QCReport(
    applicant_id=applicant_id,
    report_data=qc_result,
    overall_status=qc_result['overall_status']
)
```

## Authentication Flow

### Login Process

```
1. User submits credentials (templates/auth/login.html)
2. Route receives POST request (auth/routes.py)
3. Look up user by username (models.User.query)
4. Check password hash (user.check_password)
5. Update last_login timestamp
6. Create session (flask_login.login_user)
7. Redirect to dashboard or next page
```

### Protected Routes

```python
@login_required  # Flask-Login decorator
def view_applicant(applicant_id):
    # Accessible only to logged-in users

    # Additional check for applicant ownership
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('Access denied', 'danger')
        return redirect(...)
```

## Dashboard Architecture

### Executive Dashboard
- Personal statistics (own applicants only)
- Charts: Status distribution, weekly volume
- Recent QC results
- Data filtered by `created_by_id`

### Admin Dashboard
- System-wide statistics
- Team performance metrics per executive
- Detailed break down by status
- Unfiltered data access

### Dynamic Charts

```javascript
// Backend provides JSON data
fetch('/dashboard/data/status-distribution')
  .then(r => r.json())
  .then(data => {
    // Frontend renders with Chart.js
    new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [...]
      }
    })
  })
```

## Error Handling

### Validation Errors
- Form field validation on server
- Flash messages to user
- Re-render form with entered data

### Database Errors
- Try-catch blocks on database operations
- Flash error message
- Redirect to safe page

### File Errors
- Check file exists before operations
- Handle missing/corrupted PDFs
- Graceful fallback for detection failures

### Access Control Errors
- Check user permissions before operations
- Return 404 for unauthorized access (not 403)
- Log unauthorized access attempts

## Performance Optimizations

### Database
- Relationships use `lazy=True` for on-demand loading
- Indexes on frequently queried fields
- Pagination on list views (20 items per page)
- Avoid N+1 queries with eager loading when needed

### Frontend
- Bootstrap CDN (cached across sites)
- Minimized static CSS/JS
- Chart data as JSON (not rendering huge tables)
- Lazy loading of relationships

### File Handling
- Validate before processing
- Early return on errors
- Limit concurrent uploads

## Testing Strategy

### Unit Tests
- Test individual functions
- Mock database
- Mock external APIs

### Integration Tests
- Test routes with database
- Verify data persistence
- Test full workflows

### Example
```python
def test_create_applicant(client):
    response = client.post('/applicants/new', data={
        'full_name': 'John Doe',
        'visa_type': 'schengen'
    })
    assert response.status_code == 302  # Redirect
    assert Applicant.query.filter_by(
        full_name='John Doe'
    ).first() is not None
```

## Deployment Guide

### Development (Current)
```bash
python app.py  # Debug mode enabled
```

### Production
```bash
# Set environment
export FLASK_ENV=production
export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')

# Use production server
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"

# Or with uWSGI
uwsgi --http :8000 --wsgi-file app.py --callable create_app --processes 4
```

### Database Migration
```python
# Change SQLALCHEMY_DATABASE_URI in config.py
# PostgreSQL example:
# 'postgresql://user:password@localhost/visadesk'

# SQLite → PostgreSQL
# 1. Export data from SQLite
# 2. Create new PostgreSQL database
# 3. Update URI in config
# 4. Run python seed.py (creates tables)
# 5. Import data
```

## Monitoring and Logging

### Application Logs
```python
import logging
logging.basicConfig(
    filename='visadesk.log',
    level=logging.INFO
)
```

### Database Monitoring
```python
# In production, monitor:
# - Query count
# - Slow queries
# - Connection pool usage
```

### User Activity
```python
# QCReport records who ran checks and when
# User.last_login tracks access
# Document.uploaded_by tracks uploads
```

## Security Checklist

- [x] Password hashing (werkzeug.security)
- [x] CSRF protection (Flask-WTF)
- [x] SQL injection prevention (SQLAlchemy ORM)
- [x] XSS prevention (Jinja2 auto-escaping)
- [x] File upload validation
- [x] Path traversal protection
- [x] Session security (HTTP-only, SameSite)
- [x] Role-based access control
- [x] Input validation
- [x] Rate limiting (recommend adding in production)
- [ ] HTTPS (set SESSION_COOKIE_SECURE=True)
- [ ] Two-factor authentication (optional)
- [ ] API rate limiting (optional)

## Future Enhancements

1. **Batch Processing**: Upload multiple applicants at once
2. **Email Notifications**: Notify on QC completion
3. **API Authentication**: OAuth2 for external integrations
4. **Advanced Analytics**: Trend analysis, forecasting
5. **Mobile App**: React Native frontend
6. **Document Validation**: Additional OCR validation
7. **Workflow Automation**: Auto-trigger actions on conditions
8. **Multi-language Support**: i18n for international use
9. **Audit Trail**: Detailed tracking of all changes
10. **Export Reports**: PDF/Excel report generation

## Summary

VisaDesk is built on solid Flask fundamentals with:
- **Modular architecture** (blueprints by domain)
- **Proper separation of concerns** (models/views/controllers)
- **Security-first design** (authentication, authorization, validation)
- **Scalable database** (SQLAlchemy ORM, indexed queries)
- **Professional frontend** (Bootstrap 5, responsive design)
- **Integrated QC engine** (legacy modules preserved and utilized)

The application is production-ready and can be deployed immediately with proper environment configuration and HTTPS setup.
