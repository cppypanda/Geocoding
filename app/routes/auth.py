import re
import hashlib
import hmac
import secrets
import json # For image_paths in feedback, though feedback routes go to user.py
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, current_user
from sqlalchemy import or_

from .. import config # 导入顶层配置
from ..services import user_service, email_service, urpa_auth # 导入用户和邮件服务
from .. import db
from ..models import BonusRewardLog, EmailVerificationCode, User

auth_bp = Blueprint('auth', __name__) # 移除 url_prefix

def _check_and_sync_admin_status(user):
    """
    根据配置文件检查用户是否应为管理员，并在必要时更新数据库。
    """
    if not user or not user.email:
        return

    admin_emails = current_app.config.get('ADMIN_EMAILS', [])
    should_be_admin = user.email in admin_emails

    if user.is_admin != should_be_admin:
        # 这里我们直接修改user对象，让后续的用户信息返回更新后的状态
        user.is_admin = should_be_admin
        # 调用服务层函数来更新数据库
        user_service.update_admin_status(user, should_be_admin)
        current_app.logger.info(f"Admin status for {user.email} synchronized to {should_be_admin}.")

_VERIFICATION_PURPOSES = {'register_login', 'reset_password', 'register_or_set_password'}
_VERIFICATION_TTL = timedelta(minutes=5)
_VERIFICATION_RESEND_INTERVAL = timedelta(seconds=60)
_VERIFICATION_MAX_ATTEMPTS = 5


def _normalize_email(email):
    return (email or '').strip().lower()


def _public_email(user):
    return None if user.account_origin == 'urpa' else user.email


def _mask_phone(phone):
    value = phone or ''
    if len(value) >= 7:
        return f'{value[:3]}****{value[-4:]}'
    return value


def _user_info(user):
    email = _public_email(user)
    fallback_name = _mask_phone(user.phone) or ((email or '').split('@')[0]) or 'GeoCo用户'
    return {
        'id': user.id,
        'email': email,
        'username': user.username or fallback_name,
        'points': user.points or 0,
        'is_admin': bool(user.is_admin),
        'avatar_url': user.avatar_url,
        'phone': user.phone,
        'phone_masked': _mask_phone(user.phone),
        'urpa_linked': bool(user.urpa_user_id),
        'needs_phone_binding': not bool(user.urpa_user_id),
        'account_origin': user.account_origin or 'email',
    }


def _synthetic_urpa_email(external_id):
    digest = hashlib.sha256(external_id.encode('utf-8')).hexdigest()[:24]
    return f'urpa-{digest}@accounts.invalid'


def _resolve_urpa_user(identity):
    user = User.query.filter(
        or_(User.urpa_user_id == identity.external_id, User.phone == identity.phone)
    ).first()
    if user:
        if user.is_deleted:
            raise urpa_auth.UrpaAuthError('该 GeoCo 账户已注销', 403)
        if user.urpa_user_id and user.urpa_user_id != identity.external_id:
            raise urpa_auth.UrpaAuthError('该手机号的账户映射存在冲突，请联系管理员', 409)
        user.urpa_user_id = identity.external_id
        user.phone = identity.phone
        user.urpa_linked_at = user.urpa_linked_at or datetime.utcnow()
        db.session.commit()
        return user

    synthetic_email = _synthetic_urpa_email(identity.external_id)
    reward_log = BonusRewardLog.query.filter_by(email=synthetic_email).first()
    points = 0 if reward_log else current_app.config.get('NEW_USER_REWARD_POINTS', 100)
    user = User(
        email=synthetic_email,
        password_hash=current_app.config['NO_PASSWORD_PLACEHOLDER'],
        username=None,
        phone=identity.phone,
        urpa_user_id=identity.external_id,
        urpa_linked_at=datetime.utcnow(),
        account_origin='urpa',
        points=points,
        created_at=datetime.utcnow(),
        registration_date=datetime.utcnow(),
    )
    db.session.add(user)
    if points > 0 and not reward_log:
        db.session.add(BonusRewardLog(email=synthetic_email))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        existing = User.query.filter(
            or_(User.urpa_user_id == identity.external_id, User.phone == identity.phone)
        ).first()
        if existing and not existing.is_deleted:
            return existing
        raise
    user_service.create_notification(
        user.id,
        '欢迎使用 URPA 手机号登录陆梧GeoCo。您的任务、积分和后续陆梧工具将通过同一身份关联。',
    )
    return user


def _link_urpa_identity(user, identity):
    if user.urpa_user_id and user.urpa_user_id != identity.external_id:
        raise urpa_auth.UrpaAuthError(
            '当前 GeoCo 账户已经绑定其他 URPA 身份。如需更换，请联系管理员核验。',
            409,
        )
    conflict = User.query.filter(
        User.id != user.id,
        or_(User.urpa_user_id == identity.external_id, User.phone == identity.phone),
    ).first()
    if conflict:
        raise urpa_auth.UrpaAuthError(
            '该 URPA 手机号已关联另一个 GeoCo 账户。为保护积分和任务，暂不自动合并，请联系管理员处理。',
            409,
        )
    user.phone = identity.phone
    user.urpa_user_id = identity.external_id
    user.urpa_linked_at = datetime.utcnow()
    db.session.commit()
    return user


def _urpa_identity_from_request(data):
    if data.get('register') is True:
        return urpa_auth.register(
            data.get('phone', ''), data.get('code', ''), data.get('password', '')
        )
    return urpa_auth.password_login(data.get('phone', ''), data.get('password', ''))


def _urpa_error_response(error):
    if isinstance(error, urpa_auth.UrpaAuthError):
        return jsonify({'success': False, 'message': str(error)}), error.status_code
    current_app.logger.exception('URPA 账户操作失败')
    return jsonify({'success': False, 'message': '账户操作失败，请稍后重试'}), 500


def _verification_digest(email, purpose, code):
    payload = f'{email}|{purpose}|{code}'.encode('utf-8')
    secret = current_app.config['SECRET_KEY'].encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _consume_verification_code(email, code, purposes):
    email = _normalize_email(email)
    now = datetime.utcnow()
    records = (
        EmailVerificationCode.query
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose.in_(purposes),
        )
        .with_for_update()
        .all()
    )
    if not records:
        return False, '请先获取验证码', 400

    active = [record for record in records if record.expires_at > now]
    if not active:
        for record in records:
            db.session.delete(record)
        db.session.commit()
        return False, '验证码已过期', 400

    if all(record.attempt_count >= _VERIFICATION_MAX_ATTEMPTS for record in active):
        return False, '验证码尝试次数过多，请重新获取', 429

    for record in active:
        if record.attempt_count >= _VERIFICATION_MAX_ATTEMPTS:
            continue
        expected = _verification_digest(email, record.purpose, code)
        if hmac.compare_digest(record.code_digest, expected):
            for item in records:
                db.session.delete(item)
            db.session.commit()
            return True, None, 200

    for record in active:
        record.attempt_count += 1
    db.session.commit()
    remaining = max(0, _VERIFICATION_MAX_ATTEMPTS - max(r.attempt_count for r in active))
    return False, f'验证码错误，还可尝试 {remaining} 次', 400

@auth_bp.route('/send_verification_code', methods=['POST'])
def send_verification_code():
    data = request.json
    if not data:
        current_app.logger.warning("Received empty JSON for send_verification_code")
        return jsonify({'success': False, 'message': '无效的请求'}), 400
        
    email = _normalize_email(data.get('email'))
    purpose = data.get('purpose', 'register_login') # 'register_login', 'reset_password', 'register_or_set_password'
    if purpose not in _VERIFICATION_PURPOSES:
        return jsonify({'success': False, 'message': '无效的验证码用途'}), 400

    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({'success': False, 'message': '无效的邮箱地址'}), 400

    user = user_service.get_user_by_email(email)

    if purpose == 'reset_password' and not user:
        # Do not reveal whether an account exists.
        return jsonify({'success': True, 'message': '如果该邮箱已注册，验证码将发送至邮箱'}), 200
    
    if purpose == 'register_or_set_password':
        if user and user.password_hash != current_app.config['NO_PASSWORD_PLACEHOLDER']:
            return jsonify({'success': False, 'message': '该账号已注册，请直接登录或找回密码'}), 409

    now = datetime.utcnow()
    record = (
        EmailVerificationCode.query
        .filter_by(email=email, purpose=purpose)
        .with_for_update()
        .first()
    )
    if record and now - record.last_sent_at < _VERIFICATION_RESEND_INTERVAL:
        return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429

    code = f'{secrets.randbelow(900000) + 100000:06d}'
    try:
        purpose_map = {
            'register_login': '注册或登录',
            'reset_password': '重置密码',
            'register_or_set_password': '注册或设置密码'
        }
        purpose_text = purpose_map.get(purpose, purpose)

        if record is None:
            record = EmailVerificationCode(email=email, purpose=purpose)
            db.session.add(record)
        record.code_digest = _verification_digest(email, purpose, code)
        record.attempt_count = 0
        record.expires_at = now + _VERIFICATION_TTL
        record.last_sent_at = now
        # Reserve the unique email/purpose row before sending so concurrent requests
        # cannot both send different codes while only one is persisted.
        db.session.flush()

        subject = f"您的验证码是: {code}"
        body = f"您正在进行{purpose_text}操作，验证码为：<h1>{code}</h1>此验证码5分钟内有效。"
        email_service.send_email(email, subject, body)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"发送验证码邮件失败: {e}")
        return jsonify({'success': False, 'message': '邮件发送失败，请稍后再试'}), 500
    
    return jsonify({'success': True, 'message': '验证码已发送至您的邮箱'})

@auth_bp.route('/login_register_email', methods=['POST'])
def login_register_email():
    data = request.json
    email = _normalize_email(data.get('email'))
    code = data.get('code')

    if not email or not code:
        return jsonify({'success': False, 'message': '邮箱和验证码不能为空'}), 400

    verified, message, status = _consume_verification_code(email, code, ('register_login',))
    if not verified:
        return jsonify({'success': False, 'message': message}), status

    user = user_service.get_user_by_email(email)
    new_user_created = False
    
    if not user:
        user = user_service.create_user_for_email_login(email)
        if not user:
            return jsonify({'success': False, 'message': '创建新用户失败'}), 500
        new_user_created = True

        # 为新用户发送欢迎通知
        if new_user_created:
            welcome_message = "欢迎您加入陆梧GeoCo！我们致力于为您提供智能、精准的地理编码服务。为了帮助您快速上手，这里有一个核心技巧：本工具支持批量地址处理，您只需将地址“每行一个”粘贴到输入框，即可轻松处理大量数据。更多高级功能，请随时查阅右上角用户菜单里的“使用教程”。祝您使用愉快！"
            user_service.create_notification(user.id, welcome_message)

    login_user(user, remember=True)
    user_service.update_user_last_login(user.id)
    _check_and_sync_admin_status(user)
    
    user_info = _user_info(user)
    
    message = '注册并登录成功' if new_user_created else '登录成功'
    return jsonify({'success': True, 'message': message, 'user': user_info})


@auth_bp.route('/urpa_account_status', methods=['POST'])
def urpa_account_status():
    data = request.get_json(silent=True) or {}
    try:
        status = urpa_auth.account_status(data.get('phone', ''))
        return jsonify({'success': True, **status})
    except Exception as error:
        return _urpa_error_response(error)


@auth_bp.route('/urpa_send_code', methods=['POST'])
def urpa_send_code():
    data = request.get_json(silent=True) or {}
    try:
        result = urpa_auth.send_code(data.get('phone', ''), data.get('purpose', 'register'))
        return jsonify({'success': True, 'message': '短信验证码已发送', **result})
    except Exception as error:
        return _urpa_error_response(error)


@auth_bp.route('/urpa_login', methods=['POST'])
def urpa_login():
    data = request.get_json(silent=True) or {}
    try:
        identity = _urpa_identity_from_request(data)
        user = _resolve_urpa_user(identity)
        login_user(user, remember=True)
        user_service.update_user_last_login(user.id)
        _check_and_sync_admin_status(user)
        message = 'URPA 账号注册并登录成功' if data.get('register') is True else 'URPA 登录成功'
        return jsonify({'success': True, 'message': message, 'user': _user_info(user)})
    except Exception as error:
        db.session.rollback()
        return _urpa_error_response(error)


@auth_bp.route('/urpa_link', methods=['POST'])
def urpa_link():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '请先登录原有 GeoCo 账户'}), 401
    data = request.get_json(silent=True) or {}
    try:
        identity = _urpa_identity_from_request(data)
        user = _link_urpa_identity(current_user, identity)
        return jsonify({
            'success': True,
            'message': 'URPA 手机号已绑定，原有积分和任务保持不变',
            'user': _user_info(user),
        })
    except Exception as error:
        db.session.rollback()
        return _urpa_error_response(error)


@auth_bp.route('/urpa_reset_password', methods=['POST'])
def urpa_reset_password():
    data = request.get_json(silent=True) or {}
    try:
        identity = urpa_auth.reset_password(
            data.get('phone', ''), data.get('code', ''), data.get('password', '')
        )
        user = _resolve_urpa_user(identity)
        login_user(user, remember=True)
        user_service.update_user_last_login(user.id)
        return jsonify({
            'success': True,
            'message': 'URPA 密码已重置并登录',
            'user': _user_info(user),
        })
    except Exception as error:
        db.session.rollback()
        return _urpa_error_response(error)

@auth_bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return jsonify({'success': True, 'message': '已退出登录'})

@auth_bp.route('/check_login_status', methods=['GET'])
def check_login_status():
    if current_user.is_authenticated:
        return jsonify({'logged_in': True, 'user': _user_info(current_user)})
    else:
        return jsonify({'logged_in': False})

@auth_bp.route('/register_set_password', methods=['POST'])
def register_set_password():
    data = request.json
    email = _normalize_email(data.get('email'))
    code = data.get('code', '').strip()
    password = data.get('password', '').strip()
    username = data.get('username', '').strip()

    if not email or not code or not password:
        return jsonify({'success': False, 'message': '邮箱、验证码和密码不能为空'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少为6位'}), 400

    verified, message, status = _consume_verification_code(
        email,
        code,
        ('register_or_set_password', 'register_login'),
    )
    if not verified:
        return jsonify({'success': False, 'message': message}), status

    user = user_service.get_user_by_email(email)

    if user:
        # 兼容历史占位符（如 'not_set'）
        from ..services.user_service import is_no_password_placeholder
        if is_no_password_placeholder(user.password_hash):
            if user_service.set_password_for_user(email, password):
                user_service.update_user_last_login(user.id)
                # ... (login user and return success)
            else:
                return jsonify({'success': False, 'message': '密码设置失败'}), 500
        else:
            return jsonify({'success': False, 'message': '该邮箱已注册并设置密码，您可以通过"忘记密码"找回'}), 409
    else:
        if username and user_service.get_user_by_username(username):
            return jsonify({'success': False, 'message': '该用户名已被占用'}), 409

        new_user = user_service.create_user_with_password(username, password, email)
        if new_user:
            # ... (login user and return success)
            pass
        else:
            return jsonify({'success': False, 'message': '注册失败'}), 500
    
    # Unified login logic after setting/creating password
    final_user = user_service.get_user_by_email(email)
    login_user(final_user, remember=True)
    
    user_info = _user_info(final_user)
    return jsonify({'success': True, 'message': '操作成功并已登录', 'user': user_info})

@auth_bp.route('/login_account', methods=['POST'])
def login_account():
    data = request.json
    username_or_email = data.get('username_or_email')
    password = data.get('password')

    if not username_or_email or not password:
        return jsonify({'success': False, 'message': '邮箱/用户名和密码不能为空'}), 400
    
    if not user_service.verify_password(username_or_email, password):
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    user = user_service.get_user_by_username(username_or_email) or user_service.get_user_by_email(username_or_email)
    
    if user:
        login_user(user, remember=True)
        user_service.update_user_last_login(user.id)
        _check_and_sync_admin_status(user)

        return jsonify({'success': True, 'message': '登录成功', 'user': _user_info(user)})
    else: # Should not happen if verify_password passed
        return jsonify({'success': False, 'message': '登录失败，用户不存在'}), 404

@auth_bp.route('/update_username', methods=['POST'])
def update_username():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    data = request.json
    new_username = data.get('username')

    if not new_username or not isinstance(new_username, str) or not (1 <= len(new_username) <= 20):
        return jsonify({'success': False, 'message': '用户名长度应为1-20个字符'}), 400

    user_id = current_user.id
    
    # Check if username is taken by another user
    existing_user = user_service.get_user_by_username(new_username)
    if existing_user and existing_user.id != user_id:
        return jsonify({'success': False, 'message': '该用户名已被占用'}), 400

    if user_service.update_username(user_id, new_username):
        updated_user = user_service.get_user_by_id(user_id)
        if updated_user:
            return jsonify({'success': True, 'message': '用户名更新成功', 'user': _user_info(updated_user)}), 200
        else:
            return jsonify({'success': False, 'message': '更新失败，用户不存在'}), 404
    else:
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500


@auth_bp.route('/update_api_keys', methods=['POST'])
def update_api_keys():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '未登录'}), 401
    
    user_id = current_user.id
    data = request.json

    # Instead of updating the users table directly, this logic should be in user_service
    # and potentially interact with the UserApiKey model.
    # For now, we adapt the existing logic.
    keys_to_update = {
        'amap': data.get('amap_key'),
        'baidu': data.get('baidu_key'),
        'tianditu': data.get('tianditu_key'),
        'zhipuai': data.get('ai_key')
    }

    try:
        for service, key_value in keys_to_update.items():
            if key_value is not None: # Allow clearing keys by sending empty string
                 user_service.update_user_api_key_in_users_table(user_id, service, key_value)

        updated_user = user_service.get_user_by_id(user_id)
        if updated_user:
            return jsonify({'success': True, 'message': 'API Key 更新成功', 'user': _user_info(updated_user)}), 200
        else:
            return jsonify({'success': False, 'message': '更新失败，用户不存在'}), 404
    except Exception as e:
        current_app.logger.error(f"Error in update_api_keys: {e}")
        return jsonify({'success': False, 'message': f'服务器内部错误'}), 500

@auth_bp.route('/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    email = _normalize_email(data.get('email'))
    code = data.get('code', '').strip()
    new_password = data.get('new_password', '').strip()

    if not email or not code or not new_password:
        return jsonify({'success': False, 'message': '必要信息不完整'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少为6位'}), 400

    verified, message, status = _consume_verification_code(email, code, ('reset_password',))
    if not verified:
        return jsonify({'success': False, 'message': message}), status

    if user_service.set_password_for_user(email, new_password):
        return jsonify({'success': True, 'message': '密码重置成功，请使用新密码登录'})
    else:
        return jsonify({'success': False, 'message': '密码重置失败，用户不存在或发生错误'}), 500

@auth_bp.route('/get_user_info')
def get_user_info():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '用户未登录'}), 401
    
    return jsonify({'success': True, 'user': _user_info(current_user)})

@auth_bp.route('/update_user_profile', methods=['POST'])
def update_user_profile():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    user_id = current_user.id
    data = request.json
    new_username = data.get('username', '').strip()

    if not new_username:
        return jsonify({'success': False, 'message': '用户名不能为空'}), 400
    
    if len(new_username) > 20:
        return jsonify({'success': False, 'message': '用户名不能超过20个字符'}), 400

    # 检查用户名是否已被其他用户占用
    existing_user = user_service.get_user_by_username(new_username)
    if existing_user and existing_user.id != user_id:
        return jsonify({'success': False, 'message': '该用户名已被占用'}), 409

    if user_service.update_username(user_id, new_username):
        # 更新 session 中的用户名
        # No need to update session manually, it's handled by Flask-Login
        
        # 获取最新的用户信息并返回
        updated_user = user_service.get_user_by_id(user_id)
        return jsonify({'success': True, 'message': '用户信息更新成功', 'user': _user_info(updated_user)})
    else:
        return jsonify({'success': False, 'message': '更新失败或用户名未改变'}), 500 

@auth_bp.route('/change_password', methods=['POST'])
def change_password():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '未登录'}), 401

    data = request.json or {}
    old_password = (data.get('old_password') or '').strip()
    new_password = (data.get('new_password') or '').strip()
    confirm_password = (data.get('confirm_password') or '').strip()

    if not old_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': '所有字段均为必填'}), 400

    if new_password != confirm_password:
        return jsonify({'success': False, 'message': '两次输入的新密码不一致'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码长度至少为6位'}), 400

    # 获取当前用户
    user = current_user
    if not user: # Should not happen if authenticated
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    # 校验旧密码（若用户原本为验证码登录且未设置密码，则拒绝）
    password_hash = user.password_hash
    # 兼容历史占位符（如 'not_set'）
    from ..services.user_service import is_no_password_placeholder
    if is_no_password_placeholder(password_hash):
        return jsonify({'success': False, 'message': '当前账号未设置密码，请在登录窗口使用“注册/设置密码”流程'}), 400

    if not check_password_hash(password_hash, old_password):
        return jsonify({'success': False, 'message': '旧密码不正确'}), 400

    # 更新为新密码
    try:
        new_hash = generate_password_hash(new_password)
        if user_service.set_password_for_user(user.email, new_password):
             return jsonify({'success': True, 'message': '密码已更新，请使用新密码重新登录'})
        else:
            raise Exception("Failed to set password in user_service")
    except Exception as e:
        current_app.logger.error(f"Error in change_password: {e}")
        return jsonify({'success': False, 'message': '更新失败，请稍后重试'}), 500
