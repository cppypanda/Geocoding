import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.geocoding_apis import BaiduGeocoder
from app.utils.api_managers import APIRateLimiter, REASON_RATE_LIMITED


class APIRateLimiterTests(unittest.TestCase):
    def test_concurrent_slots_are_spaced_instead_of_released_as_a_burst(self):
        limiter = APIRateLimiter(qps=2)
        sleep = AsyncMock()

        with patch('app.utils.api_managers.time.monotonic', return_value=10.0), patch(
            'app.utils.api_managers.asyncio.sleep', sleep
        ):
            asyncio.run(limiter.acquire())
            asyncio.run(limiter.acquire())
            asyncio.run(limiter.acquire())

        self.assertEqual(
            [call.args[0] for call in sleep.await_args_list],
            [0.5, 1.0],
        )


class BaiduConcurrencyClassificationTests(unittest.TestCase):
    def test_business_status_401_concurrency_error_does_not_invalidate_key(self):
        geocoder = BaiduGeocoder('test-key')
        geocoder.key_manager.report_failure = Mock()

        result = geocoder._standardize_result({
            'status': 401,
            'message': '当前并发量已经超过约定并发配额，限制访问',
        }, 'test-key')

        self.assertIn('并发量', result['error'])
        geocoder.key_manager.report_failure.assert_called_once_with(
            'test-key',
            REASON_RATE_LIMITED,
        )


if __name__ == '__main__':
    unittest.main()
