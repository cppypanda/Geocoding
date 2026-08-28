from dataclasses import dataclass

import requests
from flask import current_app


@dataclass(frozen=True)
class UrpaIdentity:
    external_id: str
    phone: str
    display_name: str
    plan: str = 'free'


class UrpaAuthError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def normalize_phone(value: str) -> str:
    raw = (value or '').strip()
    if raw.startswith('+'):
        return '+' + ''.join(char for char in raw[1:] if char.isdigit())
    return ''.join(char for char in raw if char.isdigit())


def _validate_phone(value: str) -> str:
    phone = normalize_phone(value)
    digit_count = len(phone[1:] if phone.startswith('+') else phone)
    if digit_count < 7 or digit_count > 20:
        raise UrpaAuthError('请输入有效的手机号', 400)
    return phone


def _request(path: str, body: dict) -> dict:
    base_url = current_app.config['URPA_BASE_URL'].rstrip('/')
    timeout = current_app.config.get('URPA_AUTH_TIMEOUT_SECONDS', 12)
    try:
        response = requests.post(
            f'{base_url}{path}',
            json=body,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-URPA-Product': 'geoco',
            },
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise UrpaAuthError('URPA 账号服务响应超时，请稍后重试', 503) from exc
    except requests.RequestException as exc:
        raise UrpaAuthError('暂时无法连接 URPA 账号服务，请稍后重试或使用原邮箱登录', 503) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise UrpaAuthError('URPA 账号服务返回了无效响应', 502) from exc
    if not isinstance(payload, dict):
        raise UrpaAuthError('URPA 账号服务返回了无效响应', 502)
    if not response.ok:
        message = payload.get('message') or payload.get('error') or 'URPA 账号操作失败'
        raise UrpaAuthError(str(message), response.status_code)
    return payload


def _identity(payload: dict) -> UrpaIdentity:
    user = payload.get('user') or {}
    external_id = str(user.get('id') or '').strip()
    phone = normalize_phone(str(user.get('phone') or ''))
    if not external_id or not phone:
        raise UrpaAuthError('URPA 账号信息不完整', 502)
    if user.get('status') not in (None, 'active'):
        raise UrpaAuthError('该 URPA 账号已停用', 403)
    plan = str(user.get('plan') or 'free').lower()
    if plan not in {'free', 'go', 'plus', 'pro'}:
        plan = 'free'
    return UrpaIdentity(
        external_id=external_id,
        phone=phone,
        display_name=str(user.get('name') or '').strip() or phone,
        plan=plan,
    )


def account_status(phone_input: str) -> dict:
    phone = _validate_phone(phone_input)
    payload = _request('/api/auth/status', {'phone': phone})
    return {
        'exists': bool(payload.get('exists')),
        'has_password': bool(payload.get('hasPassword')),
        'phone': normalize_phone(str(payload.get('phone') or phone)),
    }


def send_code(phone_input: str, purpose: str = 'register') -> dict:
    phone = _validate_phone(phone_input)
    normalized_purpose = 'reset' if purpose == 'reset' else 'register'
    payload = _request('/api/auth/send-code', {
        'phone': phone,
        'purpose': normalized_purpose,
    })
    result = {'phone': normalize_phone(str(payload.get('phone') or phone))}
    if current_app.testing and payload.get('devCode'):
        result['dev_code'] = str(payload['devCode'])
    return result


def password_login(phone_input: str, password: str) -> UrpaIdentity:
    phone = _validate_phone(phone_input)
    if not password:
        raise UrpaAuthError('请输入 URPA 密码', 400)
    try:
        return _identity(_request('/api/auth/password-login', {
            'phone': phone,
            'password': password,
            'clientProduct': 'geoco',
        }))
    except UrpaAuthError as exc:
        if exc.status_code == 401:
            raise UrpaAuthError('URPA 手机号或密码错误', 401) from exc
        raise


def register(phone_input: str, code: str, password: str) -> UrpaIdentity:
    phone = _validate_phone(phone_input)
    if not (code or '').strip():
        raise UrpaAuthError('请输入短信验证码', 400)
    if not 6 <= len(password or '') <= 128:
        raise UrpaAuthError('密码长度必须为 6-128 位', 400)
    return _identity(_request('/api/auth/register', {
        'phone': phone,
        'code': code.strip(),
        'password': password,
        'clientProduct': 'geoco',
    }))


def reset_password(phone_input: str, code: str, password: str) -> UrpaIdentity:
    phone = _validate_phone(phone_input)
    if not (code or '').strip():
        raise UrpaAuthError('请输入短信验证码', 400)
    if not 6 <= len(password or '') <= 128:
        raise UrpaAuthError('密码长度必须为 6-128 位', 400)
    return _identity(_request('/api/auth/reset-password', {
        'phone': phone,
        'code': code.strip(),
        'password': password,
        'clientProduct': 'geoco',
    }))
