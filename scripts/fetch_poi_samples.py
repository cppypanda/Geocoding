import os
import json
import pathlib
import sys
from urllib.parse import quote

import requests


def ensure_dir(path: str) -> None:
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)


def fetch_amap(keyword: str, out_path: str, api_key: str) -> dict:
    url = "https://restapi.amap.com/v3/place/text"
    params = {
        "key": api_key,
        "keywords": keyword,
        "offset": 5,
        "page": 1,
        "extensions": "all",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def fetch_baidu(keyword: str, out_path: str, api_key: str, region: str = "全国") -> dict:
    url = "https://api.map.baidu.com/place/v2/search"
    params = {
        "ak": api_key,
        "query": keyword,
        "region": region,
        "output": "json",
        "scope": 2,
        "page_size": 5,
        "page_num": 0,
        "ret_coordtype": "bd09ll",
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def fetch_tianditu(keyword: str, out_path: str, api_key: str) -> dict:
    url = "http://api.tianditu.gov.cn/v2/search"
    post_str_data = {
        "keyWord": str(keyword),
        "queryType": str(7),
        "count": str(5),
        "start": str(0),
        "level": str(12),
        "mapBound": "73,18,135,54",
    }
    params = {
        "postStr": json.dumps(post_str_data),
        "type": "query",
        "tk": api_key,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


def main():
    keyword = os.environ.get("POI_SAMPLE_KEYWORD", "成都市高新区天府软件园")
    out_dir = os.path.join("docs", "poi_samples")
    ensure_dir(out_dir)

    # Prefer reading AMAP key from app config; fall back to env if import fails
    amap_key = None
    try:
        from app.config import Config  # type: ignore
        amap_key = getattr(Config, "AMAP_KEY", None)
    except Exception:
        amap_key = None
    if not amap_key:
        amap_key = os.environ.get("AMAP_KEY")

    if not amap_key:
        print("AMAP_KEY 未配置，跳过高德样例抓取", file=sys.stderr)
    else:
        out_path = os.path.join(out_dir, "amap_poi.json")
        data = fetch_amap(keyword, out_path, amap_key)
        print(f"amap_ok:{out_path}")

    # Optional: Baidu
    baidu_key = os.environ.get("BAIDU_KEY")
    if baidu_key:
        out_path = os.path.join(out_dir, "baidu_poi.json")
        try:
            fetch_baidu(keyword, out_path, baidu_key)
            print(f"baidu_ok:{out_path}")
        except Exception as e:
            print(f"baidu_fail:{e}", file=sys.stderr)
    else:
        print("BAIDU_KEY 未配置，跳过百度样例抓取", file=sys.stderr)

    # Optional: Tianditu
    tdt_key = os.environ.get("TIANDITU_KEY")
    if tdt_key:
        out_path = os.path.join(out_dir, "tianditu_poi.json")
        try:
            fetch_tianditu(keyword, out_path, tdt_key)
            print(f"tianditu_ok:{out_path}")
        except Exception as e:
            print(f"tianditu_fail:{e}", file=sys.stderr)
    else:
        print("TIANDITU_KEY 未配置，跳过天地图样例抓取", file=sys.stderr)


if __name__ == "__main__":
    main()


