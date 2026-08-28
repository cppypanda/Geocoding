import json
import unittest
from unittest.mock import AsyncMock, patch

from app import create_app, db
from app.models import AddressLog, GeocodingTask, InteractionEvent, User


class InteractionAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'PROPAGATE_EXCEPTIONS': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'SECRET_KEY': 'interaction-test-secret',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

        self.user = User(email='analytics@example.test', points=100)
        db.session.add(self.user)
        db.session.commit()
        self.login(self.user)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    def create_tracking_records(self):
        task = GeocodingTask(
            user_id=self.user.id,
            task_name='测试任务',
            run_mode='multisource',
            trigger_origin='human_multisource',
        )
        db.session.add(task)
        db.session.flush()
        address = AddressLog(
            task_id=task.id,
            address_index=0,
            address_keyword='测试地址',
            confidence=0.5,
            initial_source='baidu',
            final_source='baidu',
            final_confidence=0.5,
        )
        db.session.add(address)
        db.session.commit()
        return task, address

    def test_manual_map_event_updates_final_address_snapshot(self):
        task, address = self.create_tracking_records()
        response = self.client.post('/geocode/interaction_events', json={
            'event_name': 'map_manual_mark_completed',
            'trigger_origin': 'human_manual_map',
            'client_event_id': 'evt.manual-map-0001',
            'geocoding_task_id': task.id,
            'address_log_id': address.id,
            'metadata': {
                'final_source': 'manual_mark',
                'confidence_after': 1.0,
                'latitude_wgs84': 39.9,
                'longitude_wgs84': 116.4,
                'selection_method': 'manual_map_mark',
                'correction_source': 'manual_map',
                'raw_address': 'must-not-be-stored',
            },
        })

        self.assertEqual(response.status_code, 200)
        event = InteractionEvent.query.one()
        self.assertEqual(event.event_source, 'human')
        self.assertNotIn('raw_address', json.loads(event.metadata_json))

        updated = db.session.get(AddressLog, address.id)
        self.assertTrue(updated.corrected)
        self.assertEqual(updated.final_source, 'manual_mark')
        self.assertEqual(updated.correction_source, 'manual_map')
        self.assertEqual(updated.final_latitude_wgs84, 39.9)

    def test_event_is_idempotent_and_cannot_cross_user_boundary(self):
        task, address = self.create_tracking_records()
        payload = {
            'event_name': 'result_card_selected',
            'trigger_origin': 'human_result_card',
            'client_event_id': 'evt.idempotent-0001',
            'geocoding_task_id': task.id,
            'address_log_id': address.id,
        }
        self.assertEqual(self.client.post('/geocode/interaction_events', json=payload).status_code, 200)
        duplicate = self.client.post('/geocode/interaction_events', json=payload)
        self.assertTrue(duplicate.get_json()['duplicate'])
        self.assertEqual(InteractionEvent.query.count(), 1)

        other = User(email='other@example.test')
        db.session.add(other)
        db.session.flush()
        other_task = GeocodingTask(
            user_id=other.id,
            task_name='其他用户任务',
            run_mode='multisource',
            trigger_origin='human_multisource',
        )
        db.session.add(other_task)
        db.session.flush()
        other_address = AddressLog(
            task_id=other_task.id,
            address_keyword='其他地址',
        )
        db.session.add(other_address)
        db.session.commit()
        denied = self.client.post('/geocode/interaction_events', json={
            **payload,
            'client_event_id': 'evt.cross-user-0001',
            'geocoding_task_id': other_task.id,
            'address_log_id': other_address.id,
        })
        self.assertEqual(denied.status_code, 404)

    @patch('app.routes.geocoding._process_batch_geocoding_async', new_callable=AsyncMock)
    def test_smart_mode_and_client_ids_are_forwarded_to_task_processing(self, process_batch):
        process_batch.return_value = {
            'results': [{'selected_result': {'api': 'baidu'}}],
            'semantic_analysis': {},
            'tracking': None,
        }
        response = self.client.post('/geocode/process', json={
            'addresses': ['测试地址'],
            'mode': 'smart',
            'trigger_origin': 'human_smart_oneclick',
            'client_session_id': 'ses.12345678',
            'client_action_id': 'act.12345678',
        })
        self.assertEqual(response.status_code, 200)
        tracking = process_batch.await_args.args[3]
        self.assertEqual(tracking['run_mode'], 'smart')
        self.assertEqual(tracking['trigger_origin'], 'human_smart_oneclick')
        self.assertEqual(tracking['client_action_id'], 'act.12345678')


if __name__ == '__main__':
    unittest.main()
