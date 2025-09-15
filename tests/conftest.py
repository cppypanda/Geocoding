import pytest
import tempfile
import os
import threading
import time
from werkzeug.serving import make_server
from collections import namedtuple
from app import create_app
from app.database.db_setup import init_user_db, init_user_api_keys_db
from app.services import user_service

Server = namedtuple('Server', ['app', 'url'])

class ServerThread(threading.Thread):
    def __init__(self, app, host='127.0.0.1', port=5000):
        super().__init__()
        self.srv = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        self.srv.serve_forever()

    def shutdown(self):
        self.srv.shutdown()

@pytest.fixture(scope='session')
def app():
    """
    创建一个作用域为 'session' 的应用实例。
    """
    db_fd, db_path = tempfile.mkstemp()

    app = create_app('development', config_overrides={
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'SERVER_NAME': '127.0.0.1:5000',
        'USER_DB_NAME': db_path,
        'GEOCODING_DB_NAME': db_path, 
        'USER_API_KEYS_DB_NAME': db_path,
    })
    
    with app.app_context():
        init_user_db(db_path)
        init_user_api_keys_db(db_path)

    yield app

    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture(scope='session')
def live_server(app):
    """
    一个自定义的 live server，返回一个包含 app 和 url 的对象。
    """
    host = '127.0.0.1'
    port = 5000
    server_thread = ServerThread(app, host, port)
    server_thread.start()
    time.sleep(1)
    
    server = Server(app=app, url=f"http://{host}:{port}")
    
    yield server
    
    server_thread.shutdown()

@pytest.fixture
def client(app):
    """为应用创建一个测试客户端"""
    return app.test_client()

@pytest.fixture
def runner(app):
    """为应用创建一个命令行运行器"""
    return app.test_cli_runner()

@pytest.fixture(scope='session')
def test_user(app):
    """
    在会话开始时，在数据库中创建一个用于所有测试的共享用户。
    """
    with app.app_context():
        existing_user = user_service.get_user_by_username('testuser')
        if not existing_user:
            user_service.create_user_with_password(
                username='testuser',
                password='testpassword',
                phone='19999999999'
            )
        
        user = user_service.get_user_by_username('testuser')
        assert user is not None
        
        return {
            'username': 'testuser',
            'password': 'testpassword',
            'phone_number': '19999999999'
        } 