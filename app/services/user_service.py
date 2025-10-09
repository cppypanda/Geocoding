import hashlib
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from sqlalchemy import or_

from .. import db
from ..models import User, BonusRewardLog

def is_no_password_placeholder(hash_value):
    """Returns True if the given password hash value indicates 'no password set'.
    This is backward-compatible with legacy placeholder values such as 'not_set'.
    """
    try:
        placeholder = current_app.config.get('NO_PASSWORD_PLACEHOLDER')
    except Exception:
        placeholder = None
    if not hash_value:
        return True
    legacy_placeholders = {'not_set'}
    if placeholder:
        legacy_placeholders.add(placeholder)
    return hash_value in legacy_placeholders

def get_user_by_username(username):
    """Gets a user by their username."""
    return User.query.filter_by(username=username).first()

def get_user_by_email(email):
    """Gets a user by their email."""
    return User.query.filter_by(email=email).first()

def get_user_by_id(user_id):
    """Gets a user by their ID."""
    return User.query.get(user_id)

def update_username(user_id, new_username):
    """Updates a user's username."""
    user = get_user_by_id(user_id)
    if not user:
        return False
    try:
        user.username = new_username
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating username: {e}")
        return False

def create_user_with_password(username, password, email):
    """Creates a new user with password-based registration."""
    if get_user_by_email(email) or (username and get_user_by_username(username)):
        return None
    
    hashed_password = generate_password_hash(password)
    # Determine whether this email has already received the new user reward
    existing_reward_log = BonusRewardLog.query.filter_by(email=email).first()
    points = 0 if existing_reward_log else current_app.config.get('NEW_USER_REWARD_POINTS', 100)
    
    new_user = User(
        username=username,
        password_hash=hashed_password,
        email=email,
        points=points,
        created_at=datetime.utcnow(),
        registration_date=datetime.utcnow()
    )
    
    try:
        db.session.add(new_user)
        # Record that this email has received the new user reward, if not already recorded
        if points > 0 and not existing_reward_log:
            db.session.add(BonusRewardLog(email=email))
        db.session.commit()
        return new_user
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user with password: {e}")
        return None

def create_user_for_email_login(email):
    """Creates a new user for email verification login."""
    if get_user_by_email(email):
        return None
        
    # Determine whether this email has already received the new user reward
    existing_reward_log = BonusRewardLog.query.filter_by(email=email).first()
    points = 0 if existing_reward_log else current_app.config.get('NEW_USER_REWARD_POINTS', 100)
    
    new_user = User(
        email=email,
        password_hash=current_app.config['NO_PASSWORD_PLACEHOLDER'],
        username=None,
        points=points,
        created_at=datetime.utcnow(),
        registration_date=datetime.utcnow()
    )
    
    try:
        db.session.add(new_user)
        # Record that this email has received the new user reward, if not already recorded
        if points > 0 and not existing_reward_log:
            db.session.add(BonusRewardLog(email=email))
        db.session.commit()
        return new_user
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user for email login: {e}")
        return None

def verify_password(username_or_email, password):
    """Verifies a user's password (supports username or email)."""
    user = User.query.filter(or_(User.username == username_or_email, User.email == username_or_email)).first()
    
    if user and user.password_hash and not is_no_password_placeholder(user.password_hash):
        return check_password_hash(user.password_hash, password)
    return False

def update_user_last_login(user_id):
    """Updates the last login timestamp for a user."""
    user = get_user_by_id(user_id)
    if user:
        try:
            user.last_login_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating last login: {e}")

def set_password_for_user(email, password):
    """Sets or updates the password for an existing user."""
    user = get_user_by_email(email)
    if not user:
        return False
        
    hashed_password = generate_password_hash(password)
    user.password_hash = hashed_password
    
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting password: {e}")
        return False

def add_points(user_id, points_to_add):
    """Adds points to a user's account."""
    user = get_user_by_id(user_id)
    if user:
        try:
            user.points = (user.points or 0) + points_to_add
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding points: {e}")

def update_user_api_key_in_users_table(user_id, service_name, api_key):
    """Updates a user's API key in the main users table."""
    key_column_map = {
        'amap': 'amap_key',
        'baidu': 'baidu_key',
        'tianditu': 'tianditu_key',
        'zhipuai': 'ai_key'
    }
    
    column_name = key_column_map.get(service_name)
    if not column_name:
        current_app.logger.warning(f"Unknown service name for API key update: {service_name}")
        return

    user = get_user_by_id(user_id)
    if user:
        try:
            setattr(user, column_name, api_key)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating user API key for {column_name}: {e}")

def update_admin_status(user, is_admin):
    """Updates the is_admin status for a user."""
    try:
        user.is_admin = is_admin
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating admin status for user {user.id}: {e}") 