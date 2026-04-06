"""
Dashboard routes for VisaDesk
"""
from datetime import datetime, timedelta
from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, and_, or_
from extensions import db
from models import Applicant, Document, QCReport, User

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/', methods=['GET'])
@login_required
def index():
    """Main dashboard"""
    if current_user.is_admin():
        return admin_dashboard()
    else:
        return executive_dashboard()


def executive_dashboard():
    """Executive dashboard - personal statistics"""
    # Count applicants
    total_applicants = Applicant.query.filter_by(created_by_id=current_user.id).count()
    draft_applicants = Applicant.query.filter_by(created_by_id=current_user.id, status='draft').count()
    pending_qc = Applicant.query.filter_by(
        created_by_id=current_user.id,
        status='documents_uploaded'
    ).count()
    qc_passed = Applicant.query.filter_by(created_by_id=current_user.id, status='qc_passed').count()
    qc_failed = Applicant.query.filter_by(created_by_id=current_user.id, status='qc_failed').count()

    # Recent QC results
    recent_reports = QCReport.query.join(Applicant).filter(
        Applicant.created_by_id == current_user.id
    ).order_by(QCReport.run_at.desc()).limit(5).all()

    # QC pass rate
    total_qc_runs = QCReport.query.join(Applicant).filter(
        Applicant.created_by_id == current_user.id
    ).count()
    qc_passed_runs = QCReport.query.join(Applicant).filter(
        and_(
            Applicant.created_by_id == current_user.id,
            QCReport.overall_status == 'pass'
        )
    ).count()
    qc_pass_rate = round((qc_passed_runs / total_qc_runs * 100), 1) if total_qc_runs > 0 else 0

    return render_template(
        'dashboard/index.html',
        total_applicants=total_applicants,
        draft_applicants=draft_applicants,
        pending_qc=pending_qc,
        qc_passed=qc_passed,
        qc_failed=qc_failed,
        recent_reports=recent_reports,
        qc_pass_rate=qc_pass_rate,
        total_qc_runs=total_qc_runs,
        is_admin=False
    )


def admin_dashboard():
    """Admin dashboard - team-wide statistics"""
    # Overall statistics
    total_applicants = Applicant.query.count()
    total_users = User.query.filter_by(is_active=True).count()
    total_qc_runs = QCReport.query.count()

    # Status distribution
    status_dist = db.session.query(
        Applicant.status,
        func.count(Applicant.id).label('count')
    ).group_by(Applicant.status).all()

    # QC statistics
    qc_passed = QCReport.query.filter_by(overall_status='pass').count()
    qc_failed = QCReport.query.filter_by(overall_status='fail').count()
    qc_pass_rate = round((qc_passed / total_qc_runs * 100), 1) if total_qc_runs > 0 else 0

    # Executive performance
    exec_stats = db.session.query(
        User.id,
        User.username,
        User.full_name,
        func.count(Applicant.id).label('applicant_count'),
        func.sum(func.cast(QCReport.overall_status == 'pass', db.Integer)).label('qc_passed_count')
    ).outerjoin(Applicant, Applicant.created_by_id == User.id).outerjoin(
        QCReport, QCReport.applicant_id == Applicant.id
    ).filter(User.role == 'executive', User.is_active == True).group_by(User.id).all()

    # Last 7 days activity
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    weekly_applicants = Applicant.query.filter(
        Applicant.created_at >= seven_days_ago
    ).count()
    weekly_qc_runs = QCReport.query.filter(
        QCReport.run_at >= seven_days_ago
    ).count()

    return render_template(
        'dashboard/index.html',
        total_applicants=total_applicants,
        total_users=total_users,
        total_qc_runs=total_qc_runs,
        qc_pass_rate=qc_pass_rate,
        status_dist=status_dist,
        exec_stats=exec_stats,
        weekly_applicants=weekly_applicants,
        weekly_qc_runs=weekly_qc_runs,
        is_admin=True
    )


@dashboard_bp.route('/data/status-distribution', methods=['GET'])
@login_required
def status_distribution():
    """Get status distribution data for chart"""
    if current_user.is_admin():
        query = Applicant.query
    else:
        query = Applicant.query.filter_by(created_by_id=current_user.id)

    status_dist = db.session.query(
        Applicant.status,
        func.count(Applicant.id).label('count')
    ).select_from(Applicant).filter(
        *([Applicant.created_by_id == current_user.id] if not current_user.is_admin() else [])
    ).group_by(Applicant.status).all()

    status_labels = {
        'draft': 'Draft',
        'documents_uploaded': 'Documents Uploaded',
        'qc_passed': 'QC Passed',
        'qc_failed': 'QC Failed',
        'submitted': 'Submitted',
        'approved': 'Approved',
        'rejected': 'Rejected',
    }

    labels = [status_labels.get(s[0], s[0]) for s in status_dist]
    data = [s[1] for s in status_dist]

    return jsonify({
        'labels': labels,
        'data': data
    })


@dashboard_bp.route('/data/weekly-volume', methods=['GET'])
@login_required
def weekly_volume():
    """Get weekly processing volume data"""
    # Get data for last 30 days, grouped by week
    today = datetime.utcnow()
    data_points = []

    for i in range(4):
        week_start = today - timedelta(days=today.weekday() + 7 * (3 - i))
        week_end = week_start + timedelta(days=7)

        if current_user.is_admin():
            applicant_count = Applicant.query.filter(
                and_(
                    Applicant.created_at >= week_start,
                    Applicant.created_at < week_end
                )
            ).count()
            qc_count = QCReport.query.filter(
                and_(
                    QCReport.run_at >= week_start,
                    QCReport.run_at < week_end
                )
            ).count()
        else:
            applicant_count = Applicant.query.filter(
                and_(
                    Applicant.created_by_id == current_user.id,
                    Applicant.created_at >= week_start,
                    Applicant.created_at < week_end
                )
            ).count()
            qc_count = QCReport.query.join(Applicant).filter(
                and_(
                    Applicant.created_by_id == current_user.id,
                    QCReport.run_at >= week_start,
                    QCReport.run_at < week_end
                )
            ).count()

        week_label = week_start.strftime('%b %d')
        data_points.append({
            'week': week_label,
            'applicants': applicant_count,
            'qc_runs': qc_count
        })

    return jsonify(data_points)


@dashboard_bp.route('/executives', methods=['GET'])
@login_required
def executive_performance():
    """Executive performance dashboard (admin only)"""
    if not current_user.is_admin():
        return {'error': 'Access denied'}, 403

    # Get all executives with their stats
    exec_stats = db.session.query(
        User.id,
        User.username,
        User.full_name,
        func.count(distinct(Applicant.id)).label('applicant_count'),
        func.count(distinct(QCReport.id)).label('qc_run_count'),
        func.sum(func.cast(QCReport.overall_status == 'pass', db.Integer)).label('qc_passed_count')
    ).select_from(User).outerjoin(
        Applicant, Applicant.created_by_id == User.id
    ).outerjoin(
        QCReport, QCReport.applicant_id == Applicant.id
    ).filter(User.role == 'executive', User.is_active == True).group_by(User.id).all()

    # Calculate pass rates
    exec_performance = []
    for exec_stat in exec_stats:
        user_id, username, full_name, app_count, qc_count, qc_passed = exec_stat
        pass_rate = round((qc_passed / qc_count * 100), 1) if qc_count and qc_count > 0 else 0
        exec_performance.append({
            'user_id': user_id,
            'username': username,
            'full_name': full_name or username,
            'applicant_count': app_count or 0,
            'qc_run_count': qc_count or 0,
            'qc_passed_count': qc_passed or 0,
            'pass_rate': pass_rate
        })

    return render_template('dashboard/executive.html', executives=exec_performance)
