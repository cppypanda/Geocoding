import os
import unittest


os.environ['ZHIPUAI_KEY'] = ''

from app import create_app, db
from app.models import ErrorRecord, User


class ErrorCenterTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'PROPAGATE_EXCEPTIONS': False,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'ERROR_CENTER_ENABLED': True,
        })

        @self.app.post('/api/test-error-center/unhandled')
        def raise_unhandled_error():
            raise RuntimeError('测试异常订单 987654')

        @self.app.get('/api/test-error-center/logged')
        def log_caught_error():
            self.app.logger.error('已经捕获但需要记录的测试错误')
            return {'success': True}

        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        admin = User(email='error-admin@example.test', points=0, is_admin=True)
        db.session.add(admin)
        db.session.commit()
        self.admin_id = admin.id
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_unhandled_errors_are_redacted_and_deduplicated(self):
        for _ in range(2):
            response = self.client.post(
                '/api/test-error-center/unhandled?access_token=query-secret',
                json={'password': 'plain-password', 'address': '杭州'},
            )
            self.assertEqual(response.status_code, 500)
            self.assertTrue(response.get_json()['error_reference'].startswith('ERR-'))

        records = ErrorRecord.query.all()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.exception_type, 'RuntimeError')
        self.assertEqual(record.occurrence_count, 2)
        self.assertIn('[REDACTED]', record.query_params)
        self.assertIn('[REDACTED]', record.request_payload)
        self.assertNotIn('query-secret', record.query_params)
        self.assertNotIn('plain-password', record.request_payload)
        self.assertIn('RuntimeError', record.traceback)

    def test_caught_error_logs_are_collected(self):
        response = self.client.get('/api/test-error-center/logged')
        self.assertEqual(response.status_code, 200)
        record = ErrorRecord.query.one()
        self.assertEqual(record.exception_type, 'LogError')
        self.assertEqual(record.source, f'log:{self.app.logger.name}')

    def test_admin_can_view_and_resolve_error(self):
        self.client.get('/api/test-error-center/logged')
        record = ErrorRecord.query.one()

        listing = self.client.get('/admin/errors?status=all')
        self.assertEqual(listing.status_code, 200)
        self.assertIn('已经捕获但需要记录的测试错误', listing.get_data(as_text=True))

        detail = self.client.get(f'/admin/errors/{record.id}')
        self.assertEqual(detail.status_code, 200)
        self.assertIn(f'ERR-{record.id}', detail.get_data(as_text=True))

        updated = self.client.post(
            f'/admin/errors/{record.id}/status',
            data={'status': 'resolved', 'resolution_notes': '已在测试中修复'},
            follow_redirects=True,
        )
        self.assertEqual(updated.status_code, 200)
        db.session.expire_all()
        record = db.session.get(ErrorRecord, record.id)
        self.assertEqual(record.status, 'resolved')
        self.assertEqual(record.resolved_by_id, self.admin_id)
        self.assertEqual(record.resolution_notes, '已在测试中修复')

    def test_browser_errors_are_collected(self):
        response = self.client.post('/api/client-errors', json={
            'kind': 'promise',
            'type': 'TypeError',
            'message': 'Cannot read properties of undefined',
            'stack': 'TypeError at map-search.js:20:10',
            'location': '/static/js/map-search.js:20:10',
            'token': 'must-not-be-stored',
        })
        self.assertEqual(response.status_code, 204)
        record = ErrorRecord.query.one()
        self.assertEqual(record.exception_type, 'TypeError')
        self.assertEqual(record.source, 'client:promise')
        self.assertIn('map-search.js', record.traceback)
        self.assertNotIn('must-not-be-stored', record.request_payload)


if __name__ == '__main__':
    unittest.main()
