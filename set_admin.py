
import argparse
import os
from app import create_app, db
from app.models import User

# This script now uses the Flask application context to interact with the database
# through SQLAlchemy, making it compatible with the production environment on Render.

def set_user_as_admin(email):
    """
    Find a user by email and set them as an administrator using SQLAlchemy.
    """
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=email).first()

        if user is None:
            print(f"Error: User with email '{email}' not found.")
            return

        if user.is_admin:
            print(f"User '{user.username}' (Email: {email}) is already an administrator.")
            return

        # Set the user as an administrator
        user.is_admin = True
        db.session.commit()

        print(f"Success! User '{user.username}' (Email: {email}) has been set as an administrator.")
        print("The user will have admin privileges upon their next login.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Set a user as an administrator.")
    parser.add_argument("email", type=str, help="The email address of the user to be set as an administrator.")
    
    args = parser.parse_args()
    
    set_user_as_admin(args.email) 