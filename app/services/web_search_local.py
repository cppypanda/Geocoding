import os
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from flask import current_app

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Connection": "keep-alive",
}

DEFAULT_SEARXNG_URL = "http://127.0.0.1:8888"


def _get_searxng_url() -> str:
    """Return the configured SearXNG endpoint without a trailing slash."""
    configured = current_app.config.get('SEARXNG_URL') or os.environ.get('SEARXNG_URL')
    return (configured or DEFAULT_SEARXNG_URL).strip().rstrip('/')


def _get_searxng_headers() -> dict[str, str]:
    headers = {'Accept': 'application/json'}
    api_key = current_app.config.get('SEARXNG_API_KEY') or os.environ.get('SEARXNG_API_KEY')
    if api_key:
        headers['X-SearXNG-Token'] = api_key.strip()
    return headers

def _fix_weixin_url(url: str) -> str:
    try:
        if 'mp.weixin.qq.com' in url:
            if url.startswith('http'):
                return url
            if url.startswith('//'):
                return 'https:' + url
            if 'url=' in url:
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                if 'url' in qs:
                    return qs['url'][0]
            return 'https://mp.weixin.qq.com' + url
        return url
    except Exception:
        return url


def _get_real_url(sogou_url: str) -> str:
    try:
        if 'weixin.qq.com' in sogou_url or 'mp.weixin.qq.com' in sogou_url:
            return _fix_weixin_url(sogou_url)

        if sogou_url.startswith('/'):
            full_url = f"https://www.sogou.com{sogou_url}"
        else:
            full_url = sogou_url

        resp = requests.head(full_url, headers=HEADERS, allow_redirects=False, timeout=8)
        if resp.status_code in (301, 302):
            return resp.headers.get('Location', '')

        resp = requests.get(full_url, headers=HEADERS, allow_redirects=False, timeout=10)
        if resp.status_code in (301, 302):
            return resp.headers.get('Location', '')

        m = re.search(r"window\.location\.replace\([\"\'](.*?)[\"\']", resp.text)
        if m:
            return m.group(1)
        return full_url
    except Exception:
        return sogou_url


def _get_article_content(url: str) -> str:
    try:
        headers = dict(HEADERS)
        if 'mp.weixin.qq.com' in url:
            headers.update({'Host': 'mp.weixin.qq.com', 'Referer': 'https://mp.weixin.qq.com/'})
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()  # 确保请求成功
        
        # 将原始二进制内容传给BeautifulSoup，让它来处理编码问题，更为可靠
        soup = BeautifulSoup(resp.content, 'html.parser')

        # 移除噪声
        for tag in soup(['script', 'style', 'iframe']):
            tag.decompose()

        article = (
            soup.find('article') or
            soup.find('div', id='js_content') or
            soup.find('div', class_='rich_media_content') or
            soup.find('div', class_=re.compile(r'(article|content|text|main)', re.I)) or
            soup.find('div', id=re.compile(r'(article|content|text|main)', re.I))
        )
        text = ''
        if article:
            text = article.get_text(' ', strip=True)
        else:
            text = soup.body.get_text(' ', strip=True) if soup.body else ''

        # 清理
        text = re.sub(r"\s+", " ", text)
        return text[:4000]
    except Exception:
        return ''


def _extract_relevant_sentences(original_address: str, text: str, max_sentences: int = 3) -> str:
    if not text:
        return ''
    # 分句（中文/英文标点）
    sentences = re.split(r'[。！？!?；;\n]+', text)
    if not sentences:
        return ''

    # 地址关键词与行政区关键词
    addr_tokens = [t for t in re.split(r'[\s,，、]+', original_address) if t]
    keywords = [
        '位于', '坐落', '地处', '隶属于', '行政区', '辖区', '省', '市', '县', '区', '镇', '乡', '街道',
        '大道', '公路', '道路', '路', '巷', '村', '社区', '附近', '坐标', '经度', '纬度'
    ]

    def score(s: str) -> float:
        sc = 0.0
        s_low = s.lower()
        for k in keywords:
            if k in s:
                sc += 1.0
        for tok in addr_tokens[-3:]:  # 取地址尾部3个片段更有辨识度
            if tok and tok.lower() in s_low:
                sc += 1.5
        # 略惩罚过短/过长
        if len(s) < 8:
            sc -= 0.5
        if len(s) > 120:
            sc -= 0.2
        return sc

    ranked = sorted([s for s in sentences if s.strip()], key=score, reverse=True)
    picked = ranked[:max_sentences]
    return '。'.join(picked)


def search_searxng(query: str, max_results: int = 10) -> list[dict]:
    """通过 URPA 同款 SearXNG JSON API 搜索并补抓网页正文。"""
    if not query:
        return []

    base_url = _get_searxng_url()
    try:
        response = requests.get(
            f"{base_url}/search",
            params={'q': query, 'format': 'json', 'pageno': 1},
            headers=_get_searxng_headers(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        current_app.logger.warning(
            "SearXNG 搜索失败，将尝试搜狗降级。endpoint=%s error=%s",
            base_url,
            type(exc).__name__,
        )
        return []

    raw_results = payload.get('results') if isinstance(payload, dict) else []
    if not isinstance(raw_results, list):
        current_app.logger.warning("SearXNG 返回了无效的 results 字段。endpoint=%s", base_url)
        return []

    def result_score(item):
        try:
            return float(item.get('score') or 0)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    results: list[dict] = []
    seen_urls: set[str] = set()
    for item in sorted(raw_results, key=result_score, reverse=True):
        if not isinstance(item, dict):
            continue
        url = str(item.get('url') or '').strip()
        if not url or url in seen_urls or not url.lower().startswith(('http://', 'https://')):
            continue
        seen_urls.add(url)

        title = re.sub(r"\s+", " ", str(item.get('title') or '')).strip()
        description = re.sub(r"\s+", " ", str(item.get('content') or '')).strip()
        body_text = _get_article_content(url)
        analysis_content = body_text or description
        picked = _extract_relevant_sentences(query, body_text, max_sentences=3)
        excerpt_core = picked or description or title
        if not excerpt_core:
            continue

        excerpt = (
            f"{title}：{excerpt_core}"
            if title and not excerpt_core.startswith(title)
            else excerpt_core
        )
        engines = item.get('engines') or ([item.get('engine')] if item.get('engine') else [])
        results.append({
            'title': title,
            'url': url,
            'description': description,
            'excerpt': excerpt[:800],
            'sources': [url],
            # 部分站点会拒绝正文抓取；此时保留 SearXNG 聚合出的搜索摘要，
            # 避免后续情报整理链路因为正文为空而直接丢弃该结果。
            'raw_content': analysis_content,
            'provider': 'searxng',
            'engines': [str(engine) for engine in engines if engine],
        })
        if len(results) >= max_results:
            break

    current_app.logger.info(
        "SearXNG 搜索 '%s' 返回 %s 条可用结果（原始结果 %s 条）。",
        query,
        len(results),
        len(raw_results),
    )
    return results


def search_sogou(query: str, max_results: int = 10) -> list[dict]:
    """使用搜狗网页搜索抓取前若干条搜索结果，输出简要摘录。

    返回的每一项结构为：
    { 'excerpt': '标题 - 简介', 'sources': ['https://xxx'] }
    """
    if not query:
        return []

    results: list[dict] = []
    try:
        url = f"https://www.sogou.com/web?query={requests.utils.quote(query)}&page=1"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 兼容多种结果容器
        containers = soup.find_all('div', class_='vrwrap')
        if not containers:
            containers = soup.select('div.results, div.rb, div.vrResult')

        current_app.logger.info(f"搜狗搜索 '{query}' 找到 {len(containers)} 个结果容器。")

        for item in containers:
            # 标题
            a = item.select_one('h3 a') or item.find('a')
            title = a.get_text(strip=True) if a else ''
            href = a.get('href') if a and a.has_attr('href') else ''
            real_url = _get_real_url(href) if href else ''
            # 简介
            desc_elem = item.select_one('.text-layout') or item.find('p') or item.find('div')
            desc = desc_elem.get_text(strip=True) if desc_elem else ''
            # 清理文本
            title = re.sub(r"\s+", " ", title)
            desc = re.sub(r"\s+", " ", desc)

            # 抓取正文并抽取与地址相关句子
            body_text = _get_article_content(real_url) if real_url else ''
            picked = _extract_relevant_sentences(query, body_text, max_sentences=3)
            excerpt_core = picked or desc or title
            if excerpt_core:
                # 将标题附在前面，正文摘录在后
                if title and excerpt_core and not excerpt_core.startswith(title):
                    excerpt = f"{title}：{excerpt_core}"
                else:
                    excerpt = excerpt_core
                sources = [real_url or href] if (real_url or href) else []
                results.append({
                    'title': title,
                    'url': (real_url or href or ''),
                    'excerpt': excerpt[:800],
                    'sources': sources,
                    'raw_content': body_text,
                    'provider': 'sogou_local',
                    'engines': ['sogou'],
                })
            if len(results) >= max_results:
                break
    except Exception as e:
        # 静默失败，返回已收集的结果
        current_app.logger.error(f"搜狗搜索失败，查询: '{query}'. 错误: {e}", exc_info=True)
        pass

    return results


def search_web(query: str, max_results: int = 10) -> list[dict]:
    """统一网络搜索入口：SearXNG 优先，失败或无结果时降级到搜狗。"""
    results = search_searxng(query, max_results=max_results)
    if results:
        return results
    current_app.logger.info("SearXNG 未返回可用结果，开始使用搜狗降级搜索。")
    return search_sogou(query, max_results=max_results)


