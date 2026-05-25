import os
from dotenv import load_dotenv

load_dotenv()

from flask import Flask, url_for, session, request
from flask_login import current_user
import json
from config import Config
from extensions import db, migrate, login_manager, limiter
from routes import main

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(Config)

    import time as _t
    app.config['APP_START_TS'] = _t.time()

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    app.register_blueprint(main)

    @app.template_filter('property_image_url')
    def property_image_url(filename):
        """Return external URLs unchanged; convert local filenames to static URL."""
        if not filename:
            return ''
        if filename.startswith('http://') or filename.startswith('https://'):
            return filename
        return url_for('static', filename=f'uploads/{filename}')
        
    with open(os.path.join(app.root_path, 'translations.json'), 'r', encoding='utf-8') as f:
        app.translations = json.load(f)

    @app.context_processor
    def inject_context():
        
        if current_user.is_authenticated and hasattr(current_user, 'preferred_language'):
            lang = current_user.preferred_language or 'en'
        else:
            lang = session.get('language', 'en')
            
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

    with app.app_context():
        db.create_all()

        import logging
        _ml_logger = logging.getLogger("ml_engine")
        try:
            from ml_engine import init_ml_engine, ml
            if init_ml_engine():
                _ml_logger.info(
                    f"[ML] Engine ready: {ml.metadata.get('version')} "
                    f"({len(ml._known_areas)} areas, {len(ml.model.estimators_)} trees)"
                )
            else:
                _ml_logger.warning("[ML] Engine load failed — predictions will use CAGR fallback")
        except Exception as _ml_err:
            _ml_logger.warning(f"[ML] Engine init skipped: {_ml_err}")

        _sched_logger = logging.getLogger("scheduler")
        try:
            from extensions import init_scheduler
            
            if not os.environ.get('WERKZEUG_RUN_MAIN'):
                init_scheduler(app)
        except Exception as _sched_err:
            _sched_logger.warning(f"[Scheduler] init skipped: {_sched_err}")

        _rag_logger = logging.getLogger("rag_engine")
        try:
            from rag_engine import build_knowledge_base
            build_knowledge_base()
            _rag_logger.info("[RAG] Knowledge base ready on startup.")
        except Exception as _rag_err:
            _rag_logger.warning(
                f"[RAG] Knowledge base build skipped on startup: {_rag_err}"
            )

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5002)
