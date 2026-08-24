import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch


os.environ['ZHIPUAI_KEY'] = ''

from app import create_app, db
from app.services.geocoding_apis import TiandituGeocoder


class TiandituGeocodingProxyTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'WTF_CSRF_ENABLED': False,
            'ZHIPUAI_KEY': None,
            'TIANDITU_KEY': 'render-side-key',
            'TIANDITU_PROXY_URL': 'https://urpa.example.test/api/tianditu',
            'TIANDITU_PROXY_TOKEN': 'proxy-secret',
            'ERROR_CENTER_ENABLED': False,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_forward_geocoding_uses_urpa_operation_without_render_key(self):
        geocoder = TiandituGeocoder('render-side-key')
        proxy_response = {
            'status': '0',
            'location': {
                'lon': '104.83',
                'lat': '26.59',
                'keyWord': '贵州省六盘水市钟山区水城钢铁厂',
                'score': '88',
            },
        }

        with patch.object(
            geocoder,
            '_make_tianditu_request',
            new=AsyncMock(return_value=proxy_response),
        ) as request:
            result = asyncio.run(geocoder.geocode('贵州省六盘水市钟山区水城钢铁厂'))

        self.assertEqual(result['source'], 'tianditu')
        direct_params, proxy_payload, _current_key, service_name = request.call_args.args
        self.assertEqual(proxy_payload, {
            'operation': 'geocode',
            'address': '贵州省六盘水市钟山区水城钢铁厂',
        })
        self.assertEqual(service_name, 'tianditu')
        self.assertNotIn('render-side-key', str(proxy_payload))
        self.assertEqual(direct_params['tk'], 'render-side-key')

    def test_reverse_geocoding_uses_urpa_operation(self):
        geocoder = TiandituGeocoder('render-side-key')
        proxy_response = {
            'status': '0',
            'result': {
                'formatted_address': '贵州省六盘水市钟山区',
                'addressComponent': {
                    'province': '贵州省',
                    'city': '六盘水市',
                    'district': '钟山区',
                },
            },
        }

        with patch.object(
            geocoder,
            '_make_tianditu_request',
            new=AsyncMock(return_value=proxy_response),
        ) as request:
            result = asyncio.run(geocoder.reverse_geocode(26.59, 104.83))

        self.assertEqual(result['source'], 'tianditu_reverse')
        proxy_payload = request.call_args.args[1]
        self.assertEqual(proxy_payload, {
            'operation': 'reverse_geocode',
            'latitude': 26.59,
            'longitude': 104.83,
        })

    def test_direct_request_remains_available_without_proxy_config(self):
        self.app.config.update({
            'TIANDITU_PROXY_URL': None,
            'TIANDITU_PROXY_TOKEN': None,
        })
        geocoder = TiandituGeocoder('render-side-key')
        geocoder._make_request = AsyncMock(return_value={'status': '0', 'location': {}})

        asyncio.run(geocoder._make_tianditu_request(
            {'ds': '{}', 'tk': 'render-side-key'},
            {'operation': 'geocode', 'address': '测试'},
            'render-side-key',
            'tianditu',
        ))

        request_params = geocoder._make_request.call_args.args[1]
        self.assertEqual(request_params['tk'], 'render-side-key')
        self.assertEqual(request_params['key'], 'render-side-key')


if __name__ == '__main__':
    unittest.main()
