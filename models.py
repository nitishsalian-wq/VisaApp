"""
SQLAlchemy models for VisaDesk
"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager


class User(UserMixin, db.Model):
    """User model"""
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(200))
    role = db.Column(db.String(20), default='executive', nullable=False)  # 'admin' or 'executive'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)

    # Relationships
    applicants = db.relationship('Applicant', backref='creator', lazy=True, foreign_keys='Applicant.created_by_id')
    documents = db.relationship('Document', backref='uploader', lazy=True, foreign_keys='Document.uploaded_by_id')
    qc_reports = db.relationship('QCReport', backref='run_by', lazy=True, foreign_keys='QCReport.run_by_id')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user is admin"""
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.username}>'


class Applicant(db.Model):
    """Applicant model"""
    __tablename__ = 'applicant'

    id = db.Column(db.Integer, primary_key=True)

    # Client type: corporate or retail
    client_type = db.Column(db.String(20), nullable=False, default='retail')  # 'corporate' or 'retail'
    corporate_name = db.Column(db.String(200))  # Company name if corporate
    crm_id = db.Column(db.String(50), index=True)  # CRM ID if retail client

    # Passport-format name fields
    surname = db.Column(db.String(100), nullable=False, index=True)
    given_names = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(300), nullable=False, index=True)  # Auto: SURNAME, Given Names

    passport_number = db.Column(db.String(50), index=True)
    nationality = db.Column(db.String(100))
    date_of_birth = db.Column(db.Date)
    visa_type = db.Column(db.String(50))  # 'schengen', 'uk', etc.
    destination_country = db.Column(db.String(100))
    visa_purpose = db.Column(db.String(100))  # 'tourist', 'business'
    status = db.Column(db.String(50), default='draft', nullable=False)
    # draft, documents_uploaded, qc_passed, qc_failed, submitted, approved, rejected
    notes = db.Column(db.Text)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    documents = db.relationship('Document', backref='applicant', lazy=True, cascade='all, delete-orphan')
    qc_reports = db.relationship('QCReport', backref='applicant', lazy=True, cascade='all, delete-orphan')

    def get_display_name(self):
        """Return name in passport format: SURNAME, Given Names"""
        return f"{self.surname.upper()}, {self.given_names}"

    def get_client_display(self):
        """Return client info string"""
        if self.client_type == 'corporate':
            return f"Corporate — {self.corporate_name or 'N/A'}"
        return f"Retail — CRM: {self.crm_id or 'N/A'}"

    def __repr__(self):
        return f'<Applicant {self.full_name}>'

    def get_status_badge_class(self):
        """Return Bootstrap class for status badge"""
        status_map = {
            'draft': 'secondary',
            'documents_uploaded': 'info',
            'qc_passed': 'success',
            'qc_failed': 'danger',
            'submitted': 'primary',
            'approved': 'success',
            'rejected': 'danger',
        }
        return status_map.get(self.status, 'secondary')

    def get_status_display(self):
        """Return human-readable status"""
        status_map = {
            'draft': 'Draft',
            'documents_uploaded': 'Documents Uploaded',
            'qc_passed': 'QC Passed',
            'qc_failed': 'QC Failed',
            'submitted': 'Submitted',
            'approved': 'Approved',
            'rejected': 'Rejected',
        }
        return status_map.get(self.status, self.status)


class Document(db.Model):
    """Document model"""
    __tablename__ = 'document'

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    doc_type = db.Column(db.String(50))
    # visa_application, passport_copy, bank_statement, flight_ticket, hotel_booking,
    # invitation_letter, cover_letter, photo, other
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    gdrive_link = db.Column(db.String(500))

    def __repr__(self):
        return f'<Document {self.original_filename}>'

    def get_doc_type_display(self):
        """Return human-readable doc type"""
        type_map = {
            'visa_application': 'Visa Application',
            'passport_copy': 'Passport Copy',
            'bank_statement': 'Bank Statement',
            'flight_ticket': 'Flight Ticket',
            'hotel_booking': 'Hotel Booking',
            'invitation_letter': 'Invitation Letter',
            'cover_letter': 'Cover Letter',
            'photo': 'Photograph',
            'other': 'Other',
        }
        return type_map.get(self.doc_type, self.doc_type or 'Unknown')


class QCReport(db.Model):
    """QC Report model"""
    __tablename__ = 'qc_report'

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey('applicant.id'), nullable=False, index=True)
    run_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    run_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    visa_purpose = db.Column(db.String(100))
    check_type = db.Column(db.String(100))
    overall_status = db.Column(db.String(20))  # 'pass', 'fail', 'warning'
    total_checks = db.Column(db.Integer, default=0)
    passed_checks = db.Column(db.Integer, default=0)
    failed_checks = db.Column(db.Integer, default=0)
    warning_checks = db.Column(db.Integer, default=0)
    report_data = db.Column(db.JSON)  # Store full QC report JSON

    def __repr__(self):
        return f'<QCReport {self.id} for Applicant {self.applicant_id}>'

    def get_status_badge_class(self):
        """Return Bootstrap class for status badge"""
        status_map = {
            'pass': 'success',
            'fail': 'danger',
            'warning': 'warning',
        }
        return status_map.get(self.overall_status, 'secondary')

    def get_pass_rate(self):
        """Calculate pass rate percentage"""
        if self.total_checks == 0:
            return 0
        return round((self.passed_checks / self.total_checks) * 100, 1)


@login_manager.user_loader
def load_user(user_id):
    """Load user from ID"""
    return User.query.get(int(user_id))
