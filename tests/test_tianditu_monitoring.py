import asyncio
import os
import unittest
from unittest.mock import Mock, patch

import requests


os.environ['ZHIPUAI_KEY'] = ''

from app import create_app, db
from app.models import ErrorRecord
from app.services.poi_search import TiandituSearcher


class TiandituMonitoringTests(unittest.TestCase):
    SECRET_KEY_VALUE = 'tdt-secret-must-not-appear'

    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'TIANDITU_KEY': self.SECRET_KEY_VALUE,
            'ERROR_CENTER_ENABLED': True,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _search(self, side_effect=None, response=None):
        searcher = TiandituSearcher()
        with patch(
            'app.services.poi_search.requests.get',
            side_effect=side_effect,
            return_value=response,
        ):
            return asyncio.run(searcher.search('测试地址'))

    def _assert_recorded(self, expected_code):
        record = ErrorRecord.query.one()
        self.assertIn(expected_code, record.message)
        self.assertNotIn(self.SECRET_KEY_VALUE, record.message)
        self.assertNotIn('tk=', record.message)
        return record

    def test_timeout_is_classified_and_redacted(self):
        result = self._search(side_effect=requests.Timeout(
            f'https://api.tianditu.gov.cn/v2/search?tk={self.SECRET_KEY_VALUE}'
        ))

        self.assertEqual(result['error_code'], 'TDT_TIMEOUT')
        record = self._assert_recorded('TDT_TIMEOUT')
        self.assertIn('exception_type=Timeout', record.message)

    def test_http_error_records_status_without_body_or_key(self):
        response = Mock(
            status_code=503,
            headers={'Content-Type': 'text/html; charset=utf-8'},
            content=f'upstream error tk={self.SECRET_KEY_VALUE}'.encode(),
        )

        result = self._search(response=response)

        self.assertEqual(result['error_code'], 'TDT_HTTP_ERROR')
        record = self._assert_recorded('TDT_HTTP_ERROR')
        self.assertIn('http_status=503', record.message)
        self.assertIn('content_type=text/html', record.message)

    def test_invalid_json_records_response_metadata_only(self):
        response = Mock(
            status_code=200,
            headers={'Content-Type': 'text/html'},
            content=f'<!DOCTYPE html> tk={self.SECRET_KEY_VALUE}'.encode(),
        )
        response.json.side_effect = ValueError('invalid JSON')

        result = self._search(response=response)

        self.assertEqual(result['error_code'], 'TDT_INVALID_JSON')
        record = self._assert_recorded('TDT_INVALID_JSON')
        self.assertIn('content_type=text/html', record.message)
        self.assertNotIn('<!DOCTYPE', record.message)

    def test_provider_error_records_only_business_code(self):
        response = Mock(
            status_code=200,
            headers={'Content-Type': 'application/json'},
            content=b'{}',
        )
        response.json.return_value = {
            'status': {
                'infocode': 1001,
                'cndesc': f'invalid key {self.SECRET_KEY_VALUE}',
            }
        }

        result = self._search(response=response)

        self.assertEqual(result['error_code'], 'TDT_API_ERROR')
        record = self._assert_recorded('TDT_API_ERROR')
        self.assertIn('provider_code=1001', record.message)
        self.assertNotIn('invalid key', record.message)

    def test_successful_response_is_not_added_to_error_center(self):
        response = Mock(
            status_code=200,
            headers={'Content-Type': 'application/json'},
            content=b'{}',
        )
        response.json.return_value = {
            'status': {'infocode': 1000},
            'resultType': 1,
            'count': 0,
            'pois': [],
        }

        result = self._search(response=response)

        self.assertEqual(result, {'pois': []})
        self.assertEqual(ErrorRecord.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
