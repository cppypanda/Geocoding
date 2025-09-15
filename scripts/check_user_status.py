import sqlite3
import os
import sys

# Add the project root to the Python path to allow importing from 'app'
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'user_data.db')

def check_user_status(phone_number):
    """
    Connects to the database and prints the full status of a user.
    """
    if not phone_number:
        print("Please provide a phone number.")
        return

    print(f"Connecting to database at: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database file does not exist.")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE phone_number = ?", (phone_number,))
        user = cursor.fetchone()

        if user:
            print("\\n--- User Status ---")
            for key in user.keys():
                print(f"{key}: {user[key]}")
            print("-------------------\\n")
        else:
            print(f"No user found with phone number: {phone_number}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    # You can run this script from the command line:
    # python scripts/check_user_status.py YOUR_PHONE_NUMBER
    # We will use the known phone number for this check.
    admin_phone_number = "18700437298"
    check_user_status(admin_phone_number) 