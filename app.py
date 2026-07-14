import os
from flask import Flask
from flask_login import LoginManager

from backend.models import db, User
from backend.routes import auth_bp, admin_bp, staff_bp, user_bp
from werkzeug.security import generate_password_hash


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = "trekking-app-secret-key-change-later"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trekking.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join("static", "upload")

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(staff_bp, url_prefix="/staff")
    app.register_blueprint(user_bp, url_prefix="/user")

    with app.app_context():
        db.create_all()
        create_default_admin()

    return app


def create_default_admin():
    existing_admin = User.query.filter_by(role="admin").first()

    if existing_admin is None:
        admin_user = User(
            username="admin",
            password_hash=generate_password_hash("admin123"),
            full_name="Admin",
            email="admin@trekapp.com",
            role="admin",
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Default admin account created -> username: admin, password: admin123")


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
