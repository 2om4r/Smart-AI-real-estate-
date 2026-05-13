import os
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing other modules
load_dotenv()

from flask import Flask, url_for
from config import Config
from extensions import db, migrate, login_manager
from routes import main

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Register blueprints
    app.register_blueprint(main)

    # ── Template filter: resolve property image to a displayable URL ──────────
    @app.template_filter('property_image_url')
    def property_image_url(filename):
        """Return external URLs unchanged; convert local filenames to static URL."""
        if not filename:
            return ''
        if filename.startswith('http://') or filename.startswith('https://'):
            return filename
        return url_for('static', filename=f'uploads/{filename}')

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5002)

