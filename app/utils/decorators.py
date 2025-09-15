import asyncio
from functools import wraps
from asgiref.sync import async_to_sync

def async_route(f):
    """
    一个装饰器，用于将异步的Flask路由函数包装起来，
    以便在同步的Flask应用中运行。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return decorated_function

def wrap_async(f):
    """装饰器：将异步函数包装为同步函数"""
    def sync_f(*args, **kwargs):
        return async_to_sync(f)(*args, **kwargs)
    sync_f.__name__ = f.__name__
    return sync_f 