"""
Applicant management routes for VisaDesk
"""
import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from sqlalchemy import desc
from extensions import db
from models import Applicant, Document, QCReport
from qc.extractor import detect_document_type, extract_text_from_pdf

applicants_bp = Blueprint('applicants', __name__, url_prefix='/applicants')


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def get_applicant_directory(applicant_id):
    """Get the upload directory for an applicant"""
    return os.path.join(current_app.config['UPLOAD_FOLDER'], str(applicant_id))


@applicants_bp.route('/', methods=['GET'])
@login_required
def list_applicants():
    """List all applicants"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = Applicant.query

    # Filter by owner or show all for admin
    if not current_user.is_admin():
        query = query.filter_by(created_by_id=current_user.id)

    # Search by name or passport
    if search:
        query = query.filter(
            db.or_(
                Applicant.full_name.ilike(f'%{search}%'),
                Applicant.passport_number.ilike(f'%{search}%')
            )
        )

    # Filter by status
    if status_filter:
        query = query.filter_by(status=status_filter)

    # Sort by updated_at descending
    query = query.order_by(desc(Applicant.updated_at))

    pagination = query.paginate(page=page, per_page=20)
    applicants = pagination.items

    return render_template(
        'applicants/list.html',
        applicants=applicants,
        pagination=pagination,
        search=search,
        status_filter=status_filter
    )


@applicants_bp.route('/new', methods=['GET', 'POST'])
@login_required
def add_applicant():
    """Add new applicant"""
    if request.method == 'POST':
        # Client type fields
        client_type = request.form.get('client_type', 'retail').strip()
        corporate_name = request.form.get('corporate_name', '').strip()
        crm_id = request.form.get('crm_id', '').strip()

        # Passport-format name
        surname = request.form.get('surname', '').strip()
        given_names = request.form.get('given_names', '').strip()

        passport_number = request.form.get('passport_number', '').strip()
        nationality = request.form.get('nationality', '').strip()
        date_of_birth = request.form.get('date_of_birth', '').strip()
        visa_type = request.form.get('visa_type', '').strip()
        destination_country = request.form.get('destination_country', '').strip()
        visa_purpose = request.form.get('visa_purpose', '').strip()
        notes = request.form.get('notes', '').strip()

        if not surname or not given_names:
            flash('Surname and Given Names are required.', 'danger')
            return render_template('applicants/form.html', applicant=None)

        if not visa_type:
            flash('Visa type is required.', 'danger')
            return render_template('applicants/form.html', applicant=None)

        if client_type == 'corporate' and not corporate_name:
            flash('Corporate name is required for corporate clients.', 'danger')
            return render_template('applicants/form.html', applicant=None)

        # Build full_name in passport format: SURNAME, Given Names
        full_name = f"{surname.upper()}, {given_names}"

        applicant = Applicant(
            client_type=client_type,
            corporate_name=corporate_name or None,
            crm_id=crm_id or None,
            surname=surname.upper(),
            given_names=given_names,
            full_name=full_name,
            passport_number=passport_number or None,
            nationality=nationality or None,
            date_of_birth=datetime.strptime(date_of_birth, '%Y-%m-%d').date() if date_of_birth else None,
            visa_type=visa_type,
            destination_country=destination_country or None,
            visa_purpose=visa_purpose or None,
            status='draft',
            notes=notes or None,
            created_by_id=current_user.id
        )

        db.session.add(applicant)
        db.session.commit()

        # Handle passport copy upload if provided
        passport_file = request.files.get('passport_copy')
        if passport_file and passport_file.filename and allowed_file(passport_file.filename):
            applicant_dir = get_applicant_directory(applicant.id)
            os.makedirs(applicant_dir, exist_ok=True)

            original_filename = secure_filename(passport_file.filename)
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{original_filename}"
            file_path = os.path.join(applicant_dir, filename)
            passport_file.save(file_path)

            relative_path = os.path.join(str(applicant.id), filename)
            document = Document(
                applicant_id=applicant.id,
                filename=filename,
                original_filename=original_filename,
                file_path=relative_path,
                doc_type='passport_copy',
                uploaded_by_id=current_user.id
            )
            db.session.add(document)
            applicant.status = 'documents_uploaded'
            db.session.commit()

        flash(f'Applicant {full_name} created successfully!', 'success')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant.id))

    return render_template('applicants/form.html', applicant=None)


@applicants_bp.route('/<int:applicant_id>', methods=['GET'])
@login_required
def view_applicant(applicant_id):
    """View applicant details"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this applicant.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    documents = Document.query.filter_by(applicant_id=applicant_id).order_by(desc(Document.uploaded_at)).all()
    qc_reports = QCReport.query.filter_by(applicant_id=applicant_id).order_by(desc(QCReport.run_at)).all()

    return render_template('applicants/detail.html', applicant=applicant, documents=documents, qc_reports=qc_reports)


@applicants_bp.route('/<int:applicant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_applicant(applicant_id):
    """Edit applicant"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to edit this applicant.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    if request.method == 'POST':
        client_type = request.form.get('client_type', 'retail').strip()
        corporate_name = request.form.get('corporate_name', '').strip()
        crm_id = request.form.get('crm_id', '').strip()
        surname = request.form.get('surname', '').strip()
        given_names = request.form.get('given_names', '').strip()
        passport_number = request.form.get('passport_number', '').strip()
        nationality = request.form.get('nationality', '').strip()
        date_of_birth = request.form.get('date_of_birth', '').strip()
        visa_type = request.form.get('visa_type', '').strip()
        destination_country = request.form.get('destination_country', '').strip()
        visa_purpose = request.form.get('visa_purpose', '').strip()
        notes = request.form.get('notes', '').strip()

        if not surname or not given_names:
            flash('Surname and Given Names are required.', 'danger')
            return render_template('applicants/form.html', applicant=applicant)

        if not visa_type:
            flash('Visa type is required.', 'danger')
            return render_template('applicants/form.html', applicant=applicant)

        applicant.client_type = client_type
        applicant.corporate_name = corporate_name or None
        applicant.crm_id = crm_id or None
        applicant.surname = surname.upper()
        applicant.given_names = given_names
        applicant.full_name = f"{surname.upper()}, {given_names}"
        applicant.passport_number = passport_number or None
        applicant.nationality = nationality or None
        applicant.date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d').date() if date_of_birth else None
        applicant.visa_type = visa_type
        applicant.destination_country = destination_country or None
        applicant.visa_purpose = visa_purpose or None
        applicant.notes = notes or None
        applicant.updated_at = datetime.utcnow()

        db.session.commit()

        flash(f'Applicant {applicant.full_name} updated successfully!', 'success')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant.id))

    return render_template('applicants/form.html', applicant=applicant)


@applicants_bp.route('/<int:applicant_id>/upload', methods=['POST'])
@login_required
def upload_document(applicant_id):
    """Upload document for applicant"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        return redirect(url_for('applicants.list_applicants')), 403

    if 'file' not in request.files:
        flash('No file provided.', 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    if not allowed_file(file.filename):
        flash('File type not allowed. Allowed types: ' + ', '.join(current_app.config['ALLOWED_EXTENSIONS']), 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    # Create applicant directory if it doesn't exist
    applicant_dir = get_applicant_directory(applicant_id)
    os.makedirs(applicant_dir, exist_ok=True)

    # Save file with secure name
    original_filename = secure_filename(file.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{original_filename}"
    file_path = os.path.join(applicant_dir, filename)

    file.save(file_path)

    # Detect document type if PDF
    doc_type = 'other'
    if original_filename.lower().endswith('.pdf'):
        try:
            pages = extract_text_from_pdf(file_path)
            detected_type = detect_document_type(pages)
            # Map detected type to our model choices
            type_map = {
                'schengen_visa': 'visa_application',
                'uk_visa': 'visa_application',
                'france_receipt': 'visa_application',
                'passport_copy': 'passport_copy',
                'bank_statement': 'bank_statement',
                'flight_ticket': 'flight_ticket',
                'hotel_booking': 'hotel_booking',
                'invitation_letter': 'invitation_letter',
                'covering_letter': 'cover_letter',
                'travel_insurance': 'other',
            }
            doc_type = type_map.get(detected_type, 'other')
        except Exception:
            doc_type = 'other'

    # Store in database with relative path
    relative_path = os.path.join(str(applicant_id), filename)
    document = Document(
        applicant_id=applicant_id,
        filename=filename,
        original_filename=original_filename,
        file_path=relative_path,
        doc_type=doc_type,
        uploaded_by_id=current_user.id
    )

    db.session.add(document)

    # Update applicant status if this is the first document
    if not applicant.documents:
        applicant.status = 'documents_uploaded'

    applicant.updated_at = datetime.utcnow()
    db.session.commit()

    flash(f'Document {original_filename} uploaded successfully!', 'success')
    return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))


@applicants_bp.route('/<int:applicant_id>/documents/<int:doc_id>/download', methods=['GET'])
@login_required
def download_document(applicant_id, doc_id):
    """Download document"""
    applicant = Applicant.query.get_or_404(applicant_id)
    document = Document.query.get_or_404(doc_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this document.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], document.file_path)
    if not os.path.exists(file_path):
        flash('File not found.', 'danger')
        return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    return send_file(file_path, as_attachment=True, download_name=document.original_filename)


@applicants_bp.route('/<int:applicant_id>/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(applicant_id, doc_id):
    """Delete document"""
    applicant = Applicant.query.get_or_404(applicant_id)
    document = Document.query.get_or_404(doc_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to delete this document.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    # Delete from disk
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], document.file_path)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    original_filename = document.original_filename
    db.session.delete(document)
    db.session.commit()

    flash(f'Document {original_filename} deleted successfully!', 'success')
    return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))
