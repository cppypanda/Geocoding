import unittest
from unittest.mock import patch

from app import create_app, db
from app.models import Task, User
from app.services.urpa_auth import UrpaIdentity


class UrpaAccountMigrationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'PROPAGATE_EXCEPTIONS': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'urpa-migration-test',
            'NEW_USER_REWARD_POINTS': 100,
            'ZHIPUAI_KEY': None,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login_local(self, user):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    @patch('app.routes.auth.urpa_auth.password_login')
    def test_urpa_login_creates_and_reuses_one_local_identity(self, login):
        login.return_value = UrpaIdentity('urpa-user-1', '13800138000', '测试用户')
        first = self.client.post('/urpa_login', json={
            'phone': '138 0013 8000',
            'password': 'secret1',
        })
        self.assertEqual(first.status_code, 200)
        payload = first.get_json()
        self.assertEqual(payload['user']['phone'], '13800138000')
        self.assertEqual(payload['user']['account_origin'], 'urpa')
        self.assertIsNone(payload['user']['email'])
        self.assertEqual(User.query.count(), 1)
        self.assertEqual(User.query.one().points, 100)

        self.client.post('/logout')
        second = self.client.post('/urpa_login', json={
            'phone': '13800138000',
            'password': 'secret1',
        })
        self.assertEqual(second.status_code, 200)
        self.assertEqual(User.query.count(), 1)
        self.assertEqual(User.query.one().points, 100)

    @patch('app.routes.auth.urpa_auth.password_login')
    def test_email_user_can_link_phone_without_losing_business_data(self, login):
        user = User(email='legacy@example.test', points=37, account_origin='email')
        db.session.add(user)
        db.session.commit()
        task = Task(user_id=user.id, task_name='保留任务', result_data='{}')
        db.session.add(task)
        db.session.commit()
        self.login_local(user)
        login.return_value = UrpaIdentity('urpa-user-2', '13900139000', '老用户')

        response = self.client.post('/urpa_link', json={
            'phone': '13900139000',
            'password': 'secret2',
        })
        self.assertEqual(response.status_code, 200)
        db.session.refresh(user)
        self.assertEqual(user.email, 'legacy@example.test')
        self.assertEqual(user.points, 37)
        self.assertEqual(user.urpa_user_id, 'urpa-user-2')
        self.assertEqual(Task.query.filter_by(user_id=user.id).count(), 1)
        self.assertFalse(response.get_json()['user']['needs_phone_binding'])

    @patch('app.routes.auth.urpa_auth.password_login')
    def test_link_conflict_never_merges_accounts_implicitly(self, login):
        linked = User(
            email='urpa-existing@accounts.invalid',
            phone='13700137000',
            urpa_user_id='urpa-user-3',
            account_origin='urpa',
            points=88,
        )
        legacy = User(email='legacy2@example.test', points=12, account_origin='email')
        db.session.add_all([linked, legacy])
        db.session.commit()
        self.login_local(legacy)
        login.return_value = UrpaIdentity('urpa-user-3', '13700137000', '冲突用户')

        response = self.client.post('/urpa_link', json={
            'phone': '13700137000',
            'password': 'secret3',
        })
        self.assertEqual(response.status_code, 409)
        db.session.refresh(legacy)
        db.session.refresh(linked)
        self.assertIsNone(legacy.phone)
        self.assertEqual(legacy.points, 12)
        self.assertEqual(linked.points, 88)

    @patch('app.routes.auth.urpa_auth.password_login')
    def test_linked_user_cannot_silently_replace_urpa_identity(self, login):
        user = User(
            email='linked@example.test',
            phone='13500135000',
            urpa_user_id='original-urpa-id',
            account_origin='email',
            points=20,
        )
        db.session.add(user)
        db.session.commit()
        self.login_local(user)
        login.return_value = UrpaIdentity('replacement-id', '13400134000', '替换身份')

        response = self.client.post('/urpa_link', json={
            'phone': '13400134000',
            'password': 'secret4',
        })
        self.assertEqual(response.status_code, 409)
        db.session.refresh(user)
        self.assertEqual(user.urpa_user_id, 'original-urpa-id')
        self.assertEqual(user.phone, '13500135000')

    @patch('app.routes.auth.urpa_auth.send_code')
    def test_send_code_uses_urpa_without_storing_code_locally(self, send_code):
        send_code.return_value = {'phone': '13600136000'}
        response = self.client.post('/urpa_send_code', json={
            'phone': '13600136000',
            'purpose': 'register',
        })
        self.assertEqual(response.status_code, 200)
        send_code.assert_called_once_with('13600136000', 'register')


if __name__ == '__main__':
    unittest.main()
