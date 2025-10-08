import os
import sys

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db

def add_columns():
    """
    Adds upload_status, total_images, and uploaded_images to the feedback table
    using the application's SQLAlchemy context.
    """
    app = create_app()
    with app.app_context():
        try:
            with db.engine.connect() as connection:
                # Use SQLAlchemy's Inspector to check for columns
                inspector = db.inspect(db.engine)
                columns = [col['name'] for col in inspector.get_columns('feedback')]

                if 'upload_status' not in columns:
                    connection.execute(db.text("ALTER TABLE feedback ADD COLUMN upload_status VARCHAR(20) DEFAULT 'complete' NOT NULL"))
                    print("Added 'upload_status' column to 'feedback' table.")

                if 'total_images' not in columns:
                    connection.execute(db.text("ALTER TABLE feedback ADD COLUMN total_images INTEGER DEFAULT 0 NOT NULL"))
                    print("Added 'total_images' column to 'feedback' table.")

                if 'uploaded_images' not in columns:
                    connection.execute(db.text("ALTER TABLE feedback ADD COLUMN uploaded_images INTEGER DEFAULT 0 NOT NULL"))
                    print("Added 'uploaded_images' column to 'feedback' table.")
                
                # The connection commits automatically with `db.text` in this context
                print("Migration check complete.")

        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == '__main__':
    add_columns()
