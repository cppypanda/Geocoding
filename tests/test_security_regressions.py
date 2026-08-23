import re
import unittest
from unittest.mock import patch

from app import create_app, db
from app.models import EmailVerificationCode, RechargeCard, RechargeOrder, User, UserApiKey
from app.routes.geocoding import deduct_points
from app.routes.main import _safe_export_name


class SecurityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'PROPAGATE_EXCEPTIONS': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'SECRET_KEY': 'security-test-secret',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def create_user(self, email='security@example.test', points=10):
        user = User(email=email, points=points)
        db.session.add(user)
        db.session.commit()
        return user

    def login(self, user):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    @patch('app.routes.auth.email_service.send_email')
    def test_verification_code_is_server_side_hashed_and_single_use(self, send_email):
        sent = self.client.post('/send_verification_code', json={
            'email': 'NewUser@Example.Test',
            'purpose': 'register_login',
        })
        self.assertEqual(sent.status_code, 200)
        body = send_email.call_args.args[2]
        code = re.search(r'(\d{6})', body).group(1)

        with self.client.session_transaction() as session:
            self.assertNotIn('verification_codes', session)
        record = EmailVerificationCode.query.one()
        self.assertEqual(record.email, 'newuser@example.test')
        self.assertNotEqual(record.code_digest, code)

        logged_in = self.client.post('/login_register_email', json={
            'email': 'newuser@example.test',
            'code': code,
        })
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(EmailVerificationCode.query.count(), 0)
        reused = self.client.post('/login_register_email', json={
            'email': 'newuser@example.test',
            'code': code,
        })
        self.assertEqual(reused.status_code, 400)

    @patch('app.routes.auth.email_service.send_email')
    def test_verification_attempts_are_limited(self, send_email):
        self.client.post('/send_verification_code', json={
            'email': 'attempts@example.test',
            'purpose': 'register_login',
        })
        for _ in range(5):
            response = self.client.post('/login_register_email', json={
                'email': 'attempts@example.test',
                'code': '000000',
            })
            self.assertEqual(response.status_code, 400)
        blocked = self.client.post('/login_register_email', json={
            'email': 'attempts@example.test',
            'code': '000000',
        })
        self.assertEqual(blocked.status_code, 429)

    def test_paid_api_requires_login_and_atomic_balance(self):
        anonymous = self.client.post('/geocode/poi_search', json={
            'keyword': '西湖', 'source': 'amap',
        })
        self.assertEqual(anonymous.status_code, 401)

        user = self.create_user(points=2)
        self.assertTrue(deduct_points(user.id, 2))
        self.assertFalse(deduct_points(user.id, 1))
        db.session.expire_all()
        self.assertEqual(db.session.get(User, user.id).points, 0)

    def test_invalid_export_does_not_charge_and_name_is_confined(self):
        user = self.create_user(points=10)
        self.login(user)
        response = self.client.post('/export', json={
            'format': 'kml',
            'location_name': '../../outside',
            'data': [{'name': 'missing coordinates'}],
        })
        self.assertEqual(response.status_code, 400)
        db.session.expire_all()
        self.assertEqual(db.session.get(User, user.id).points, 10)
        safe_name = _safe_export_name('../../outside')
        self.assertNotIn('..', safe_name)
        self.assertNotIn('/', safe_name)
        self.assertNotIn('\\', safe_name)

    @patch('app.routes.user._validate_amap_key', return_value=(True, ''))
    def test_api_key_fields_are_consistent_and_masked(self, _validator):
        user = self.create_user(points=0)
        self.login(user)
        saved = self.client.post('/user/keys', json={
            'service_name': 'amap',
            'api_key': 'abcdefgh12345678',
        })
        self.assertEqual(saved.status_code, 200)
        key = UserApiKey.query.one()
        self.assertEqual(key.service_name, 'amap')
        listed = self.client.get('/user/keys')
        self.assertEqual(listed.status_code, 200)
        self.assertNotIn('abcdefgh12345678', listed.get_data(as_text=True))

    def test_card_is_single_use_and_account_is_soft_deleted(self):
        user = self.create_user(points=0)
        self.login(user)
        card = RechargeCard(code='SECURE-CARD', points=50, is_used=False)
        order = RechargeOrder(
            user_id=user.id,
            order_number='SOFT-DELETE-ORDER',
            package_name='测试',
            amount=1,
            points=1,
            status='PENDING',
        )
        db.session.add_all([card, order])
        db.session.commit()

        first = self.client.post('/redeem_card', json={'code': 'SECURE-CARD'})
        second = self.client.post('/redeem_card', json={'code': 'SECURE-CARD'})
        self.assertEqual(first.status_code, 200)
        self.assertIn(second.status_code, (400, 409))
        db.session.expire_all()
        self.assertEqual(db.session.get(User, user.id).points, 50)

        deleted = self.client.post('/user/delete_account')
        self.assertEqual(deleted.status_code, 200)
        retained_user = db.session.get(User, user.id)
        self.assertTrue(retained_user.is_deleted)
        self.assertIsNotNone(RechargeOrder.query.filter_by(user_id=user.id).first())

    def test_legacy_migration_route_is_removed_and_logout_is_post_only(self):
        self.assertEqual(self.client.get('/admin/run-migration').status_code, 404)
        self.assertEqual(self.client.get('/logout').status_code, 405)

    def test_batch_geocoding_has_a_hard_input_limit(self):
        user = self.create_user()
        self.login(user)
        response = self.client.post('/geocode/process', json={
            'addresses': ['测试地址'] * 501,
        })
        self.assertEqual(response.status_code, 413)

    @patch('app.routes.geocoding._process_batch_geocoding_async')
    def test_batch_geocoding_reports_total_provider_failure(self, process_batch):
        async def failed_batch(*_args, **_kwargs):
            return {
                'results': [{
                    'address': '测试地址',
                    'selected_result': {'api': 'error', 'name': '处理失败'},
                    'api_results': [],
                }],
                'semantic_analysis': {},
            }

        process_batch.side_effect = failed_batch
        user = self.create_user()
        self.login(user)
        response = self.client.post('/geocode/process', json={'addresses': ['测试地址']})
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.get_json()['success'])
        self.assertEqual(response.get_json()['failed_count'], 1)


if __name__ == '__main__':
    unittest.main()
