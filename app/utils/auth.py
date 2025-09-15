from functools import wraps
from flask import session, jsonify

def login_required(f):
    """
    一个要求用户登录的装饰器。
    如果用户未登录，返回401错误。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function 