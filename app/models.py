from datetime import datetime
from sqlalchemy import func
from . import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# Using SQLAlchemy's declarative base, which is accessed through db.Model

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    password_hash = db.Column(db.String, nullable=True)
    username = db.Column(db.String, unique=True, nullable=True)
    points = db.Column(db.Integer, default=0)
    avatar_url = db.Column(db.String, nullable=True)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    referral_code = db.Column(db.String, unique=True, nullable=True)
    referrer_id = db.Column(db.Integer, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Kept for simple key storage, but more complex relations are in UserApiKey
    amap_key = db.Column(db.String, nullable=True)
    baidu_key = db.Column(db.String, nullable=True)
    tianditu_key = db.Column(db.String, nullable=True)
    ai_key = db.Column(db.String, nullable=True)

    # Relationships
    feedbacks = db.relationship('Feedback', backref='user', lazy=True)
    saved_sessions = db.relationship('UserSavedSession', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    geocoding_history = db.relationship('GeocodingHistory', backref='user', lazy=True)
    tasks = db.relationship('Task', backref='user', lazy=True)
    api_keys = db.relationship('UserApiKey', backref='user', lazy=True)
    recharge_orders = db.relationship('RechargeOrder', backref='user', lazy=True)
    geocoding_tasks = db.relationship('GeocodingTask', backref='user', lazy=True)

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    description = db.Column(db.Text, nullable=False)
    image_paths = db.Column(db.Text, nullable=True) # Storing as JSON string
    contact_email = db.Column(db.String, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String, default='new')
    category = db.Column(db.String, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True) # Renamed from 'metadata' to avoid keyword conflict
    upload_status = db.Column(db.String, default='complete') # e.g., 'pending_images', 'complete'
    total_images = db.Column(db.Integer, default=0)
    uploaded_images = db.Column(db.Integer, default=0)
    replies_json = db.Column(db.Text, nullable=True) # To store a JSON list of replies

class UserSavedSession(db.Model):
    __tablename__ = 'user_saved_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_name = db.Column(db.String, nullable=False)
    results_data = db.Column(db.Text, nullable=False) # JSON string
    last_saved_at = db.Column(db.DateTime, default=datetime.utcnow)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GeocodingHistory(db.Model):
    __tablename__ = 'geocoding_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    address = db.Column(db.String, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_name = db.Column(db.String, nullable=False)
    result_data = db.Column(db.Text, nullable=False) # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'task_name'),)

class Referral(db.Model):
    __tablename__ = 'referrals'
    id = db.Column(db.Integer, primary_key=True)
    referrer_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    invitee_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserApiKey(db.Model):
    __tablename__ = 'user_api_keys'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    service_name = db.Column(db.String(20)) # Renamed from 'provider'
    key_value = db.Column(db.String)
    share_count = db.Column(db.Integer, default=1)
    earned_points = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='active')
    fail_count = db.Column(db.Integer, default=0)
    last_checked = db.Column(db.DateTime, nullable=True)
    cooldown_until = db.Column(db.DateTime, nullable=True) # Add the missing field
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RechargeOrder(db.Model):
    __tablename__ = 'recharge_orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_number = db.Column(db.String, unique=True, nullable=False)
    package_name = db.Column(db.String, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    points = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String, nullable=False, default='PENDING') # PENDING, COMPLETED, CANCELLED
    payment_method = db.Column(db.String, nullable=True) # e.g., 'alipay', 'wechat'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

class LocationType(db.Model):
    __tablename__ = 'location_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True, nullable=False)
    status = db.Column(db.String, nullable=False, default='pending') # pending, approved, rejected
    source = db.Column(db.String, nullable=False, default='user_generated') # user_generated, system_default
    usage_count = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class ApiRequestLog(db.Model):
    __tablename__ = 'api_request_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_name = db.Column(db.String, nullable=False)
    request_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    request_count = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('user_id', 'service_name', 'request_date', name='_user_service_date_uc'),)

class BonusRewardLog(db.Model):
    __tablename__ = 'bonus_reward_logs'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GeocodingTask(db.Model):
    __tablename__ = 'geocoding_tasks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    task_name = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship to AddressLog
    addresses = db.relationship('AddressLog', backref='task', lazy=True, cascade="all, delete-orphan")

class AddressLog(db.Model):
    __tablename__ = 'address_logs'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('geocoding_tasks.id'), nullable=False, index=True)
    address_keyword = db.Column(db.String(512), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)