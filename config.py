import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for Flask application")
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_dir = os.path.join(basedir, 'instance', 'database')
    os.makedirs(db_dir, exist_ok=True)
    
    target_db = os.path.join(db_dir, 'real_estate.db')
    seed_db = os.path.join(basedir, 'data', 'seed_db.sqlite')
    if not os.path.exists(target_db) and os.path.exists(seed_db):
        import shutil
        shutil.copy2(seed_db, target_db)
        print("Seeded database from data/seed_db.sqlite")
        
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + target_db
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
