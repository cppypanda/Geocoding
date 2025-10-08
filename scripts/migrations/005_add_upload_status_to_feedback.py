import sqlite3
import os
from dotenv import load_dotenv

def upgrade():
    """
    Adds upload_status, total_images, and uploaded_images columns to the feedback table.
    """
    # Load environment variables from .env file
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    load_dotenv(dotenv_path=dotenv_path)

    database_url = os.getenv('DATABASE_URL')
    
    # If DATABASE_URL is not set, fallback to a default location
    if not database_url:
        print("DATABASE_URL not found in environment, falling back to default 'instance/prod.db'")
        database_url = 'sqlite:///instance/prod.db'

    if not database_url.startswith('sqlite:///'):
        print("DATABASE_URL is not a sqlite database. Migration skipped.")
        return

    # Assuming the format is sqlite:///path/to/db
    db_path = database_url.split('sqlite:///')[-1]
    
    # In case of Windows paths, the absolute path might start with a drive letter.
    # The project root needs to be prepended if the path is relative.
    if not os.path.isabs(db_path):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        db_path = os.path.join(project_root, db_path)

    # Ensure the directory for the database exists
    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table exists first
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'")
        if cursor.fetchone() is None:
            print("Error: 'feedback' table does not exist in the database.")
            return

        # Check if columns exist
        cursor.execute("PRAGMA table_info(feedback)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'upload_status' not in columns:
            cursor.execute("ALTER TABLE feedback ADD COLUMN upload_status VARCHAR(20) DEFAULT 'complete' NOT NULL")
        
        if 'total_images' not in columns:
            cursor.execute("ALTER TABLE feedback ADD COLUMN total_images INTEGER DEFAULT 0 NOT NULL")

        if 'uploaded_images' not in columns:
            cursor.execute("ALTER TABLE feedback ADD COLUMN uploaded_images INTEGER DEFAULT 0 NOT NULL")

        conn.commit()
        print("Database migration successful.")
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    upgrade()
