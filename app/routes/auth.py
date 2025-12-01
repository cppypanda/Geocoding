import re
import time
import random
import os
import json # For image_paths in feedback, though feedback routes go to user.py

from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, current_user

from .. import config # 导入顶层配置
from ..services import user_service, email_service # 导入用户和邮件服务
from ..models import User # Import User model

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

# This cache is for temporary verification codes and does not need to be in the database.
verification_codes_cache = {}
# 兼容旧代码/测试中使用的名称（例如 sms_codes_cache）
sms_codes_cache = verification_codes_cache

@auth_bp.route('/send_verification_code', methods=['POST'])
def send_verification_code():
    data = request.json
    if not data:
        current_app.logger.warning("Received empty JSON for send_verification_code")
        return jsonify({'success': False, 'message': '无效的请求'}), 400
        
    email = data.get('email')
    purpose = data.get('purpose', 'register_login') # 'register_login', 'reset_password', 'register_or_set_password'
    current_app.logger.info(f"send_verification_code request received for email: {email}, purpose: {purpose}")

    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({'success': False, 'message': '无效的邮箱地址'}), 400

    # 频率限制 (例如60秒内不能重复发送)
    cache_key = f"{email}_{purpose}"
    last_sent_time = verification_codes_cache.get(cache_key, (None, 0))[1]
    if time.time() - last_sent_time < 60:
        return jsonify({'success': False, 'message': '请求过于频繁，请稍后再试'}), 429

    user = user_service.get_user_by_email(email)

    if purpose == 'reset_password' and not user:
        return jsonify({'success': False, 'message': '该邮箱未注册'}), 404
    
    if purpose == 'register_or_set_password':
        if user and user.password_hash != current_app.config['NO_PASSWORD_PLACEHOLDER']:
            return jsonify({'success': False, 'message': '该账号已注册，请直接登录或找回密码'}), 409

    code = str(random.randint(100000, 999999))
    
    # [调试] 在后端日志中打印验证码
    current_app.logger.info(f"为 {email} (用途: {purpose}) 生成的验证码是: {code}")
    
    # 发送邮件
    try:
        purpose_map = {
            'register_login': '注册或登录',
            'reset_password': '重置密码',
            'register_or_set_password': '注册或设置密码'
        }
        purpose_text = purpose_map.get(purpose, purpose)

        subject = f"您的验证码是: {code}"
        body = f"您正在进行{purpose_text}操作，验证码为：<h1>{code}</h1>此验证码5分钟内有效。"
        email_service.send_email(email, subject, body)
    except Exception as e:
        current_app.logger.error(f"发送验证码邮件失败: {e}")
        return jsonify({'success': False, 'message': '邮件发送失败，请稍后再试'}), 500

    verification_codes_cache[cache_key] = (code, time.time(), purpose)
    # 同步一份到用户会话，增强容错（例如进程重启/多实例）
    try:
        per_session_codes = session.get('verification_codes') or {}
        per_session_codes[cache_key] = (code, time.time(), purpose)
        session['verification_codes'] = per_session_codes
    except Exception:
        pass
    
    return jsonify({'success': True, 'message': '验证码已发送至您的邮箱'})

@auth_bp.route('/login_register_email', methods=['POST'])
def login_register_email():
    data = request.json
    email = data.get('email')
    code = data.get('code')

    if not email or not code:
        return jsonify({'success': False, 'message': '邮箱和验证码不能为空'}), 400

    cache_key = f"{email}_register_login"
    # 优先从用户会话中获取
    per_session_codes = session.get('verification_codes') or {}
    cached_data = per_session_codes.get(cache_key) or verification_codes_cache.get(cache_key)
    if not cached_data:
        return jsonify({'success': False, 'message': '请先获取验证码'}), 400

    correct_code, timestamp, _ = cached_data
    if time.time() - timestamp > 300 or code != correct_code:
        if time.time() - timestamp > 300:
            message = '验证码已过期'
            try:
                if cache_key in verification_codes_cache:
                    del verification_codes_cache[cache_key]
            except Exception:
                pass
            try:
                if cache_key in per_session_codes:
                    del per_session_codes[cache_key]
                    session['verification_codes'] = per_session_codes
            except Exception:
                pass
        else:
            message = '验证码错误'
        return jsonify({'success': False, 'message': message}), 400

    try:
        if cache_key in verification_codes_cache:
            del verification_codes_cache[cache_key]
    except Exception:
        pass
    try:
        if cache_key in per_session_codes:
            del per_session_codes[cache_key]
            session['verification_codes'] = per_session_codes
    except Exception:
        pass

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
    
    user_info = {
        'id': user.id,
        'email': user.email,
        'username': user.username or user.email.split('@')[0],
        'points': user.points,
        'is_admin': user.is_admin,
        'avatar_url': user.avatar_url
    }
    
    message = '注册并登录成功' if new_user_created else '登录成功'
    return jsonify({'success': True, 'message': message, 'user': user_info})

@auth_bp.route('/logout', methods=['GET'])
def logout():
    logout_user()
    session.clear() # 清除所有 session 数据，防止 cookie 过大
    return jsonify({'success': True, 'message': '已退出登录'})

@auth_bp.route('/check_login_status', methods=['GET'])
def check_login_status():
    if current_user.is_authenticated:
        user_info = {
            'id': current_user.id,
            'email': current_user.email,
            'username': current_user.username or current_user.email.split('@')[0],
            'points': current_user.points,
            'is_admin': current_user.is_admin,
            'avatar_url': current_user.avatar_url
        }
        return jsonify({'logged_in': True, 'user': user_info})
    else:
        return jsonify({'logged_in': False})

@auth_bp.route('/register_set_password', methods=['POST'])
def register_set_password():
    data = request.json
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    password = data.get('password', '').strip()
    username = data.get('username', '').strip()

    if not email or not code or not password:
        return jsonify({'success': False, 'message': '邮箱、验证码和密码不能为空'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少为6位'}), 400

    # 兼容用户在“邮箱登录”入口获取验证码后切到“注册/设置密码”入口提交的情况
    primary_key = f"{email}_register_or_set_password"
    fallback_key = f"{email}_register_login"

    now_ts = time.time()
    per_session_codes = session.get('verification_codes') or {}
    primary_data = per_session_codes.get(primary_key) or verification_codes_cache.get(primary_key)
    fallback_data = per_session_codes.get(fallback_key) or verification_codes_cache.get(fallback_key)

    if not primary_data and not fallback_data:
        return jsonify({'success': False, 'message': '请先获取验证码'}), 400

    # 构造候选集合，并判断是否匹配输入验证码
    candidates = []
    if primary_data:
        candidates.append((primary_key, primary_data))
    if fallback_data:
        candidates.append((fallback_key, fallback_data))

    # 先检测是否有过期项（用于必要时清理）
    any_not_expired = False
    matched_key = None
    for k, v in candidates:
        correct_code, ts, _p = v
        is_expired = (now_ts - ts) > 300
        if not is_expired:
            any_not_expired = True
            if code == correct_code:
                matched_key = k
                break

    if matched_key is None:
        # 若没有未过期匹配项：区分“全部过期”与“存在但不匹配”
        if not any_not_expired:
            # 清理已过期的验证码
            try:
                if primary_data and primary_key in verification_codes_cache:
                    del verification_codes_cache[primary_key]
            except Exception:
                pass
            try:
                if fallback_data and fallback_key in verification_codes_cache:
                    del verification_codes_cache[fallback_key]
            except Exception:
                pass
            try:
                if primary_data and primary_key in per_session_codes:
                    del per_session_codes[primary_key]
                    session['verification_codes'] = per_session_codes
            except Exception:
                pass
            try:
                if fallback_data and fallback_key in per_session_codes:
                    del per_session_codes[fallback_key]
                    session['verification_codes'] = per_session_codes
            except Exception:
                pass
            return jsonify({'success': False, 'message': '验证码已过期'}), 400
        else:
            return jsonify({'success': False, 'message': '验证码错误'}), 400

    # 使用并清理已匹配的验证码
    try:
        if matched_key in verification_codes_cache:
            del verification_codes_cache[matched_key]
    except Exception:
        pass
    try:
        if matched_key in per_session_codes:
            del per_session_codes[matched_key]
            session['verification_codes'] = per_session_codes
    except Exception:
        pass

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
    
    user_info = {
        'id': final_user.id,
        'email': final_user.email,
        'username': final_user.username or final_user.email.split('@')[0],
        'points': final_user.points,
        'is_admin': final_user.is_admin,
        'avatar_url': final_user.avatar_url
    }
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

        user_info = {
            'id': user.id,
            'email': user.email,
            'username': user.username or user.email.split('@')[0],
            'points': user.points,
            'is_admin': user.is_admin,
            'avatar_url': user.avatar_url
        }
        return jsonify({'success': True, 'message': '登录成功', 'user': user_info})
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
            user_info = {
                'id': updated_user.id,
                'email': updated_user.email,
                'username': updated_user.username or updated_user.email,
                'points': updated_user.points or 0
            }
            return jsonify({'success': True, 'message': '用户名更新成功', 'user': user_info}), 200
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
            user_info = {
                'id': updated_user.id,
                'email': updated_user.email,
                'username': updated_user.username or updated_user.email,
                'points': updated_user.points or 0,
                'avatar_url': updated_user.avatar_url
            }
            return jsonify({'success': True, 'message': 'API Key 更新成功', 'user': user_info}), 200
        else:
            return jsonify({'success': False, 'message': '更新失败，用户不存在'}), 404
    except Exception as e:
        current_app.logger.error(f"Error in update_api_keys: {e}")
        return jsonify({'success': False, 'message': f'服务器内部错误'}), 500

@auth_bp.route('/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    email = data.get('email', '').strip()
    code = data.get('code', '').strip()
    new_password = data.get('new_password', '').strip()

    if not email or not code or not new_password:
        return jsonify({'success': False, 'message': '必要信息不完整'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '密码长度至少为6位'}), 400

    cache_key = f"{email}_reset_password"
    per_session_codes = session.get('verification_codes') or {}
    cached_data = per_session_codes.get(cache_key) or verification_codes_cache.get(cache_key)
    if not cached_data:
        return jsonify({'success': False, 'message': '请先获取验证码'}), 400

    correct_code, timestamp, _ = cached_data
    if time.time() - timestamp > 300 or code != correct_code:
        message = '验证码已过期' if time.time() - timestamp > 300 else '验证码错误'
        if time.time() - timestamp > 300:
            try:
                if cache_key in verification_codes_cache:
                    del verification_codes_cache[cache_key]
            except Exception:
                pass
            try:
                if cache_key in per_session_codes:
                    del per_session_codes[cache_key]
                    session['verification_codes'] = per_session_codes
            except Exception:
                pass
        return jsonify({'success': False, 'message': message}), 400

    try:
        if cache_key in verification_codes_cache:
            del verification_codes_cache[cache_key]
    except Exception:
        pass
    try:
        if cache_key in per_session_codes:
            del per_session_codes[cache_key]
            session['verification_codes'] = per_session_codes
    except Exception:
        pass

    if user_service.set_password_for_user(email, new_password):
        return jsonify({'success': True, 'message': '密码重置成功，请使用新密码登录'})
    else:
        return jsonify({'success': False, 'message': '密码重置失败，用户不存在或发生错误'}), 500

@auth_bp.route('/get_user_info')
def get_user_info():
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '用户未登录'}), 401
    
    user = current_user
    user_info = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'points': user.points,
        'avatar_url': user.avatar_url
        # Add other fields as needed
    }
    return jsonify({'success': True, 'user': user_info})

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
        user_info = {
            'id': updated_user.id,
            'email': updated_user.email,
            'username': updated_user.username,
            'points': updated_user.points,
            'is_admin': updated_user.is_admin,
            'avatar_url': updated_user.avatar_url
        }
        return jsonify({'success': True, 'message': '用户信息更新成功', 'user': user_info})
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
        return jsonify({'success': False, 'message': f'更新失败: {e}'}), 500