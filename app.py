"""
VisaDesk Flask Application Factory
"""
import os
from flask import Flask, redirect, url_for
from extensions import db, login_manager
from config import config


def create_app(config_name=None):
    """Application factory"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Register blueprints
    from auth.routes import auth_bp
    from applicants.routes import applicants_bp
    from qc.routes import qc_bp
    from dashboard.routes import dashboard_bp
    from admin.routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(applicants_bp)
    app.register_blueprint(qc_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    # Home route - redirect to dashboard or login
    @app.route('/')
    def index():
        from flask_login import current_user
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    # Create tables only in development (auto-create)
    if config_name == 'development':
        with app.app_context():
            db.create_all()

    # Register CLI commands
    @app.cli.command()
    def init_db():
        """Initialize the database and create admin user."""
        from models import User
        with app.app_context():
            db.create_all()

            # Create admin if doesn't exist
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    email='admin@visadesk.local',
                    full_name='Administrator',
                    role='admin',
                    is_active=True
                )
                admin.set_password(os.environ.get('ADMIN_PASSWORD', 'admin123'))
                db.session.add(admin)
                db.session.commit()
                print("Admin user created successfully")
            else:
                print("Admin user already exists")

            print("Database initialized successfully!")

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=9090, debug=True)
