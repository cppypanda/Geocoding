import unittest
from unittest.mock import AsyncMock, patch

from app import create_app, db
from app.models import GeocodingTask, PointTransaction, User


class BillingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'PROPAGATE_EXCEPTIONS': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'SECRET_KEY': 'billing-test-secret',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.user = User(email='billing@example.test', points=20)
        db.session.add(self.user)
        db.session.commit()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.user.id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def balance(self):
        db.session.expire_all()
        return db.session.get(User, self.user.id).points

    def test_pricing_estimate_is_clear_and_bounded(self):
        response = self.client.get('/geocode/pricing/estimate?mode=smart&address_count=3')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['unit_points'], 2)
        self.assertEqual(payload['base_points'], 6)
        self.assertEqual(payload['web_research_points_each'], 2)

    @patch('app.routes.geocoding._process_batch_geocoding_async', new_callable=AsyncMock)
    def test_multisource_is_free_and_smart_is_fixed_per_address(self, process_batch):
        process_batch.return_value = {
            'results': [{'selected_result': {'api': 'baidu'}}],
            'semantic_analysis': {},
            'tracking': None,
        }
        free = self.client.post('/geocode/process', json={
            'addresses': ['地址一'],
            'mode': 'default',
        })
        self.assertEqual(free.status_code, 200)
        self.assertEqual(self.balance(), 20)

        paid = self.client.post('/geocode/process', headers={
            'X-Request-ID': 'smart-batch-test-0001',
        }, json={
            'addresses': ['地址一', '地址二'],
            'mode': 'smart',
        })
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(paid.get_json()['billing']['charged_points'], 4)
        self.assertEqual(self.balance(), 16)
        entry = PointTransaction.query.filter_by(transaction_type='charge').one()
        self.assertEqual(entry.task_key, 'smart_project_address')
        self.assertEqual(entry.points_delta, -4)

    @patch('app.routes.geocoding._process_batch_geocoding_async', new_callable=AsyncMock)
    def test_total_provider_failure_refunds_smart_project(self, process_batch):
        process_batch.return_value = {
            'results': [{'selected_result': {'api': 'error'}}],
            'semantic_analysis': {},
            'tracking': None,
        }
        response = self.client.post('/geocode/process', headers={
            'X-Request-ID': 'smart-refund-test-0001',
        }, json={'addresses': ['失败地址'], 'mode': 'smart'})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.balance(), 20)
        entries = PointTransaction.query.order_by(PointTransaction.id).all()
        self.assertEqual([entry.points_delta for entry in entries], [-2, 2])
        self.assertIn('自动退还', entries[-1].reason)

    @patch('app.routes.geocoding.llm_service.select_best_poi_from_search', new_callable=AsyncMock)
    def test_smart_project_model_selection_is_not_charged_twice(self, select_best):
        select_best.return_value = {'selected_index': 0}
        task = GeocodingTask(
            user_id=self.user.id,
            task_name='智能任务',
            run_mode='smart',
            trigger_origin='human_smart_oneclick',
            client_action_id='act.billing-0001',
        )
        db.session.add(task)
        db.session.commit()
        response = self.client.post('/geocode/auto_select_point', headers={
            'X-Geocoding-Task-ID': str(task.id),
            'X-Geocoding-Action-ID': task.client_action_id,
            'X-Request-ID': 'smart-llm-included-0001',
        }, json={
            'original_address': '测试地址',
            'poi_results': [{'name': '测试地点'}],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.balance(), 20)
        self.assertEqual(PointTransaction.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
