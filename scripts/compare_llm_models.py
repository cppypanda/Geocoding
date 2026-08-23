"""Compare the configured GLM and DeepSeek models without exposing API keys."""
import argparse
import json
import os
import time

import requests
from dotenv import load_dotenv
from zhipuai import ZhipuAI


ADDRESSES = [
    '辽宁省鞍山市铁西区鞍山钢铁厂',
    '辽宁省本溪市溪湖区本溪湖煤铁公司',
    '重庆市大渡口区重钢型钢厂',
    '湖北省黄石市西塞山区汉冶萍公司(大冶铁厂)',
    '安徽省合肥市瑶海区合肥钢铁厂',
    '云南省昆明市安宁市昆明钢铁厂',
    '四川省攀枝花市东区攀枝花钢铁厂',
    '湖北省武汉市汉阳区汉冶萍公司(汉阳铁厂)',
    '黑龙江省齐齐哈尔市富拉尔基区北满钢厂',
    '湖北省武汉市青山区武钢一号高炉',
    '湖北省武汉市青山区一米七轧机工程（武钢重点建设项目）',
    '广东省广州市荔湾区广州钢铁厂旧址（广钢工业遗产博览公园）',
    '贵州省黔东南苗族侗族自治州镇远县青溪铁厂遗址',
    '贵州省六盘水市钟山区水城钢铁厂',
    '江苏省南京市梅山钢铁厂',
    '山东省济宁市铁合金1971工业遗址公园',
    '山东省济南市济南重工铸铁车间建筑群',
    '山西省晋城市阳城县应朝钢铁厂旧址',
    '陕西省陕钢厂',
    '四川省攀钢三线建设工业遗产群',
    '云南省昆明市安宁市昆明钢铁厂',
]


def messages():
    prompt = '''你是地理编码数据质量专家。请分析下面这一批待地理编码名录，并严格只输出一个合法 JSON 对象，不要使用 Markdown 代码块。

JSON字段：theme_name、entity_type、spatial_pattern、duplicate_indices、incomplete_indices、suspicious_indices、observations、recommended_queries。
其中三个 indices 字段必须是从1开始的序号数组；observations 为3至6条简短、可核验的观察；recommended_queries 最多5条。不要凭空补造具体地址或坐标。

名录：
''' + '\n'.join(f'{index}. {address}' for index, address in enumerate(ADDRESSES, 1))
    return [
        {'role': 'system', 'content': '你是严谨的中国历史工业遗产地理数据分析专家。'},
        {'role': 'user', 'content': prompt},
    ]


def call_glm():
    started = time.perf_counter()
    response = ZhipuAI(api_key=os.environ['ZHIPUAI_KEY']).chat.completions.create(
        model=os.getenv('ZHIPUAI_MODEL', 'glm-4.7-flash'),
        messages=messages(),
        temperature=0.1,
        max_tokens=4096,
    )
    return response.choices[0].message.content, time.perf_counter() - started


def call_deepseek():
    started = time.perf_counter()
    response = requests.post(
        os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com').rstrip('/') + '/chat/completions',
        headers={
            'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY'],
            'Content-Type': 'application/json',
        },
        json={
            'model': os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-flash'),
            'messages': messages(),
            'temperature': 0.1,
            'max_tokens': 1600,
            'stream': False,
            'thinking': {'type': 'disabled'},
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content'], time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('provider', choices=('glm', 'deepseek'))
    args = parser.parse_args()
    load_dotenv('.env', override=True)
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        os.environ.pop(name, None)

    try:
        content, elapsed = call_glm() if args.provider == 'glm' else call_deepseek()
        try:
            parsed = json.loads(content)
            valid_json = isinstance(parsed, dict)
        except json.JSONDecodeError:
            valid_json = False
        print(json.dumps({
            'provider': args.provider,
            'ok': True,
            'elapsed_seconds': round(elapsed, 2),
            'valid_json': valid_json,
            'content': content,
        }, ensure_ascii=True, indent=2))
    except Exception as exc:
        details = ''
        response = getattr(exc, 'response', None)
        if response is not None:
            try:
                details = ((response.json().get('error') or {}).get('message') or '')[:300]
            except Exception:
                pass
        print(json.dumps({
            'provider': args.provider,
            'ok': False,
            'error_type': type(exc).__name__,
            'details': details,
        }, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
