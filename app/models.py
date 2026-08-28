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
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
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

    __table_args__ = (
        db.UniqueConstraint('user_id', 'service_name', name='uq_user_api_key_service'),
    )

class RechargeOrder(db.Model):
    __tablename__ = 'recharge_orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_number = db.Column(db.String, unique=True, nullable=False)
    package_name = db.Column(db.String, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    points = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String, nullable=False, default='PENDING') # PENDING, COMPLETED, CANCELLED
    payment_method = db.Column(db.String, nullable=True) # alipay or yungouos
    payment_url = db.Column(db.Text, nullable=True)
    provider_trade_no = db.Column(db.String, nullable=True)
    buyer_logon_id = db.Column(db.String, nullable=True)
    notify_payload = db.Column(db.Text, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EmailVerificationCode(db.Model):
    __tablename__ = 'email_verification_codes'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(40), nullable=False)
    code_digest = db.Column(db.String(64), nullable=False)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_sent_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('email', 'purpose', name='uq_verification_email_purpose'),
        db.Index('ix_verification_email_purpose', 'email', 'purpose'),
    )
class RechargeCard(db.Model):
    __tablename__ = 'recharge_cards'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    points = db.Column(db.Integer, nullable=False)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    used_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

    # Relationship
    user = db.relationship('User', foreign_keys=[used_by], backref='used_cards', lazy=True)

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


class PointTransaction(db.Model):
    """Immutable audit trail for point charges and automatic refunds."""

    __tablename__ = 'point_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    geocoding_task_id = db.Column(
        db.Integer,
        db.ForeignKey('geocoding_tasks.id'),
        nullable=True,
        index=True,
    )
    transaction_type = db.Column(db.String(16), nullable=False, index=True)
    task_key = db.Column(db.String(64), nullable=False, index=True)
    points_delta = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)
    operation_id = db.Column(db.String(128), nullable=False, index=True)
    idempotency_key = db.Column(db.String(255), nullable=False, unique=True, index=True)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

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
    run_mode = db.Column(db.String(32), nullable=False, default='multisource', index=True)
    trigger_origin = db.Column(db.String(64), nullable=False, default='unknown', index=True)
    client_session_id = db.Column(db.String(64), nullable=True, index=True)
    client_action_id = db.Column(db.String(64), nullable=True, index=True)
    semantic_web_search_performed = db.Column(db.Boolean, nullable=False, default=False)
    semantic_web_search_success = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationship to AddressLog
    addresses = db.relationship('AddressLog', backref='task', lazy=True, cascade="all, delete-orphan")

class AddressLog(db.Model):
    __tablename__ = 'address_logs'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('geocoding_tasks.id'), nullable=False, index=True)
    address_index = db.Column(db.Integer, nullable=True)
    address_keyword = db.Column(db.String(512), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    initial_source = db.Column(db.String(64), nullable=True, index=True)
    initial_latitude_wgs84 = db.Column(db.Float, nullable=True)
    initial_longitude_wgs84 = db.Column(db.Float, nullable=True)
    final_source = db.Column(db.String(64), nullable=True, index=True)
    final_confidence = db.Column(db.Float, nullable=True)
    final_latitude_wgs84 = db.Column(db.Float, nullable=True)
    final_longitude_wgs84 = db.Column(db.Float, nullable=True)
    selection_method = db.Column(db.String(64), nullable=True, index=True)
    correction_source = db.Column(db.String(64), nullable=True, index=True)
    corrected = db.Column(db.Boolean, nullable=False, default=False, index=True)
    web_search_used = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InteractionEvent(db.Model):
    """A structured, privacy-bounded product analytics event."""

    __tablename__ = 'interaction_events'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    geocoding_task_id = db.Column(
        db.Integer,
        db.ForeignKey('geocoding_tasks.id'),
        nullable=True,
        index=True,
    )
    address_log_id = db.Column(
        db.Integer,
        db.ForeignKey('address_logs.id'),
        nullable=True,
        index=True,
    )
    client_event_id = db.Column(db.String(64), nullable=True, unique=True, index=True)
    client_action_id = db.Column(db.String(64), nullable=True, index=True)
    client_session_id = db.Column(db.String(64), nullable=True, index=True)
    event_name = db.Column(db.String(80), nullable=False, index=True)
    event_source = db.Column(db.String(16), nullable=False, index=True)
    trigger_origin = db.Column(db.String(64), nullable=False, default='unknown', index=True)
    button_id = db.Column(db.String(80), nullable=True, index=True)
    success = db.Column(db.Boolean, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


class ErrorRecord(db.Model):
    """A deduplicated application error visible in the admin error center."""

    __tablename__ = 'error_records'

    id = db.Column(db.Integer, primary_key=True)
    fingerprint = db.Column(db.String(64), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='open', index=True)
    severity = db.Column(db.String(20), nullable=False, default='error', index=True)
    source = db.Column(db.String(255), nullable=True)
    exception_type = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    traceback = db.Column(db.Text, nullable=True)
    request_method = db.Column(db.String(16), nullable=True)
    request_path = db.Column(db.Text, nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)
    query_params = db.Column(db.Text, nullable=True)
    request_payload = db.Column(db.Text, nullable=True)
    request_headers = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    user_email = db.Column(db.String(255), nullable=True)
    client_ip = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    environment = db.Column(db.String(64), nullable=True)
    release = db.Column(db.String(128), nullable=True)
    occurrence_count = db.Column(db.Integer, nullable=False, default=1)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])
