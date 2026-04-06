"""
QC check routes for VisaDesk
"""
import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from extensions import db
from models import Applicant, Document, QCReport, User
from .extractor import extract_fields
from .qc_engine import run_qc

qc_bp = Blueprint('qc', __name__, url_prefix='/qc')


@qc_bp.route('/run/<int:applicant_id>', methods=['GET', 'POST'])
@login_required
def run_qc_check(applicant_id):
    """Run QC check for an applicant"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access - only creator and admins can see
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this applicant.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    if request.method == 'POST':
        # Get visa_application document
        visa_app_doc = Document.query.filter_by(
            applicant_id=applicant_id,
            doc_type='visa_application'
        ).first()

        if not visa_app_doc:
            flash('No visa application document found. Please upload the visa application form first.', 'warning')
            return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

        # Build the full path to the visa application file
        visa_app_path = os.path.join(current_app.config['UPLOAD_FOLDER'], visa_app_doc.file_path)
        if not os.path.exists(visa_app_path):
            flash('Visa application file not found on disk.', 'danger')
            return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

        try:
            # Use the existing extract_fields() which auto-detects doc type
            visa_fields = extract_fields(visa_app_path)

            # Collect supporting documents and extract their fields
            supporting_docs = Document.query.filter_by(
                applicant_id=applicant_id
            ).filter(Document.doc_type != 'visa_application').all()

            supporting_fields_list = []
            for doc in supporting_docs:
                doc_path = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.file_path)
                if os.path.exists(doc_path):
                    fields = extract_fields(doc_path)
                    supporting_fields_list.append(fields)

            # Get check_type from form or default to 'application'
            check_type = request.form.get('check_type', 'application').lower()
            if check_type not in ('application', 'covering', 'invitation'):
                check_type = 'application'

            # Get visa_purpose from applicant record
            visa_purpose = applicant.visa_purpose or 'tourist'

            # Run QC using the existing engine signature:
            # run_qc(visa_fields, supporting_doc_fields_list, visa_purpose, check_type)
            qc_result = run_qc(visa_fields, supporting_fields_list, visa_purpose, check_type)

            # Determine overall status from qc_result
            overall_status = qc_result.get('overall_status', 'unknown')
            total_checks = qc_result.get('total_checks', 0)
            passed_checks = qc_result.get('passed', 0)
            failed_checks = qc_result.get('failed', 0)
            warning_checks = qc_result.get('warnings', 0)

            # The QC engine may use different keys - check alternatives
            if passed_checks == 0 and 'passed_checks' in qc_result:
                passed_checks = qc_result['passed_checks']
            if failed_checks == 0 and 'failed_checks' in qc_result:
                failed_checks = qc_result['failed_checks']
            if warning_checks == 0 and 'warning_checks' in qc_result:
                warning_checks = qc_result['warning_checks']

            # Save QC report
            qc_report = QCReport(
                applicant_id=applicant_id,
                run_by_id=current_user.id,
                visa_purpose=visa_purpose,
                check_type=check_type,
                overall_status=overall_status,
                total_checks=total_checks,
                passed_checks=passed_checks,
                failed_checks=failed_checks,
                warning_checks=warning_checks,
                report_data=qc_result
            )
            db.session.add(qc_report)

            # Update applicant status based on QC result
            if overall_status == 'pass':
                applicant.status = 'qc_passed'
            elif overall_status == 'fail':
                applicant.status = 'qc_failed'
            else:
                applicant.status = 'documents_uploaded'

            applicant.updated_at = datetime.utcnow()
            db.session.commit()

            flash('QC check completed successfully!', 'success')
            return redirect(url_for('qc.view_report', report_id=qc_report.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Error running QC check: {str(e)}', 'danger')
            return redirect(url_for('applicants.view_applicant', applicant_id=applicant_id))

    # GET — show the QC run page
    documents = Document.query.filter_by(applicant_id=applicant_id).all()
    has_visa_app = any(d.doc_type == 'visa_application' for d in documents)
    return render_template('qc/run.html', applicant=applicant, documents=documents, has_visa_app=has_visa_app)


@qc_bp.route('/report/<int:report_id>', methods=['GET'])
@login_required
def view_report(report_id):
    """View QC report"""
    report = QCReport.query.get_or_404(report_id)
    applicant = report.applicant

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        flash('You do not have access to this report.', 'danger')
        return redirect(url_for('applicants.list_applicants'))

    return render_template('qc/report.html', report=report, applicant=applicant)


@qc_bp.route('/history/<int:applicant_id>', methods=['GET'])
@login_required
def qc_history(applicant_id):
    """Get QC history for an applicant (JSON API)"""
    applicant = Applicant.query.get_or_404(applicant_id)

    # Check access
    if applicant.created_by_id != current_user.id and not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403

    reports = QCReport.query.filter_by(applicant_id=applicant_id).order_by(QCReport.run_at.desc()).all()

    history = []
    for report in reports:
        history.append({
            'id': report.id,
            'run_at': report.run_at.strftime('%Y-%m-%d %H:%M:%S'),
            'overall_status': report.overall_status,
            'passed_checks': report.passed_checks,
            'failed_checks': report.failed_checks,
            'total_checks': report.total_checks,
            'run_by': report.run_by.full_name or report.run_by.username
        })

    return jsonify(history)
