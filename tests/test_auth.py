import pytest
from flask import session
from app.services import user_service
import time
from app.routes.auth import sms_codes_cache

def test_login_success(client, test_user):
    """测试：使用正确的凭据成功登录"""
    response = client.post('/login_account', json={
        'username_or_phone': test_user['username'],
        'password': test_user['password']
    })
    json_data = response.get_json()
    assert response.status_code == 200
    assert json_data['success'] is True
    assert json_data['message'] == '登录成功'
    assert 'user' in json_data
    assert json_data['user']['username'] == test_user['username']
    # 检查 session 是否被正确设置
    with client:
        client.get('/') # 任何请求都可以，主要是为了加载上下文
        assert session['user_id'] is not None
        assert session['username'] == test_user['username']


def test_login_wrong_password(client, test_user):
    """测试：使用错误的密码登录失败"""
    response = client.post('/login_account', json={
        'username_or_phone': test_user['username'],
        'password': 'wrongpassword'
    })
    json_data = response.get_json()
    assert response.status_code == 401  # 401 Unauthorized
    assert json_data['success'] is False
    assert json_data['message'] == '用户名或密码错误'
    # 检查 session 是否未被设置
    with client:
        client.get('/')
        assert 'user_id' not in session


def test_login_nonexistent_user(client):
    """测试：使用不存在的用户登录失败"""
    response = client.post('/login_account', json={
        'username_or_phone': 'nonexistentuser',
        'password': 'anypassword'
    })
    json_data = response.get_json()
    assert response.status_code == 401
    assert json_data['success'] is False
    assert json_data['message'] == '用户名或密码错误'

def test_logout(client, test_user):
    """测试：成功退出登录"""
    # 先登录
    client.post('/login_account', json={
        'username_or_phone': test_user['username'],
        'password': test_user['password']
    })

    # 登出
    response = client.get('/logout')
    json_data = response.get_json()

    assert response.status_code == 200
    assert json_data['success'] is True
    
    # 检查 session，确认用户已登出
    with client:
        client.get('/') # 发起一个新请求以检查 session 状态
        assert 'user_id' not in session

def test_register_success(client, monkeypatch, app):
    """测试：使用有效验证码成功注册新用户"""
    phone_number = '19988887777'
    username = 'newuser'
    password = 'newpassword'
    sms_code = '123456'
    purpose = 'register_or_set_password'
    cache_key = f"{phone_number}_{purpose}"

    # 模拟一个有效的短信验证码在缓存中
    monkeypatch.setitem(sms_codes_cache, cache_key, (sms_code, time.time(), purpose))

    response = client.post('/register_set_password', json={
        'phone_number': phone_number,
        'sms_code': sms_code,
        'password': password,
        'username': username
    })
    json_data = response.get_json()

    assert response.status_code == 201
    assert json_data['success'] is True
    assert json_data['message'] == '注册成功'

    # 检查新用户是否已登录
    with client:
        client.get('/')
        assert session['username'] == username
    
    # 检查用户是否已写入数据库
    with app.app_context():
        user = user_service.get_user_by_phone(phone_number)
        assert user is not None
        assert user['username'] == username

def test_register_user_exists(client, test_user, monkeypatch):
    """测试：使用已注册的手机号注册会失败"""
    phone_number = test_user['phone_number'] # 使用已存在的用户手机号
    sms_code = '111111'
    purpose = 'register_or_set_password'
    cache_key = f"{phone_number}_{purpose}"

    monkeypatch.setitem(sms_codes_cache, cache_key, (sms_code, time.time(), purpose))
    
    response = client.post('/register_set_password', json={
        'phone_number': phone_number,
        'sms_code': sms_code,
        'password': 'anypassword',
        'username': 'anotheruser'
    })
    json_data = response.get_json()

    assert response.status_code == 400
    assert json_data['success'] is False
    assert '该手机号已注册' in json_data['message']

def test_reset_password_success(client, test_user, monkeypatch):
    """测试：使用有效验证码成功重置密码"""
    phone_number = test_user['phone_number']
    # 修正：使用一个符合复杂度要求（字母+数字）的新密码
    new_password = 'newpassword123'
    sms_code = '654321'
    purpose = 'reset_password'
    cache_key = f"{phone_number}_{purpose}"

    # 模拟有效的重置密码验证码
    monkeypatch.setitem(sms_codes_cache, cache_key, (sms_code, time.time(), purpose))
    
    response = client.post('/reset_password', json={
        'phone_number': phone_number,
        'sms_code': sms_code,
        'new_password': new_password
    })
    json_data = response.get_json()

    assert response.status_code == 200
    assert json_data['success'] is True
    assert json_data['message'] == '密码重置成功'

    # 登出当前所有会话，确保环境干净
    client.get('/logout')

    # 用新密码尝试登录以验证
    login_response = client.post('/login_account', json={
        'username_or_phone': test_user['username'],
        'password': new_password
    })
    assert login_response.status_code == 200
    assert login_response.get_json()['success'] is True 