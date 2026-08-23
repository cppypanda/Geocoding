import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app import create_app
from app.services import llm_service, web_search_local


class WebSearchProviderTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'SECRET_KEY': 'web-search-test',
            'SEARXNG_URL': 'http://searxng.test:8888',
            'SEARXNG_API_KEY': 'test-search-token',
            'ZHIPUAI_KEY': None,
        })
        self.context = self.app.app_context()
        self.context.push()

    def tearDown(self):
        self.context.pop()

    @patch.object(web_search_local, '_get_article_content')
    @patch.object(web_search_local.requests, 'get')
    def test_searxng_results_are_sorted_normalized_and_enriched(self, get, extract):
        response = MagicMock()
        response.json.return_value = {
            'results': [
                {
                    'title': '低分结果',
                    'url': 'https://low.example.test/page',
                    'content': '低分摘要',
                    'score': 0.2,
                    'engines': ['sogou'],
                },
                {
                    'title': '高分结果',
                    'url': 'https://high.example.test/page',
                    'content': '高分结果位于测试区测试路。',
                    'score': 0.9,
                    'engines': ['baidu', 'bing'],
                },
            ]
        }
        get.return_value = response
        extract.side_effect = ['', '低分结果位于测试市。']

        results = web_search_local.search_searxng('测试地址', max_results=2)

        self.assertEqual([item['title'] for item in results], ['高分结果', '低分结果'])
        self.assertEqual(results[0]['provider'], 'searxng')
        self.assertEqual(results[0]['engines'], ['baidu', 'bing'])
        self.assertIn('位于测试区', results[0]['excerpt'])
        self.assertEqual(results[0]['raw_content'], '高分结果位于测试区测试路。')
        get.assert_called_once_with(
            'http://searxng.test:8888/search',
            params={'q': '测试地址', 'format': 'json', 'pageno': 1},
            headers={
                'Accept': 'application/json',
                'X-SearXNG-Token': 'test-search-token',
            },
            timeout=15,
        )

    def test_unified_search_falls_back_to_sogou(self):
        fallback = [{'title': '降级结果', 'provider': 'sogou_local'}]
        with (
            patch.object(web_search_local, 'search_searxng', return_value=[]) as searxng,
            patch.object(web_search_local, 'search_sogou', return_value=fallback) as sogou,
        ):
            results = web_search_local.search_web('测试地址', max_results=3)

        self.assertEqual(results, fallback)
        searxng.assert_called_once_with('测试地址', max_results=3)
        sogou.assert_called_once_with('测试地址', max_results=3)

    def test_semantic_search_uses_shared_search_instead_of_zhipu_search_pro(self):
        search_results = [{
            'title': '测试地点介绍',
            'url': 'https://example.test/location',
            'description': '测试地点位于测试区。',
            'raw_content': '测试地点位于测试区测试路，与测试公园相邻。',
        }]
        with (
            patch.object(llm_service, 'search_web', return_value=search_results) as search,
            patch.object(
                llm_service,
                'call_llm_api',
                new=AsyncMock(return_value={'content': '1. 地点：测试公园', 'error': None}),
            ) as call_llm,
        ):
            result = asyncio.run(llm_service.call_zhipu_web_enabled_llm(
                '测试地点', max_retries=2, user_id=7
            ))

        self.assertIsNone(result['error'])
        self.assertEqual(result['web_search_results_count'], 1)
        self.assertEqual(result['web_search_references'], ['https://example.test/location'])
        search.assert_called_once_with('测试地点', max_results=8)
        self.assertEqual(call_llm.await_args.kwargs['user_id'], 7)
        self.assertEqual(call_llm.await_args.kwargs['max_retries'], 2)


if __name__ == '__main__':
    unittest.main()
