import sqlite3
import os
import sys

# Add the project root to the Python path to allow importing from 'app'
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

DB_PATH = os.path.join(PROJECT_ROOT, 'database', 'user_data.db')

def set_admin_status(phone_number, is_admin=1):
    """
    Connect to the database and set the is_admin field of the specified phone number user to 1.
    """
    if not phone_number:
        print("Please enter a phone number.")
        return

    print(f"Connecting to database at: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database file does not exist.")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # First, check if the user exists
        cursor.execute("SELECT * FROM users WHERE phone_number = ?", (phone_number,))
        user = cursor.fetchone()

        if user:
            # Update the user's is_admin status
            cursor.execute("UPDATE users SET is_admin = ? WHERE phone_number = ?", (is_admin, phone_number))
            conn.commit()
            print(f"Successfully set user with phone number {phone_number} as admin (is_admin = {is_admin}).")
        else:
            print(f"No user found with phone number: {phone_number}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    # !!! IMPORTANT !!!
    # !!! PLEASE REPLACE THIS WITH YOUR ACTUAL ADMIN PHONE NUMBER !!!
    admin_phone_number = "18700437298"
    set_admin_status(admin_phone_number)

    if len(sys.argv) > 1:
        # Allow passing phone number as a command-line argument
        set_admin_status(sys.argv[1])
    elif admin_phone_number != "18700437298":
        set_admin_status(admin_phone_number)
    else:
        print("Please edit the script 'scripts/set_admin.py' to set your phone number,")
        print("or provide it as a command-line argument:")
        print("e.g., python scripts/set_admin.py 18700437298") 