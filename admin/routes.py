"""
Admin routes for VisaDesk
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import desc
from extensions import db
from models import User

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)

    return decorated_function


@admin_bp.route('/users', methods=['GET'])
@login_required
@admin_required
def list_users():
    """List all users"""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    query = User.query

    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.full_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )

    query = query.order_by(desc(User.created_at))
    pagination = query.paginate(page=page, per_page=20)
    users = pagination.items

    return render_template('admin/users.html', users=users, pagination=pagination, search=search)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Add new user"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'executive').strip()

        # Validation
        if not username or not email or not password:
            flash('Username, email, and password are required.', 'danger')
            return render_template('admin/user_form.html', user=None)

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return render_template('admin/user_form.html', user=None)

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('admin/user_form.html', user=None)

        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return render_template('admin/user_form.html', user=None)

        if role not in ['admin', 'executive']:
            flash('Invalid role.', 'danger')
            return render_template('admin/user_form.html', user=None)

        user = User(
            username=username,
            email=email,
            full_name=full_name or None,
            role=role,
            is_active=True
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash(f'User {username} created successfully!', 'success')
        return redirect(url_for('admin.list_users'))

    return render_template('admin/user_form.html', user=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', 'executive').strip()
        password = request.form.get('password', '').strip()

        # Check email uniqueness if changed
        if email != user.email and User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return render_template('admin/user_form.html', user=user)

        if role not in ['admin', 'executive']:
            flash('Invalid role.', 'danger')
            return render_template('admin/user_form.html', user=user)

        user.email = email
        user.full_name = full_name or None
        user.role = role

        if password:
            if len(password) < 8:
                flash('Password must be at least 8 characters long.', 'danger')
                return render_template('admin/user_form.html', user=user)
            user.set_password(password)

        db.session.commit()

        flash(f'User {user.username} updated successfully!', 'success')
        return redirect(url_for('admin.list_users'))

    return render_template('admin/user_form.html', user=user)


@admin_bp.route('/users/<int:user_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_user(user_id):
    """Deactivate user"""
    user = User.query.get_or_404(user_id)

    # Prevent deactivating the current user
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin.list_users'))

    user.is_active = False
    db.session.commit()

    flash(f'User {user.username} deactivated successfully!', 'success')
    return redirect(url_for('admin.list_users'))


@admin_bp.route('/users/<int:user_id>/activate', methods=['POST'])
@login_required
@admin_required
def activate_user(user_id):
    """Activate user"""
    user = User.query.get_or_404(user_id)

    user.is_active = True
    db.session.commit()

    flash(f'User {user.username} activated successfully!', 'success')
    return redirect(url_for('admin.list_users'))
