import asyncio
import unittest
import requests
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import OperationalError

from app import create_app, db
from app.models import RechargeOrder, User
from app.routes import geocoding
from app.services import llm_service


class ModelRoutingAndGeocoderOrderTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'ZHIPUAI_KEY': None,
            'ZHIPUAI_MODEL': 'glm-4.7-flash',
            'DEEPSEEK_API_KEY': 'test-deepseek-key',
            'DEEPSEEK_API_BASE': 'https://api.deepseek.com',
            'DEEPSEEK_MODEL': 'deepseek-v4-flash',
            'SECRET_KEY': 'model-routing-test',
            'WTF_CSRF_ENABLED': False,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _create_user(self, email):
        user = User(email=email, points=100)
        db.session.add(user)
        db.session.commit()
        return user

    def test_geocoding_cascade_is_baidu_tianditu_amap(self):
        calls = []

        class FakeGeocoder:
            def __init__(self, provider):
                self.provider = provider

            async def geocode(self, address, parsed_address=None):
                calls.append(self.provider)
                return {
                    'source': self.provider,
                    'formatted_address': address,
                    'longitude_gcj02': 116.4,
                    'latitude_gcj02': 39.9,
                    'confidence': 0.1,
                }

        with (
            patch.object(
                geocoding.geocoding_apis,
                'get_geocoder',
                side_effect=lambda provider, user_id: FakeGeocoder(provider),
            ),
            patch.object(geocoding.address_processing, 'calculate_confidence_B', return_value=0.1),
            patch.object(geocoding, '_post_process_winner', new=AsyncMock(side_effect=lambda winner, *_: winner)),
        ):
            result = asyncio.run(geocoding._get_best_geocode_result(
                '测试地址', 1, {'province': '测试省'}, debug=True
            ))

        self.assertEqual(calls, ['baidu', 'tianditu', 'amap'])
        self.assertEqual(
            [item['api'] for item in result['all_results']],
            ['baidu', 'tianditu', 'amap'],
        )

    def test_regular_user_uses_configured_glm_model(self):
        user = self._create_user('regular@example.test')
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='ok')
        )])
        completion = MagicMock(return_value=response)
        self.app.extensions['zhipuai_client'] = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=completion))
        )

        result = asyncio.run(llm_service.call_llm_api('test', user_id=user.id, max_retries=1))

        self.assertIsNone(result['error'])
        self.assertEqual(result['provider'], 'zhipuai')
        self.assertEqual(result['model'], 'glm-4.7-flash')
        self.assertEqual(completion.call_args.kwargs['model'], 'glm-4.7-flash')
        self.assertEqual(completion.call_args.kwargs['timeout'], 25)

    @patch('app.services.llm_service.random.uniform', return_value=0)
    @patch('app.services.llm_service.asyncio.sleep', new_callable=AsyncMock)
    @patch('app.services.llm_service.requests.post')
    def test_regular_user_falls_back_to_deepseek_after_one_glm_attempt(
            self, post, sleep, _uniform):
        user = self._create_user('glm-fallback@example.test')
        completion = MagicMock(side_effect=RuntimeError('temporary GLM failure'))
        self.app.extensions['zhipuai_client'] = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=completion))
        )
        http_response = MagicMock()
        http_response.json.return_value = {
            'choices': [{'message': {'content': 'deepseek-fallback-ok'}}]
        }
        post.return_value = http_response

        result = asyncio.run(llm_service.call_llm_api('test', user_id=user.id))

        self.assertIsNone(result['error'])
        self.assertEqual(completion.call_count, 1)
        sleep.assert_not_awaited()
        self.assertEqual(post.call_count, 1)
        self.assertEqual(result['provider'], 'deepseek')
        self.assertEqual(result['fallback_from'], 'zhipuai')

    @patch('app.services.llm_service.random.uniform', return_value=0)
    @patch('app.services.llm_service.asyncio.sleep', new_callable=AsyncMock)
    @patch('app.services.llm_service.requests.post')
    @patch('app.services.llm_service._is_recharge_member', return_value=False)
    def test_fallback_does_not_query_membership_again(
            self, is_member, post, sleep, _uniform):
        user = self._create_user('single-membership-query@example.test')
        completion = MagicMock(side_effect=RuntimeError('temporary GLM failure'))
        self.app.extensions['zhipuai_client'] = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=completion))
        )
        http_response = MagicMock()
        http_response.json.return_value = {
            'choices': [{'message': {'content': 'deepseek-fallback-ok'}}]
        }
        post.return_value = http_response

        result = asyncio.run(llm_service.call_llm_api('test', user_id=user.id, max_retries=1))

        self.assertIsNone(result['error'])
        self.assertEqual(result['provider'], 'deepseek')
        self.assertEqual(is_member.call_count, 1)

    @patch('app.services.llm_service._reset_failed_db_session')
    @patch('app.services.llm_service._has_completed_recharge')
    def test_membership_query_recovers_after_stale_database_connection(
            self, has_completed_recharge, reset_session):
        stale_connection = OperationalError(
            'SELECT recharge_orders', {}, Exception('SSL connection has been closed unexpectedly')
        )
        has_completed_recharge.side_effect = [stale_connection, False]

        is_member = llm_service._is_recharge_member(123)

        self.assertFalse(is_member)
        self.assertEqual(has_completed_recharge.call_count, 2)
        reset_session.assert_called_once_with()

    @patch('app.services.llm_service._reset_failed_db_session')
    @patch('app.services.llm_service._has_completed_recharge')
    def test_membership_query_degrades_after_retry_failure(
            self, has_completed_recharge, reset_session):
        stale_connection = OperationalError(
            'SELECT recharge_orders', {}, Exception('SSL connection has been closed unexpectedly')
        )
        has_completed_recharge.side_effect = [stale_connection, stale_connection]

        is_member = llm_service._is_recharge_member(123)

        self.assertFalse(is_member)
        self.assertEqual(has_completed_recharge.call_count, 2)
        self.assertEqual(reset_session.call_count, 2)

    @patch('app.services.llm_service.random.uniform', return_value=0)
    @patch('app.services.llm_service.asyncio.sleep', new_callable=AsyncMock)
    @patch('app.services.llm_service.requests.post', side_effect=requests.Timeout('timeout'))
    def test_recharge_member_falls_back_to_glm_after_deepseek_retries(
            self, post, sleep, _uniform):
        user = self._create_user('deepseek-fallback@example.test')
        db.session.add(RechargeOrder(
            user_id=user.id,
            order_number='paid-order-fallback',
            package_name='测试套餐',
            amount=10.0,
            points=200,
            status='COMPLETED',
        ))
        db.session.commit()
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='glm-fallback-ok')
        )])
        completion = MagicMock(return_value=response)
        self.app.extensions['zhipuai_client'] = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=completion))
        )

        result = asyncio.run(llm_service.call_llm_api('test', user_id=user.id))

        self.assertIsNone(result['error'])
        self.assertEqual(post.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1, 2])
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(result['provider'], 'zhipuai')
        self.assertEqual(result['fallback_from'], 'deepseek')

    @patch('app.services.llm_service.requests.post')
    def test_recharge_member_uses_deepseek_flash_without_thinking(self, post):
        user = self._create_user('member@example.test')
        db.session.add(RechargeOrder(
            user_id=user.id,
            order_number='paid-order-1',
            package_name='测试套餐',
            amount=10.0,
            points=200,
            status='COMPLETED',
        ))
        db.session.commit()
        http_response = MagicMock()
        http_response.json.return_value = {
            'choices': [{'message': {'content': 'member-ok'}}]
        }
        post.return_value = http_response

        result = asyncio.run(llm_service.call_llm_api('test', user_id=user.id, max_retries=1))

        self.assertIsNone(result['error'])
        self.assertEqual(result['provider'], 'deepseek')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], 'deepseek-v4-flash')
        self.assertEqual(payload['thinking'], {'type': 'disabled'})
        self.assertEqual(post.call_args.kwargs['timeout'], 25)

    def test_auto_select_echoes_browser_request_id(self):
        user = self._create_user('request-id@example.test')
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

        request_id = 'web-test-request-1234'
        with (
            patch.object(geocoding, '_charge_points_or_402', return_value=(2, None, None)),
            patch.object(
                geocoding.llm_service,
                'select_best_poi_from_search',
                new=AsyncMock(return_value={'selected_index': 0}),
            ),
        ):
            response = client.post(
                '/geocode/auto_select_point',
                headers={'X-Request-ID': request_id},
                json={
                    'original_address': '测试地址',
                    'poi_results': [{'name': '测试地点'}],
                    'source_context': '地图搜索',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['X-Request-ID'], request_id)
        self.assertEqual(response.get_json()['request_id'], request_id)


if __name__ == '__main__':
    unittest.main()
