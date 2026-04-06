"""
Authentication routes for VisaDesk
"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login route"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') is not None

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('auth/login.html')

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('Invalid username or password.', 'danger')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('Your account has been deactivated. Contact an administrator.', 'danger')
            return render_template('auth/login.html')

        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()

        login_user(user, remember=remember_me)
        flash(f'Welcome, {user.full_name or user.username}!', 'success')

        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(url_for('dashboard.index'))

    return render_template('auth/login.html')


@auth_bp.route('/logout', methods=['GET'])
@login_required
def logout():
    """Logout route"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password route"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_password or not new_password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('auth/change_password.html')

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html')

        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('auth/change_password.html')

        if len(new_password) < 8:
            flash('New password must be at least 8 characters long.', 'danger')
            return render_template('auth/change_password.html')

        current_user.set_password(new_password)
        db.session.commit()

        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard.index'))

    return render_template('auth/change_password.html')
