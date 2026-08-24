import json
import re
import asyncio
import time
import aiohttp
import requests # For synchronous HTTP requests in Baidu/Tianditu POI searches
from abc import ABC, abstractmethod
from flask import current_app

from ..utils import geo_transforms
from ..utils.api_managers import APIKeyManager, baidu_limiter
from ..utils.address_processing import extract_province_city, calculate_unified_confidence


class TiandituDiagnosticError(Exception):
    """A sanitized Tianditu failure that is safe to write to application logs."""

    def __init__(self, error_code, **details):
        super().__init__(error_code)
        self.error_code = error_code
        self.details = {
            key: value for key, value in details.items()
            if value is not None and value != ''
        }

# --- Base Class for Searchers ---

class BaseSearcher(ABC):
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.key_manager = None
        self.source_name = ""

    @abstractmethod
    async def search(self, keyword: str):
        pass

    def _get_key(self):
        """Gets the next available API key."""
        if self.key_manager:
            key, _key_type = self.key_manager.get_next_key(self.user_id)
            return key
        raise ValueError("APIKeyManager not initialized for this searcher.")

# --- Amap Searcher ---

class AmapSearcher(BaseSearcher):
    def __init__(self, user_id=None):
        super().__init__(user_id)
        self.source_name = "amap"
        amap_key = current_app.config.get('AMAP_KEY')
        self.key_manager = APIKeyManager('amap', default_key=amap_key)

    async def search(self, keyword: str, city_limit: str = '', retry_count: int = 3):
        url = 'https://restapi.amap.com/v3/place/text'
        api_key = self._get_key()
        if not api_key:
            return {'error': 'No available Amap API key.'}
        params = {
            'key': api_key,
            'keywords': keyword,
            'offset': 20,
            'page': 1,
            'extensions': 'all'
        }
        if city_limit:
            params['city'] = city_limit

        current_app.logger.debug("调用高德 POI 搜索，关键词长度=%s", len(keyword))

        for attempt in range(retry_count):
            try:
                # amap_limiter.acquire() will be called from geocoding.py if needed, not directly here to avoid circular dependency for now
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=10) as response:
                        if response.status != 200:
                            current_app.logger.warning("高德 POI 请求返回 HTTP %s", response.status)
                            if attempt == retry_count - 1:
                                return {'error': f"Amap API HTTP Error: {response.status}"}
                            await asyncio.sleep(1)
                            continue
                        
                        data = await response.json()
                        
                        if data.get('status') == '1':
                            # 成功响应，检查是否有POI结果
                            pois_list = data.get('pois', [])
                            if pois_list:
                                pois = self._process_amap_results(pois_list, keyword)
                                return {'pois': pois}
                            else:
                                # 成功但无结果，这是正常情况，不是错误
                                current_app.logger.debug("高德 POI 请求成功但没有候选")
                                return {'pois': []}
                        else:
                            error_msg = data.get('info', '未知错误')
                            infocode = str(data.get('infocode') or '')
                            current_app.logger.warning("高德 POI API 返回错误码 %s", infocode)
                            if attempt == retry_count - 1:
                                return {'error': error_msg}
                            if infocode in {'10001', '10002', '10003', '10013'}:
                                self.key_manager.report_failure(api_key, 'invalid')
                                return {'error': error_msg}
            except aiohttp.ClientError:
                current_app.logger.warning("高德 POI 请求失败（第 %s 次）", attempt + 1)
                if attempt == retry_count - 1:
                    return {'error': "Amap API request failed"}
            except asyncio.TimeoutError:
                if attempt == retry_count - 1:
                    return {'error': f"Amap API request timeout (attempt {attempt + 1})"}
            except Exception:
                current_app.logger.exception("高德 POI 请求发生未知异常")
                if attempt == retry_count - 1:
                    return {'error': "Amap API request failed"}
            
            if attempt < retry_count - 1:
                await asyncio.sleep(1)
            
        return {'error': "Amap API request failed"}

    def _process_amap_results(self, pois_data, original_keyword: str):
        results = []
        for poi in pois_data:
            location_str = poi.get('location')
            if not location_str:
                print(f"    警告: POI '{poi.get('name')}' 缺少location信息，跳过。")
                continue
            
            try:
                lng_gcj02, lat_gcj02 = map(float, location_str.split(','))
                transformed_lng_wgs84, transformed_lat_wgs84 = geo_transforms.coordinate_transform(lng_gcj02, lat_gcj02, 'GCJ02', 'WGS84')
                
                # --- 置信度计算 ---
                # 在这里调用统一的置信度计算函数
                confidence = calculate_unified_confidence(
                    original_address=original_keyword,
                    candidate_data=poi,
                    mode='poi'
                )
                current_app.logger.debug(f"[POI_SERVICE_DEBUG] POI: '{poi.get('name')}', calculated confidence: {confidence:.3f}")
                
                results.append({
                    'name': poi.get('name', ''),
                    'address': poi.get('address', ''),
                    'pname': poi.get('pname', ''),
                    'cityname': poi.get('cityname', ''),
                    'adname': poi.get('adname', ''),
                    'latitude_gcj02': lat_gcj02,
                    'longitude_gcj02': lng_gcj02,
                    'latitude_wgs84': transformed_lat_wgs84,
                    'longitude_wgs84': transformed_lng_wgs84,
                    'type': poi.get('type', ''),
                    'tel': poi.get('tel', ''),
                    'source': 'amap_poi',
                    'source_api': 'amap_poi',
                    'source_display_name': '高德地图',
                    'confidence': confidence # 将置信度添加到结果中
                })
            except (ValueError, TypeError):
                print(f"    警告: POI '{poi.get('name')}' 的location格式无效 ('{location_str}')，跳过。")
                continue
        return results

# --- Baidu Searcher (Sync but wrapped) ---

class BaiduSearcher(BaseSearcher):
    def __init__(self, user_id=None):
        super().__init__(user_id)
        self.source_name = "baidu"
        # Get config values during initialization to avoid app context issues
        self.baidu_key = current_app.config.get('BAIDU_KEY')
        self.key_manager = APIKeyManager('baidu', default_key=self.baidu_key)

    async def search(self, keyword: str):
        # Wrap the synchronous search in an async method with Flask app context
        loop = asyncio.get_event_loop()
        try:
            flask_app = current_app._get_current_object()
            pois = await loop.run_in_executor(None, lambda: self._sync_search_with_context(flask_app, keyword))
            return {'pois': pois}
        except Exception:
            current_app.logger.warning("百度 POI 搜索请求失败")
            return {'error': "Baidu POI search request failed"}

    def _sync_search_with_context(self, app, keyword):
        with app.app_context():
            return self._sync_search(keyword)

    def _sync_search(self, keyword):
        from ..utils.address_processing import extract_province_city
        province, city = extract_province_city(keyword)
        region = city if city else province or "全国"
        
        url = "https://api.map.baidu.com/place/v2/search"
        api_key, _key_type = self.key_manager.get_next_key(self.user_id)
        params = {
            "ak": api_key, "query": keyword, "region": region,
            "output": "json", "scope": 2, "page_size": 20, "ret_coordtype": "bd09ll"
        }
        
        current_app.logger.debug("调用百度 POI 搜索，关键词长度=%s", len(keyword))
        
        response = requests.get(url, params=params, timeout=10)
        current_app.logger.debug("百度 POI 请求返回 HTTP %s", response.status_code)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == 0 and data.get("results"):
            return self._process_baidu_results(data["results"], keyword)
        return []

    def _process_baidu_results(self, results_data, original_keyword: str):
        results = []
        for poi in results_data:
            if 'location' not in poi: continue
            wgs84 = geo_transforms.bd09_to_wgs84(poi['location']['lng'], poi['location']['lat'])
            gcj02 = geo_transforms.wgs84_to_gcj02(wgs84[0], wgs84[1])
            # 统一置信度计算需要POI字段对齐：pname/cityname/adname
            candidate_for_conf = {
                'name': poi.get('name', ''),
                'address': poi.get('address', ''),
                'pname': poi.get('province', ''),
                'cityname': poi.get('city', ''),
                'adname': poi.get('area', '') or poi.get('district', '')
            }
            confidence = calculate_unified_confidence(
                original_address=original_keyword,
                candidate_data=candidate_for_conf,
                mode='poi'
            )
            results.append({
                'name': poi.get('name', ''),
                'address': poi.get('address', ''),
                'pname': poi.get('province', ''),
                'cityname': poi.get('city', ''),
                'adname': poi.get('area', '') or poi.get('district', ''),
                'longitude_wgs84': wgs84[0],
                'latitude_wgs84': wgs84[1],
                'longitude_gcj02': gcj02[0],
                'latitude_gcj02': gcj02[1],
                'source': 'baidu_poi',
                'source_api': 'baidu_poi',
                'source_display_name': '百度地图',
                'confidence': confidence
            })
        return results

# --- Tianditu Searcher (Sync but wrapped) ---
class TiandituSearcher(BaseSearcher):
    def __init__(self, user_id=None):
        super().__init__(user_id)
        self.source_name = "tianditu"
        # Get config values during initialization to avoid app context issues
        self.tianditu_key = current_app.config.get('TIANDITU_KEY')
        self.key_manager = APIKeyManager('tianditu', default_key=self.tianditu_key)

    async def search(self, keyword: str):
        loop = asyncio.get_event_loop()
        started_at = time.perf_counter()
        try:
            flask_app = current_app._get_current_object()
            pois = await loop.run_in_executor(None, lambda: self._sync_search_with_context(flask_app, keyword))
            return {'pois': pois}
        except TiandituDiagnosticError as exc:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)
            details = '; '.join(
                f'{key}={value}' for key, value in sorted(exc.details.items())
            )
            detail_suffix = f'; {details}' if details else ''
            current_app.logger.error(
                "[TDT_POI][%s] 天地图 POI 请求失败; elapsed_ms=%04d%s",
                exc.error_code,
                elapsed_ms,
                detail_suffix,
            )
            return {
                'error': "Tianditu POI search request failed",
                'error_code': exc.error_code,
            }
        except Exception as exc:
            # Never log the exception text here. requests exceptions can contain
            # the complete URL, including the `tk` API key.
            elapsed_ms = round((time.perf_counter() - started_at) * 1000)
            current_app.logger.error(
                "[TDT_POI][TDT_INTERNAL_ERROR] 天地图 POI 发生未知异常; "
                "elapsed_ms=%04d; exception_type=%s",
                elapsed_ms,
                type(exc).__name__,
            )
            return {
                'error': "Tianditu POI search request failed",
                'error_code': 'TDT_INTERNAL_ERROR',
            }

    def _sync_search_with_context(self, app, keyword):
        with app.app_context():
            return self._sync_search(keyword)

    def _sync_search(self, keyword):
        url = "https://api.tianditu.gov.cn/v2/search"
        
        # 使用行政区划区域搜索（queryType=12），并尽量设置 specify 以提高召回的行政区字段
        # from ..utils.address_processing import extract_province_city
        # province, city = extract_province_city(keyword)
        
        # 修正：直接在此处使用 jionlp 解析关键词中的省市信息
        try:
            import jionlp as jio
            parsed_loc = jio.parse_location(keyword)
            province = parsed_loc.get('province', '')
            city = parsed_loc.get('city', '')
        except Exception:
            province, city = "", ""

        # 额外从关键词中粗略提取可能的行政区（省/市/区/县）作为 specify 兜底
        def _infer_admin_from_text(text: str) -> str:
            if not isinstance(text, str):
                return ''
            m = re.search(r'([\u4e00-\u9fa5]{2,}(?:省|市|区|县))', text)
            return m.group(1) if m else ''
        
        admin_specify = city or province or _infer_admin_from_text(keyword)

        # 修正：根据官方文档，queryType=1/7（普通/地名搜索）时，level 和 mapBound 均为必填
        # 因此，不再使用 queryType=12，而是统一使用 queryType=1，并按需提供 specify
        post_data = {
            "keyWord": str(keyword),
            "queryType": "1", # 统一使用最通用的关键字搜索
            "count": "20",
            "start": "0"
        }

        if admin_specify:
            current_app.logger.info(f"[TDT_SEARCH] 使用 specify='{admin_specify}' 进行区域限定搜索")
            post_data["specify"] = admin_specify
            # 区域搜索时，可以使用一个较精细的默认级别
            post_data["level"] = "10" 
            # 修正：即使是区域搜索，mapBound 也是必填项。我们提供一个足够大的默认值。
            post_data["mapBound"] = "73,3,136,54"
        else:
            current_app.logger.info("[TDT_SEARCH] 未找到行政区, 使用中国范围进行全国搜索")
            # 全国搜索时，使用一个较宏观的级别和全国范围的Bound
            post_data["level"] = "18"
            post_data["mapBound"] = "73,3,136,54" # 中国大致范围 (minX,minY,maxX,maxY)

        # 不使用ensure_ascii=False，保持默认行为；添加 show=2 以返回更详细行政区字段
        api_key, _key_type = self.key_manager.get_next_key(self.user_id)
        params = {"postStr": json.dumps(post_data), "type": "query", "tk": api_key, "show": "2"}

        current_app.logger.debug("调用天地图 POI 搜索，关键词长度=%s", len(keyword))
        
        try:
            response = requests.get(url, params=params, timeout=10)
        except requests.Timeout as exc:
            raise TiandituDiagnosticError(
                'TDT_TIMEOUT',
                exception_type=type(exc).__name__,
            ) from None
        except requests.RequestException as exc:
            raise TiandituDiagnosticError(
                'TDT_NETWORK_ERROR',
                exception_type=type(exc).__name__,
            ) from None

        if response.status_code != 200:
            raise TiandituDiagnosticError(
                'TDT_HTTP_ERROR',
                http_status=response.status_code,
                content_type=response.headers.get('Content-Type', '').split(';', 1)[0],
            )

        try:
            data = response.json()
        except (ValueError, requests.exceptions.InvalidJSONError):
            raise TiandituDiagnosticError(
                'TDT_INVALID_JSON',
                http_status=response.status_code,
                content_type=response.headers.get('Content-Type', '').split(';', 1)[0],
            ) from None

        if not isinstance(data, dict):
            raise TiandituDiagnosticError(
                'TDT_INVALID_PAYLOAD',
                payload_type=type(data).__name__,
            )

        provider_status = data.get('status')
        if isinstance(provider_status, dict):
            provider_code = str(provider_status.get('infocode') or '')
            if provider_code and provider_code != '1000':
                raise TiandituDiagnosticError(
                    'TDT_API_ERROR',
                    provider_code=provider_code[:32],
                )
        
        # 根据天地图官方文档解析响应
        result_type = data.get("resultType")
        count = data.get("count", 0)
        
        current_app.logger.debug("天地图 POI 响应类型=%s, 数量=%s", result_type, count)
        
        if result_type == 1:
            # resultType=1: 普通POI，解析pois数组
            pois_data = data.get("pois", [])
            if pois_data:
                return self._process_tianditu_results(pois_data, keyword, province, city)
            else:
                print("天地图resultType=1但pois为空")
                return []
        elif result_type == 2:
            print("天地图返回统计信息(resultType=2)，无POI数据")
            return []
        elif result_type == 3:
            print("天地图返回行政区信息(resultType=3)，无POI数据")
            return []
        elif result_type == 4:
            print("天地图返回搜索建议(resultType=4)，无POI数据")
            return []
        elif result_type == 5:
            print("天地图返回线路信息(resultType=5)，无POI数据")
            return []
        else:
            print(f"天地图返回未知类型(resultType={result_type})")
            return []
        
    def _process_tianditu_results(self, pois_data, original_keyword: str, keyword_province: str = "", keyword_city: str = ""):
        results = []
        for poi in pois_data:
            lonlat = poi.get("lonlat")
            if not lonlat: continue
            try:
                # 天地图官方API返回的是CGCS2000坐标系，这在大多数场景下等同于WGS-84。
                # 因此，我们直接将API返回的坐标视为WGS-84坐标。
                wgs_lng, wgs_lat = map(float, lonlat.split(','))
                
                # 为了与应用内其他使用GCJ-02坐标的服务（如高德地图）保持一致性，
                # 我们需要从WGS-84坐标转换生成一份GCJ-02坐标。
                gcj_lng, gcj_lat = geo_transforms.wgs84_to_gcj02(wgs_lng, wgs_lat)
                
                # 改进地址处理：如果address只是省市区信息，使用name作为主要地址
                address = poi.get('address', '')
                name = poi.get('name', '')
                
                # 如果address只包含省市区，没有具体地址，则使用name作为详细地址
                if address and name and (address.count('区') > 0 or address.count('市') > 0):
                    # address是行政区划，name是具体地点名
                    full_address = f"{address}{name}"
                else:
                    full_address = address or name
                # 天地图行政区名：优先 county；其次 area/district/adminName
                adname = poi.get('county') or poi.get('area') or poi.get('district') or poi.get('adminName', '')
                
                # 优先使用API返回的省市信息；如果缺失，则使用从关键词解析出的上下文信息
                pname = poi.get('province', '') or keyword_province
                cityname = poi.get('city', '') or keyword_city

                # 规范化：去除 adname 中冗余的省/市前缀，并尽量截取到区/县/旗级别
                def _normalize_adname(admin_name: str, province: str, city: str) -> str:
                    if not isinstance(admin_name, str) or admin_name == '':
                        return admin_name
                    s = admin_name
                    for prefix in [province or '', city or '']:
                        if prefix and s.startswith(prefix):
                            s = s[len(prefix):]
                    m = re.search(r'([\u4e00-\u9fa5]{2,}(?:区|县|旗))', s)
                    if m:
                        return m.group(1)
                    return s

                adname = _normalize_adname(adname, pname, cityname)

                candidate_for_conf = {
                    'name': name,
                    'address': full_address,
                    'pname': pname,
                    'cityname': cityname,
                    'adname': adname
                }
                confidence = calculate_unified_confidence(
                    original_address=original_keyword,
                    candidate_data=candidate_for_conf,
                    mode='poi'
                )
                results.append({
                    'name': name,
                    'address': full_address,
                    'pname': pname,
                    'cityname': cityname,
                    'adname': adname,
                    'longitude_wgs84': wgs_lng, 
                    'latitude_wgs84': wgs_lat,
                    'longitude_gcj02': gcj_lng, 
                    'latitude_gcj02': gcj_lat,
                    'source': 'tianditu_poi',
                    'source_api': 'tianditu_poi',
                    'source_display_name': '天地图',
                    'confidence': confidence
                })
            except (ValueError, TypeError):
                continue
        return results

# --- Factory Function ---

_searcher_classes = {
    "amap": AmapSearcher,
    "baidu": BaiduSearcher,
    "tianditu": TiandituSearcher,
}

def get_searcher(source: str, user_id=None) -> BaseSearcher:
    """
    Factory function to get the appropriate searcher instance.
    """
    searcher_class = _searcher_classes.get(source.lower())
    if searcher_class:
        return searcher_class(user_id)
    return None
