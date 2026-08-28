import unittest
from unittest.mock import Mock, patch

from app import create_app
from app.services import urpa_auth


class UrpaAuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'urpa-service-test',
            'ZHIPUAI_KEY': None,
            'URPA_BASE_URL': 'https://urpa.example.test',
            'URPA_AUTH_TIMEOUT_SECONDS': 3,
        })
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        self.context.pop()

    @patch('app.services.urpa_auth.requests.post')
    def test_password_login_uses_the_shared_urpa_protocol(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            'user': {
                'id': 'shared-user-id',
                'phone': '13800138000',
                'name': '共享账户',
                'status': 'active',
                'plan': 'plus',
            }
        }
        post.return_value = response

        identity = urpa_auth.password_login('138 0013 8000', 'secret')

        self.assertEqual(identity.external_id, 'shared-user-id')
        self.assertEqual(identity.plan, 'plus')
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, 'https://urpa.example.test/api/auth/password-login')
        self.assertEqual(kwargs['json']['clientProduct'], 'geoco')
        self.assertNotIn('secret', str(kwargs['headers']).lower())
        self.assertEqual(kwargs['timeout'], 3)

    @patch('app.services.urpa_auth.requests.post')
    def test_provider_password_error_is_safe_and_actionable(self, post):
        response = Mock(ok=False, status_code=401)
        response.json.return_value = {'message': '手机号或密码不正确。'}
        post.return_value = response
        with self.assertRaises(urpa_auth.UrpaAuthError) as raised:
            urpa_auth.password_login('13800138000', 'wrong')
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(str(raised.exception), 'URPA 手机号或密码错误')


if __name__ == '__main__':
    unittest.main()
