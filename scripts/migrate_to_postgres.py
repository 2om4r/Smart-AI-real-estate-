import os
import sys

# Add parent directory to path to import app and models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def migrate_data():
    app = create_app()
    with app.app_context():
        print("Starting Database Migration to PostgreSQL...")
        
        # Local SQLite Session
        local_session = db.session
        
        # Remote PostgreSQL URL from Render
        remote_url = "postgresql://real_estate_e2e5_user:JsiBREIhvdvYSOvDHQ292cksUaE8X5eA@dpg-d8d0hb8js32c73f2jfg0-a.oregon-postgres.render.com/real_estate_e2e5"
        
        try:
            remote_engine = create_engine(remote_url)
            RemoteSession = sessionmaker(bind=remote_engine)
            remote_session = RemoteSession()
            print("Successfully connected to Remote PostgreSQL.")
        except Exception as e:
            print(f"Failed to connect to Remote DB: {e}")
            return

        print("\n1. Creating tables on Remote PostgreSQL if they don't exist...")
        db.metadata.create_all(remote_engine)
        print("Tables schema verified.")

        # Get all tables sorted by foreign key dependencies to avoid constraint errors
        tables = db.metadata.sorted_tables
        
        print("\n2. Beginning data migration...")
        for table in tables:
            print(f"\nProcessing table: '{table.name}'...")
            
            # Fetch all rows from local SQLite
            rows = local_session.execute(table.select()).fetchall()
            
            if rows:
                print(f" -> Found {len(rows)} rows locally. Preparing to migrate...")
                
                # Clear existing data in remote table to avoid duplicate primary keys
                remote_session.execute(table.delete())
                
                # Convert rows to dictionaries
                row_dicts = [{col.name: getattr(row, col.name) for col in table.columns} for row in rows]
                
                # Insert into remote Postgres
                try:
                    remote_session.execute(table.insert(), row_dicts)
                    remote_session.commit()
                    print(f" -> Successfully inserted {len(rows)} rows into remote '{table.name}'.")
                except Exception as e:
                    remote_session.rollback()
                    print(f" -> ERROR migrating '{table.name}': {e}")
            else:
                print(f" -> No data found. Skipping.")
                
        print("\n✅ MIGRATION COMPLETE! Your Render database is now fully populated with all properties.")

if __name__ == '__main__':
    migrate_data()
