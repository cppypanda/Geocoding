import os
import unittest
from unittest.mock import Mock, patch


os.environ['ZHIPUAI_KEY'] = ''

from app import create_app, db
from app.models import Notification, RechargeOrder, User
from app.routes.payment_bp import _complete_recharge_order
from app.services.payment_service import (
    PaymentConfirmation,
    PaymentProviderError,
    YungouConfig,
    create_yungou_alipay_payment,
    parse_yungou_notify,
    yungou_sign,
)


class YungouPaymentServiceTests(unittest.TestCase):
    def setUp(self):
        self.config = YungouConfig(
            mch_id='123',
            pay_key='secret',
            notify_url='https://example.test/api/pay/yungouos/notify',
        )

    def test_sign_matches_urpa_sdk_algorithm(self):
        params = {
            'code': '1',
            'mchId': '123',
            'money': '10.00',
            'orderNo': 'P',
            'outTradeNo': 'GEO1',
            'payNo': 'X',
        }
        self.assertEqual(yungou_sign(params, 'secret'), '6202AF9C09884CE269C81E7DCC7B0A49')

    def test_parse_signed_paid_callback(self):
        sign_params = {
            'code': '1',
            'mchId': '123',
            'money': '10.00',
            'orderNo': 'provider-order',
            'outTradeNo': 'GEO1',
            'payNo': 'provider-pay',
        }
        confirmation = parse_yungou_notify(
            {**sign_params, 'sign': yungou_sign(sign_params, 'secret')},
            self.config,
        )
        self.assertTrue(confirmation.paid)
        self.assertEqual(confirmation.order_number, 'GEO1')
        self.assertEqual(confirmation.amount_cny, 10.0)
        self.assertEqual(confirmation.provider_trade_no, 'provider-pay')

    def test_callback_rejects_invalid_signature(self):
        with self.assertRaises(PaymentProviderError):
            parse_yungou_notify({
                'code': '1',
                'mchId': '123',
                'money': '10.00',
                'outTradeNo': 'GEO1',
                'sign': 'invalid',
            }, self.config)

    @patch('app.services.payment_service.requests.post')
    def test_create_payment_uses_server_amount_and_returns_url(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {'code': 0, 'data': 'https://qr.alipay.com/example'}
        post.return_value = response

        url = create_yungou_alipay_payment(
            order_number='GEO1',
            amount_cny=10,
            subject='测试积分套餐',
            points=200,
            config=self.config,
        )

        self.assertEqual(url, 'https://qr.alipay.com/example')
        sent = post.call_args.kwargs['data']
        self.assertEqual(sent['total_fee'], '10.00')
        self.assertEqual(sent['mch_id'], '123')
        self.assertNotIn('secret', str(sent))


class RechargeCompletionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        user = User(email='payer@example.test', points=5)
        db.session.add(user)
        db.session.flush()
        db.session.add(RechargeOrder(
            user_id=user.id,
            order_number='GEO-IDEMPOTENT',
            package_name='测试套餐',
            amount=10,
            points=200,
            status='PENDING',
            payment_method='yungouos',
        ))
        db.session.commit()
        self.user_id = user.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_duplicate_confirmation_grants_points_once(self):
        confirmation = PaymentConfirmation(
            order_number='GEO-IDEMPOTENT',
            amount_cny=10,
            paid=True,
            provider_trade_no='PAY-1',
        )
        _, first_was_duplicate = _complete_recharge_order(confirmation)
        _, second_was_duplicate = _complete_recharge_order(confirmation)

        self.assertFalse(first_was_duplicate)
        self.assertTrue(second_was_duplicate)
        self.assertEqual(db.session.get(User, self.user_id).points, 205)
        self.assertEqual(Notification.query.filter_by(user_id=self.user_id).count(), 1)

    def test_amount_mismatch_does_not_grant_points(self):
        with self.assertRaises(PaymentProviderError):
            _complete_recharge_order(PaymentConfirmation(
                order_number='GEO-IDEMPOTENT',
                amount_cny=9.99,
                paid=True,
            ))
        db.session.rollback()
        self.assertEqual(db.session.get(User, self.user_id).points, 5)


class RechargeRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'YUNGOUOS_MCH_ID': '123',
            'YUNGOUOS_PAY_KEY': 'secret',
            'YUNGOUOS_NOTIFY_URL': 'https://example.test/api/pay/yungouos/notify',
            'RECHARGE_PACKAGES': {
                'pkg_test': {'name': '测试套餐', 'points': 200, 'price': 10.0},
            },
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        user = User(email='route-payer@example.test', points=0)
        db.session.add(user)
        db.session.commit()
        self.user_id = user.id
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user_id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_index_renders_recharge_controls(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-package-id="pkg_test"', html)
        self.assertIn('id="initiateRechargePaymentBtn"', html)
        self.assertIn('id="cardCodeInput"', html)

    @patch('app.routes.payment_bp.create_yungou_alipay_payment')
    def test_create_and_poll_payment_order(self, create_payment):
        create_payment.return_value = 'https://qr.alipay.com/route-test'
        created = self.client.post('/api/pay/recharge/create', json={'package_id': 'pkg_test'})
        self.assertEqual(created.status_code, 200)
        order = created.get_json()['order']
        self.assertEqual(order['payment_method'], 'yungouos')
        self.assertEqual(order['payment_url'], 'https://qr.alipay.com/route-test')

        confirmation = PaymentConfirmation(
            order_number=order['order_number'],
            amount_cny=10,
            paid=True,
            provider_trade_no='PAY-ROUTE',
        )
        with patch('app.routes.payment_bp.query_yungou_order', return_value=confirmation):
            polled = self.client.get('/api/pay/recharge/order', query_string={
                'order_number': order['order_number'],
            })
        self.assertEqual(polled.status_code, 200)
        payload = polled.get_json()
        self.assertEqual(payload['order']['status'], 'COMPLETED')
        self.assertEqual(payload['total_points'], 200)


if __name__ == '__main__':
    unittest.main()
