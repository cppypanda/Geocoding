import sqlite3
import os

# A more robust way to find the project root directory
# This assumes the script is in 'scripts/migrations' and the DB is in 'database' at the project root.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'user_data.db')

def add_recharge_orders_table():
    """
    Connects to the database and adds the recharge_orders table.
    """
    print(f"Connecting to database at: {DB_PATH}")
    if not os.path.exists(os.path.dirname(DB_PATH)):
        print(f"Database directory does not exist. Creating it now: {os.path.dirname(DB_PATH)}")
        os.makedirs(os.path.dirname(DB_PATH))
    elif not os.path.exists(DB_PATH):
        print(f"Database file does not exist at: {DB_PATH}")
        # We can't proceed if the DB file isn't there, as it implies user_table may also be missing.
        # The main app setup should create the initial DB.
        # For a migration, we assume the DB exists.
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print("Creating recharge_orders table...")
        
        # SQL to create the table
        # We include an 'id' as a primary key.
        # 'order_number' should be unique to identify transactions.
        # 'status' will track the order's state (e.g., PENDING, COMPLETED, CANCELLED).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recharge_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_number TEXT NOT NULL UNIQUE,
                package_name TEXT NOT NULL,
                amount REAL NOT NULL,
                points INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        print("recharge_orders table created successfully (if it didn't exist).")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    add_recharge_orders_table() 