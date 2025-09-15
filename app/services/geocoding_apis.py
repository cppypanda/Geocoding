import json
import asyncio
import aiohttp
import traceback
import abc

from flask import current_app
from ..utils import geo_transforms, address_processing
from ..utils.api_managers import baidu_limiter, APIKeyManager, APIRateLimiter, REASON_INVALID, REASON_QUOTA_EXCEEDED, REASON_RATE_LIMITED, REASON_OTHER
from ..exceptions import RateLimitError, ThirdPartyAPIError, InvalidApiKeyError

# --- Refactored Geocoder Service Structure ---

class BaseGeocoder(abc.ABC):
    """Abstract base class for all geocoders."""
    
    def __init__(self, rate_limiter: APIRateLimiter):
        self.rate_limiter = rate_limiter
        # The key_manager should be initialized in the subclass
        self.key_manager = None

    async def _make_request(self, url, params, method='GET', service_name=''):
        """Makes an asynchronous HTTP request, handling rate limiting and basic errors."""
        if not self.key_manager:
            raise ValueError("APIKeyManager not initialized for this geocoder.")
            
        current_key = params.get('key') # Assume key is in params
        if not current_key:
            raise ValueError("No API key provided in request params.")

        await self.rate_limiter.acquire()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, params=params) as response:
                    response.raise_for_status()
                    # Report success after a successful request
                    self.key_manager.report_success(current_key)
                    return await response.json(content_type=None)
        except aiohttp.ClientError as e:
            print(f"Aiohttp client error for {self.__class__.__name__}: {e}")
            # Here you might want to parse the error to determine the reason
            self.key_manager.report_failure(current_key, REASON_RATE_LIMITED) # Example reason
            return {'error': f'API request failed: {e}'}
        except Exception as e:
            print(f"An unexpected error occurred in {self.__class__.__name__}: {e}")
            traceback.print_exc()
            self.key_manager.report_failure(current_key, REASON_OTHER) # Example reason
            return {'error': f'An unexpected error occurred: {e}'}

    @abc.abstractmethod
    async def geocode(self, address: str, parsed_original_address: dict = None, **kwargs):
        """Geocode an address to coordinates."""
        pass

    def _standardize_result(self, raw_data, current_key):
        raise NotImplementedError

class AmapGeocoder(BaseGeocoder):
    """Geocoder for Amap (Gaode)."""
    
    def __init__(self, key, user_id=None):
        super().__init__(APIRateLimiter(3))
        self.key_manager = APIKeyManager('amap', default_key=key)
        self.user_id = user_id
        self.geocode_url = 'https://restapi.amap.com/v3/geocode/geo'

    def _standardize_result(self, data, current_key):
        if data['status'] == '1' and data.get('geocodes'):
            first_result = data['geocodes'][0]
            location_gcj02 = first_result['location'].split(',')
            lng_gcj02 = float(location_gcj02[0])
            lat_gcj02 = float(location_gcj02[1])
            
            lng_wgs84, lat_wgs84 = geo_transforms.coordinate_transform(lng_gcj02, lat_gcj02, 'GCJ02', 'WGS84')
            
            return {
                'longitude_gcj02': lng_gcj02, 'latitude_gcj02': lat_gcj02,
                'longitude_wgs84': lng_wgs84, 'latitude_wgs84': lat_wgs84,
                'formatted_address': first_result.get('formatted_address', ''),
                'province': first_result.get('province', ''),
                'city': first_result.get('city', ''),
                'district': first_result.get('district', ''),
                'level': first_result.get('level', ''),
                'adcode': first_result.get('adcode', ''),
                'source': 'amap'
            }
        else:
            error_msg = data.get('info', 'Unknown Amap API error')
            # 根据错误信息判断失败原因
            if "INVALID_USER_KEY" in error_msg or "KEY_INVALID" in error_msg:
                 self.key_manager.report_failure(current_key, REASON_INVALID)
            elif "DAILY_QUERY_OVER_LIMIT" in error_msg:
                 self.key_manager.report_failure(current_key, REASON_QUOTA_EXCEEDED)
            else:
                 self.key_manager.report_failure(current_key) # REASON_OTHER
            return {'error': f'Geocoding failed: {error_msg}'}
            
    async def geocode(self, address: str, parsed_original_address: dict = None, **kwargs):
        if not parsed_original_address:
            current_app.logger.error("AmapGeocoder.geocode called without a pre-parsed original address.")
            return {'error': 'Internal Error: Amap geocoding requires a pre-parsed original address.'}

        current_key, key_type = self.key_manager.get_next_key(self.user_id)
        if not current_key:
             return {'error': 'No available Amap API key.'}

        params = { 'key': current_key, 'address': address, 'output': 'json' }
        if 'city_code' in kwargs:
            params['city'] = kwargs['city_code']
        
        raw_data = await self._make_request(self.geocode_url, params, service_name='amap')
        if 'error' in raw_data:
            return raw_data
            
        # SOP 5.1: 内部选优
        geocodes = raw_data.get('geocodes', [])
        if not geocodes:
            return {'error': 'Amap returned no geocode results.'}

        standardized_results = []
        for candidate_raw in geocodes:
            # Wrap each candidate to be processed by the existing _standardize_result function
            temp_data_for_std = {'status': '1', 'geocodes': [candidate_raw]}
            standardized_candidate = self._standardize_result(temp_data_for_std, current_key)
            if 'error' in standardized_candidate:
                continue

            # Calculate confidence using the unified algorithm
            confidence = address_processing.calculate_unified_confidence(
                original_address=address,
                candidate_data=standardized_candidate,
                parsed_original=parsed_original_address,
                mode='geocoding'
            )
            
            standardized_candidate['confidence'] = confidence
            standardized_results.append(standardized_candidate)

        if not standardized_results:
            return {'error': 'Amap geocoding failed to find any valid candidate.'}

        # SOP 5.1 内部选优: 无论有几个结果，始终返回置信度最高的单个结果
        current_app.logger.debug(f"高德返回 {len(geocodes)} 个候选结果，进行内部选优。")
        for r_idx, r in enumerate(standardized_results):
            current_app.logger.debug(f"  候选 {r_idx + 1}: {r.get('formatted_address', 'N/A')}, 置信度: {r.get('confidence', 'N/A')}")
        
        best_result = max(standardized_results, key=lambda x: x.get('confidence', 0.0))
        current_app.logger.debug(f"高德内部选优 - 最佳结果: {best_result.get('formatted_address', 'N/A')}，置信度: {best_result.get('confidence', 'N/A')}")
        
        # 关键修复：确保返回的是单个字典对象，而不是列表
        return best_result

    async def reverse_geocode(self, lat_wgs84: float, lng_wgs84: float, **kwargs) -> dict:
        """
        Performs reverse geocoding for Amap.
        It takes WGS84 coordinates, sends them to Amap API, and returns a standardized address.
        """
        current_key, key_type = self.key_manager.get_next_key(self.user_id)
        if not current_key:
            return {'error': 'No available Amap API key.'}

        # Amap reverse geocoding requires lat,lng format.
        location_str = f"{lng_wgs84},{lat_wgs84}"

        params = {
            "key": current_key,
            "output": "json",
            "location": location_str,
            "extensions": "all"  # Get detailed address components
        }
        
        # Use the reverse geocoding endpoint
        reverse_url = 'https://restapi.amap.com/v3/geocode/regeo'
        raw_data = await self._make_request(reverse_url, params, service_name='amap_reverse')

        if 'error' in raw_data:
            return raw_data
        
        # Amap status 1 is success
        if raw_data.get("status") == "1":
            result = raw_data.get("regeocode", {})
            address_component = result.get("addressComponent", {})
            return {
                'formatted_address': result.get("formatted_address", ""),
                'province': address_component.get('province', ''),
                'city': address_component.get('city', ''),
                'district': address_component.get('district', ''),
                'source': 'amap_reverse'
            }

        # Handle errors and report failure
        error_msg = raw_data.get('info', 'Unknown Amap API error')
        if "INVALID_USER_KEY" in error_msg or "KEY_INVALID" in error_msg:
            self.key_manager.report_failure(current_key, REASON_INVALID)
        elif "DAILY_QUERY_OVER_LIMIT" in error_msg:
            self.key_manager.report_failure(current_key, REASON_QUOTA_EXCEEDED)
        else:
            self.key_manager.report_failure(current_key, REASON_OTHER)
        return {'error': f'Reverse geocoding failed: {error_msg}'}

class BaiduGeocoder(BaseGeocoder):
    """Geocoder for Baidu."""

    def __init__(self, key, user_id=None):
        super().__init__(baidu_limiter)
        self.key_manager = APIKeyManager('baidu', default_key=key)
        self.user_id = user_id
        self.geocode_url = "https://api.map.baidu.com/geocoding/v3/"
        self.reverse_geocode_url = "https://api.map.baidu.com/reverse_geocoding/v3/"

    def _standardize_result(self, data, current_key):
        # Baidu status 0 is success
        if data.get("status") == 0:
            result = data.get("result", {})
            location_gcj02 = result.get("location", {})
            
            if location_gcj02 and isinstance(location_gcj02, dict):
                lng_gcj02 = location_gcj02.get('lng')
                lat_gcj02 = location_gcj02.get('lat')

                # Coordinates are already GCJ02, convert to WGS84 for storage
                wgs84_coords = geo_transforms.gcj02_to_wgs84(lng_gcj02, lat_gcj02)

                return {
                    'longitude_gcj02': lng_gcj02, 'latitude_gcj02': lat_gcj02,
                    'longitude_wgs84': wgs84_coords[0], 'latitude_wgs84': wgs84_coords[1],
                    'formatted_address': result.get("formatted_address", ""),
                    'province': result.get('addressComponent', {}).get('province', ''),
                    'city': result.get('addressComponent', {}).get('city', ''),
                    'district': result.get('addressComponent', {}).get('district', ''),
                    'level': result.get('level', ''),
                    'source': 'baidu',
                    # SOP: Carry over native scores for B-Model calculation
                    'native_confidence': result.get('confidence', 0),
                    'native_comprehension': result.get('comprehension', 0)
                }
        
        # Handle errors and report failure
        error_msg = data.get('message', 'Unknown Baidu API error')
        status_code = data.get('status')
        if status_code in [302, 301]: # Quota exceeded
            self.key_manager.report_failure(current_key, REASON_QUOTA_EXCEEDED)
        elif status_code in [401, 402]: # Invalid key
            self.key_manager.report_failure(current_key, REASON_INVALID)
        else:
            self.key_manager.report_failure(current_key, REASON_OTHER)
        return {'error': f'Geocoding failed: {error_msg} (status: {status_code})'}

    async def reverse_geocode(self, lat_wgs84: float, lng_wgs84: float, **kwargs) -> dict:
        """
        Performs reverse geocoding for Baidu.
        It takes WGS84 coordinates, sends them to Baidu API, and returns a standardized address.
        """
        current_key, key_type = self.key_manager.get_next_key(self.user_id)
        if not current_key:
            return {'error': 'No available Baidu API key.'}

        # Baidu reverse geocoding requires lat,lng format.
        location_str = f"{lat_wgs84},{lng_wgs84}"

        params = {
            "ak": current_key,
            "output": "json",
            "location": location_str,
            "coordtype": "wgs84ll",  # Specify input coordinate type
            "ret_coordtype": "gcj02ll" # Ask for GCJ02 in response for consistency
        }
        
        # _make_request 依赖 params['key'] 进行Key状态跟踪，这里补充一份镜像字段
        request_params = params.copy()
        request_params['key'] = current_key
        raw_data = await self._make_request(self.reverse_geocode_url, request_params, service_name='baidu_reverse')

        if 'error' in raw_data:
            return raw_data
        
        # Baidu status 0 is success
        if raw_data.get("status") == 0:
            result = raw_data.get("result", {})
            return {
                'formatted_address': result.get("formatted_address", ""),
                'province': result.get('addressComponent', {}).get('province', ''),
                'city': result.get('addressComponent', {}).get('city', ''),
                'district': result.get('addressComponent', {}).get('district', ''),
                'source': 'baidu_reverse'
            }

        # Handle errors and report failure
        error_msg = raw_data.get('message', 'Unknown Baidu API error')
        status_code = raw_data.get('status')
        if status_code in [302, 301]: # Quota exceeded
            self.key_manager.report_failure(current_key, REASON_QUOTA_EXCEEDED)
        elif status_code in [401, 402]: # Invalid key
            self.key_manager.report_failure(current_key, REASON_INVALID)
        else:
            self.key_manager.report_failure(current_key, REASON_OTHER)
        return {'error': f'Reverse geocoding failed: {error_msg} (status: {status_code})'}

    async def geocode(self, address: str, parsed_original_address: dict = None, **kwargs):
        current_key, key_type = self.key_manager.get_next_key(self.user_id)
        if not current_key:
            return {'error': 'No available Baidu API key.'}

        params = {
            "ak": current_key,
            "output": "json",
            "address": address,
            "ret_coordtype": "gcj02ll" # SOP 5.3: Ensure GCJ02 is returned
        }
        # The base _make_request expects 'key' in params for key management.
        request_params = params.copy()
        request_params['key'] = current_key

        raw_data = await self._make_request(self.geocode_url, request_params, service_name='baidu')
        if 'error' in raw_data:
            return raw_data
        
        standardized_result = self._standardize_result(raw_data, current_key)

        if 'error' not in standardized_result:
            standardized_result['key_type'] = key_type
            
        return standardized_result

class TiandituGeocoder(BaseGeocoder):
    """Geocoder for Tianditu."""
    
    def __init__(self, key, user_id=None):
        super().__init__(APIRateLimiter(3))
        self.key_manager = APIKeyManager('tianditu', default_key=key)
        self.user_id = user_id
        self.geocode_url = "https://api.tianditu.gov.cn/geocoder"

    def _standardize_result(self, data, current_key):
        # For Tianditu geocoding, the location data is inside the 'location' key
        if data.get("status") == "0" and data.get('location'):
            result = data.get("location", {})
            try:
                lng_wgs84 = float(result['lon'])
                lat_wgs84 = float(result['lat'])
                lng_gcj02, lat_gcj02 = geo_transforms.coordinate_transform(lng_wgs84, lat_wgs84, 'WGS84', 'GCJ02')
                
                keyword = result.get('keyWord', '')

                return {
                    'longitude_wgs84': lng_wgs84, 'latitude_wgs84': lat_wgs84,
                    'longitude_gcj02': lng_gcj02, 'latitude_gcj02': lat_gcj02,
                    'formatted_address': keyword,
                    'province': '', # Per SOP, do not parse, leave for post-processing
                    'city': '',     # Per SOP, do not parse, leave for post-processing
                    'district': '', # Per SOP, do not parse, leave for post-processing
                    'level': result.get('level', ''),
                    'source': 'tianditu',
                    # SOP: Carry over native score for B-Model calculation
                    'native_score': float(result.get('score', 0))
                }
            except (ValueError, TypeError):
                 return {'error': 'Tianditu returned malformed coordinate data.'}
        else:
            error_msg = data.get('msg', 'Unknown Tianditu API error')
            # Assuming 'status' is not '0' means error
            if 'key' in error_msg.lower() or '非法' in error_msg:
                self.key_manager.report_failure(current_key, REASON_INVALID)
            else:
                self.key_manager.report_failure(current_key, REASON_OTHER)
            return {'error': f'Geocoding failed: {error_msg} (status: {data.get("status")})'}

    async def reverse_geocode(self, lat_wgs84: float, lng_wgs84: float, **kwargs) -> dict:
        """
        Performs reverse geocoding for Tianditu.
        It takes WGS84 coordinates, sends them to the API, and returns a standardized address.
        """
        current_key, key_type = self.key_manager.get_next_key(self.user_id)
        if not current_key:
            return {'error': 'No available Tianditu API key.'}

        # 天地图逆地理编码（geocoder服务）：GET 方式，使用 postStr + type=geocode + tk
        # 按天地图官方文档要求：使用数值字段 lon/lat，顺序为 经度(lon), 纬度(lat)
        post_str_data = {
            "lon": float(lng_wgs84),
            "lat": float(lat_wgs84),
            "ver": "1"
        }

        params = {
            "postStr": json.dumps(post_str_data),
            "type": "geocode",
            "tk": current_key
        }
        # _make_request需要'key'字段进行Key管理，这里镜像一份
        request_params = params.copy()
        request_params['key'] = current_key

        raw_data = await self._make_request(self.geocode_url, request_params, service_name='tianditu_reverse')

        if 'error' in raw_data:
            return raw_data

        if raw_data.get("status") == "0":
            result = raw_data.get("result", {})
            address_comp = result.get('addressComponent', {}) or {}
            formatted = result.get("formatted_address") or ''
            if not formatted:
                # 兜底：由行政区拼接一个可读地址，避免回退到原始输入
                formatted = f"{address_comp.get('province','')}{address_comp.get('city','')}{address_comp.get('district','')}".strip()
            return {
                'formatted_address': formatted,
                'province': address_comp.get('province', ''),
                'city': address_comp.get('city', ''),
                'district': address_comp.get('district', ''),
                'source': 'tianditu_reverse'
            }

        error_msg = raw_data.get('msg', 'Unknown Tianditu API error')
        self.key_manager.report_failure(current_key, REASON_OTHER)
        return {'error': f'Reverse geocoding failed: {error_msg} (status: {raw_data.get("status")})'}

    async def geocode(self, address: str, parsed_original_address: dict = None, **kwargs):
        current_key, key_type = self.key_manager.get_next_key(self.user_id)
        if not current_key:
            return {'error': 'No available Tianditu API key.'}

        params = {
            'ds': json.dumps({"keyWord": address}),
            'tk': current_key
        }
        # The base _make_request expects 'key' in params for key management.
        request_params = params.copy()
        request_params['key'] = current_key
        
        raw_data = await self._make_request(self.geocode_url, request_params, service_name='tianditu')

        if 'error' in raw_data:
            # The error from _make_request is generic, we just pass it on.
            return raw_data
            
        standardized_result = self._standardize_result(raw_data, current_key)
        
        if 'error' not in standardized_result:
            standardized_result['key_type'] = key_type
            
        return standardized_result

# --- Geocoder Factory ---

def get_geocoder(provider_name: str, user_id: int = None) -> BaseGeocoder:
    """Factory function to get a geocoder instance."""
    if provider_name == 'amap':
        return AmapGeocoder(current_app.config['AMAP_KEY'], user_id)
    elif provider_name == 'baidu':
        return BaiduGeocoder(current_app.config['BAIDU_KEY'], user_id)
    elif provider_name == 'tianditu':
        return TiandituGeocoder(current_app.config['TIANDITU_KEY'], user_id)
    else:
        raise ValueError(f"Unknown geocoder provider: {provider_name}")


# --- Existing Code (to be refactored or removed) ---

# All the geocode_* functions below this line are deprecated and have been
# replaced by the Geocoder classes above. They are now removed. 