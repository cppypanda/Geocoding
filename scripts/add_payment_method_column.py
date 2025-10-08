import os
import sys
from sqlalchemy import create_engine, text

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.config import Config

def add_payment_method_column():
    """Adds the payment_method column to the recharge_orders table."""
    
    # Use the database URI from your app's configuration
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    if not db_uri:
        print("Error: SQLALCHEMY_DATABASE_URI is not set in the configuration.")
        return

    engine = create_engine(db_uri)
    
    # SQL statement to add the column. 
    # This is for PostgreSQL. If you use a different DB, this might need to change.
    add_column_sql = text("""
        ALTER TABLE recharge_orders
        ADD COLUMN IF NOT EXISTS payment_method VARCHAR;
    """)

    try:
        with engine.connect() as connection:
            print("Connecting to the database...")
            connection.execute(add_column_sql)
            connection.commit()
            print("Successfully added 'payment_method' column to 'recharge_orders' table.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    add_payment_method_column()
