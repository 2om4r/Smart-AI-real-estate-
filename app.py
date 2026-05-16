import os
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing other modules
load_dotenv()

from flask import Flask, url_for, session, request
from flask_login import current_user
import json
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
        
    # ── Translations & Theming ──────────
    # Load translations into memory
    with open(os.path.join(app.root_path, 'translations.json'), 'r', encoding='utf-8') as f:
        app.translations = json.load(f)

    @app.context_processor
    def inject_context():
        # Determine language
        if current_user.is_authenticated and hasattr(current_user, 'preferred_language'):
            lang = current_user.preferred_language or 'en'
        else:
            lang = session.get('language', 'en')
            
        # Determine theme
        if current_user.is_authenticated and hasattr(current_user, 'theme_mode'):
            theme = current_user.theme_mode or 'light'
        else:
            theme = session.get('theme', 'light')
            
        def translate(key):
            try:
                return app.translations.get(lang, {}).get(key, app.translations.get('en', {}).get(key, key))
            except Exception:
                return key
                
        return dict(_=translate, current_lang=lang, current_theme=theme)

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5002)

