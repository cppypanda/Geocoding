import asyncio
import re
import json
import time
import os
from datetime import datetime
import jionlp as jio

from flask import Blueprint, request, jsonify, session, current_app, send_file
from flask_login import login_required, current_user

from ..services import geocoding_apis, poi_search, llm_service
from ..services.web_search_local import search_sogou
from ..utils import geo_transforms, decorators, api_managers, address_processing
from ..utils.log_context import request_context_var
from ..models import LocationType, User, ApiRequestLog, db, GeocodingTask, AddressLog
from ..services import user_service

geocoding_bp = Blueprint('geocoding', __name__, url_prefix='/geocode')

# 地理编码结果的内存缓存，用于"逐一校准"功能
geocoding_session_data = {} # {session_id: {address: [results]}}

def save_geocoding_result(session_id, original_address, geocoded_results):
    """保存地理编码结果到内存缓存"""
    if session_id not in geocoding_session_data:
        geocoding_session_data[session_id] = {}
    geocoding_session_data[session_id][original_address] = geocoded_results

def load_session_results(session_id, original_address):
    """从内存缓存加载地理编码结果"""
    return geocoding_session_data.get(session_id, {}).get(original_address)

def deduct_points(user_id, points_to_deduct):
    """为指定用户扣除积分（使用SQLAlchemy）。"""
    if not user_id or points_to_deduct <= 0:
        return

    try:
        user = User.query.get(user_id)
        if user:
            # 确保积分不会成为负数
            if user.points is None:
                user.points = 0
            
            if user.points >= points_to_deduct:
                user.points -= points_to_deduct
            else:
                current_app.logger.warning(f"用户 {user_id} 积分不足 (剩余 {user.points}, 需要 {points_to_deduct})，操作未执行。")
                # 可选：如果积分为0，则不扣除
                user.points = 0
            
            db.session.commit()
            current_app.logger.info(f"成功为用户 {user_id} 扣除 {points_to_deduct} 积分。剩余积分: {user.points}")
        else:
            current_app.logger.error(f"尝试扣分失败：未找到ID为 {user_id} 的用户。")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"为用户 {user_id} 扣除积分时发生数据库异常: {e}", exc_info=True)


def get_points_cost(task_name, used_user_key, token_count=0):
    """
    根据任务名称、是否使用用户Key以及消耗的Token数，计算应扣除的积分。
    这是未来实现动态计费的核心。
    """
    costs_config = current_app.config['POINTS_COST_BY_TASK']
    task_costs = costs_config.get(task_name)

    if not task_costs:
        return 2  # 如果任务未定义，返回一个安全的默认值

    # 基础费用计算
    base_cost = task_costs.get('discount') if used_user_key else task_costs.get('standard')

    # 未来扩展：动态Token费用计算
    # if 'per_token_cost' in task_costs and token_count > 0:
    #     token_cost = (token_count / 1000) * task_costs['per_token_cost']
    #     return base_cost + token_cost
    
    return base_cost

def get_daily_request_count(user_id, service_name, current_date=None):
    """获取用户当日的API请求计数 (使用SQLAlchemy)"""
    if current_date is None:
        current_date = datetime.utcnow().date()
    else:
        if isinstance(current_date, str):
            current_date = datetime.strptime(current_date, '%Y-%m-%d').date()

    log = ApiRequestLog.query.filter_by(
        user_id=user_id, 
        service_name=service_name, 
        request_date=current_date
    ).first()
    
    return log.request_count if log else 0

def increment_daily_request_count(user_id, service_name, increment_by=1, current_date=None):
    """增加用户当日的API请求计数 (使用SQLAlchemy)"""
    if current_date is None:
        current_date = datetime.utcnow().date()
    else:
        if isinstance(current_date, str):
            current_date = datetime.strptime(current_date, '%Y-%m-%d').date()

    try:
        log = ApiRequestLog.query.filter_by(
            user_id=user_id,
            service_name=service_name,
            request_date=current_date
        ).first()

        if log:
            log.request_count += increment_by
        else:
            log = ApiRequestLog(
                user_id=user_id,
                service_name=service_name,
                request_date=current_date,
                request_count=increment_by
            )
            db.session.add(log)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to increment request count for user {user_id}: {e}")

async def _perform_reverse_geocoding(winner_result, user_id, parsed_original_address: dict):
    """(SOP Step 4) Performs deferred reverse geocoding and ensures data consistency."""
    provider = winner_result.get('source')
    
    # 无论是否需要逆地理编码，都首先使用预处理的权威数据来统一省市区
    if parsed_original_address:
        winner_result['province'] = parsed_original_address.get('province', winner_result.get('province'))
        winner_result['city'] = parsed_original_address.get('city', winner_result.get('city'))
        # 只有在jionlp解析出有效区县时才覆盖，否则保留编码器返回的结果
        if parsed_original_address.get('county'):
            winner_result['district'] = parsed_original_address.get('county')

    # Amap results are rich enough, no reverse geocoding needed as per SOP.
    if provider not in ['baidu', 'tianditu']:
        return winner_result

    current_app.logger.info(f"SOP第4步：开始为源 '{provider}' 的获胜结果执行延迟逆地理编码。")
    try:
        geocoder = geocoding_apis.get_geocoder(provider, user_id)
        
        # 使用标准键名读取坐标（在坐标补全过程中已确保存在）
        lat = winner_result.get('latitude_wgs84')
        lng = winner_result.get('longitude_wgs84')

        if not lat or not lng:
            current_app.logger.warning(f"由于坐标缺失，跳过对 '{provider}' 的逆地理编码。")
            return winner_result

        reversed_info = await geocoder.reverse_geocode(lat, lng)
        
        if 'error' not in reversed_info:
            current_app.logger.info(f"成功使用 '{provider}' 完成逆地理编码，正在增强结果。")
            # Update winner_result with richer address details, but keep original coordinates.
            winner_result['formatted_address'] = reversed_info.get('formatted_address', winner_result.get('formatted_address'))
            # 再次使用预处理结果覆盖，确保一致性
            winner_result['province'] = parsed_original_address.get('province', reversed_info.get('province', winner_result.get('province')))
            winner_result['city'] = parsed_original_address.get('city', reversed_info.get('city', winner_result.get('city')))
            if parsed_original_address.get('county'):
                 winner_result['district'] = parsed_original_address.get('county', reversed_info.get('district', winner_result.get('district')))
            else:
                 winner_result['district'] = reversed_info.get('district', winner_result.get('district'))

            winner_result['source'] = f"{winner_result['source']}_re-geocoded" # e.g., 'baidu_re-geocoded'
        else:
            current_app.logger.error(f"'{provider}' 的逆地理编码返回错误: {reversed_info['error']}")

    except Exception as e:
        current_app.logger.error(f"'{provider}' 的逆地理编码过程中发生异常: {e}")
    
    return winner_result

async def _get_best_geocode_result(address, user_id, parsed_original_address: dict, log_prefix: str = "", debug: bool = False):
    """
    (SOP V3.0) Processes a single address using the full SOP cascade.
    Requires the address to be pre-completed and its parsed version.
    This function now returns both the winner and all individual API results.
    """
    token = request_context_var.set(log_prefix)
    try:
        if not parsed_original_address:
            current_app.logger.error(f"内部错误: _get_best_geocode_result 未收到 parsed_original_address 参数。地址: {address}")
            parsed_original_address = jio.parse_location(address)

        all_api_results = []
        candidate_results = []
        debug_trace = {'address': address, 'threshold': None, 'providers': [], 'winner_before_post': None, 'winner_after_post': None}
        CONFIDENCE_THRESHOLD = current_app.config.get('REQUIRED_CONFIDENCE_THRESHOLD', 0.9)
        debug_trace['threshold'] = CONFIDENCE_THRESHOLD

        # --- SOP 步骤 2: 核心瀑布流逻辑 (已修正为短路模式) ---
    
        # 2.1. 第一顺位：天地图
        current_app.logger.info("SOP第2.1步：尝试天地图...")
        try:
            geocoder_tianditu = geocoding_apis.get_geocoder('tianditu', user_id)
            result_tianditu = await geocoder_tianditu.geocode(address)
            if 'error' not in result_tianditu:
                confidence_tianditu = address_processing.calculate_confidence_B('tianditu', result_tianditu)
                result_tianditu['calculated_confidence'] = confidence_tianditu
                all_api_results.append({'api': 'tianditu', 'result': result_tianditu})
                candidate_results.append(result_tianditu)
                if debug:
                    debug_trace['providers'].append({'api': 'tianditu', 'confidence': confidence_tianditu, 'accepted_immediately': confidence_tianditu >= CONFIDENCE_THRESHOLD, 'summary': result_tianditu.get('formatted_address')})
                current_app.logger.info(f"天地图处理完成，坐标: ({result_tianditu.get('longitude_gcj02')}, {result_tianditu.get('latitude_gcj02')}), Level: '{result_tianditu.get('level', 'N/A')}', 置信度: {confidence_tianditu:.2%}")
                if confidence_tianditu >= CONFIDENCE_THRESHOLD:
                    current_app.logger.info(f"天地图结果满足阈值，决策完成。")
                    winner = result_tianditu
                    # 短路：直接进入后续处理
                    debug_trace['winner_before_post'] = {'api': winner.get('source'), 'confidence': winner.get('calculated_confidence')}
                    processed_winner = await _post_process_winner(winner, user_id, parsed_original_address)
                    debug_trace['winner_after_post'] = {'api': processed_winner.get('source'), 'formatted_address': processed_winner.get('formatted_address')}
                    payload = {'winner': processed_winner, 'all_results': all_api_results}
                    if debug:
                        payload['debug'] = debug_trace
                    return payload
            else:
                current_app.logger.warning(f"天地图地理编码失败: {result_tianditu.get('error')}")
        except Exception as e:
            current_app.logger.error(f"天地图地理编码过程中发生异常: {e}")

        # 2.2. 第二顺位：高德地图
        current_app.logger.info("SOP第2.2步：尝试高德地图...")
        try:
            geocoder_amap = geocoding_apis.get_geocoder('amap', user_id)
            result_amap = await geocoder_amap.geocode(address, parsed_original_address)
            if 'error' not in result_amap:
                confidence_amap = result_amap.get('confidence', 0.0)
                result_amap['calculated_confidence'] = confidence_amap
                all_api_results.append({'api': 'amap', 'result': result_amap})
                candidate_results.append(result_amap)
                if debug:
                    debug_trace['providers'].append({'api': 'amap', 'confidence': confidence_amap, 'accepted_immediately': confidence_amap >= CONFIDENCE_THRESHOLD, 'summary': result_amap.get('formatted_address')})
                current_app.logger.info(f"高德地图处理完成，地址: '{result_amap.get('formatted_address', 'N/A')}', 置信度: {confidence_amap:.2%}")
                if confidence_amap >= CONFIDENCE_THRESHOLD:
                    current_app.logger.info(f"高德地图结果满足阈值，决策完成。")
                    winner = result_amap
                    # 短路：直接进入后续处理
                    debug_trace['winner_before_post'] = {'api': winner.get('source'), 'confidence': winner.get('calculated_confidence')}
                    processed_winner = await _post_process_winner(winner, user_id, parsed_original_address)
                    debug_trace['winner_after_post'] = {'api': processed_winner.get('source'), 'formatted_address': processed_winner.get('formatted_address')}
                    payload = {'winner': processed_winner, 'all_results': all_api_results}
                    if debug:
                        payload['debug'] = debug_trace
                    return payload
            else:
                current_app.logger.warning(f"高德地图地理编码失败: {result_amap.get('error')}")
        except Exception as e:
            current_app.logger.error(f"高德地图地理编码过程中发生异常: {e}")

        # 2.3. 第三顺位：百度地图
        current_app.logger.info("SOP第2.3步：尝试百度地图...")
        try:
            geocoder_baidu = geocoding_apis.get_geocoder('baidu', user_id)
            result_baidu = await geocoder_baidu.geocode(address)
            if 'error' not in result_baidu:
                confidence_baidu = address_processing.calculate_confidence_B('baidu', result_baidu)
                result_baidu['calculated_confidence'] = confidence_baidu
                all_api_results.append({'api': 'baidu', 'result': result_baidu})
                candidate_results.append(result_baidu)
                if debug:
                    debug_trace['providers'].append({'api': 'baidu', 'confidence': confidence_baidu, 'accepted_immediately': confidence_baidu >= CONFIDENCE_THRESHOLD, 'summary': result_baidu.get('formatted_address')})
                current_app.logger.info(f"百度地图处理完成，坐标: ({result_baidu.get('longitude_gcj02')}, {result_baidu.get('latitude_gcj02')}), Level: '{result_baidu.get('level', 'N/A')}', 置信度: {confidence_baidu:.2%}")
                # 这是最后一个，无需检查阈值短路
            else:
                current_app.logger.warning(f"百度地图地理编码失败: {result_baidu.get('error')}")
        except Exception as e:
            current_app.logger.error(f"百度地图地理编码过程中发生异常: {e}")

        # --- SOP 步骤 4: 最终选择阶段 (Fallback) ---
        if not candidate_results:
            current_app.logger.error(f"所有地理编码服务对地址 '{address}' 的处理均失败。")
            return {'winner': {'error': '所有地理编码服务均失败。'}, 'all_results': all_api_results}

        # 如果没有任何服务商满足阈值，则从所有候选者中选择分数最高的
        candidate_results.sort(key=lambda x: x.get('calculated_confidence', 0), reverse=True)
        winner = candidate_results[0]
        if debug:
            debug_trace['winner_before_post'] = {'api': winner.get('source'), 'confidence': winner.get('calculated_confidence')}
        current_app.logger.info(f"决策：无服务商满足阈值。选择置信度最高的候选者：'{winner['source']}'，置信度为 {winner.get('calculated_confidence', 0):.2%}.")
    
        # 对最终的"优胜者"进行后处理
        processed_winner = await _post_process_winner(winner, user_id, parsed_original_address)
        if debug:
            debug_trace['winner_after_post'] = {'api': processed_winner.get('source'), 'formatted_address': processed_winner.get('formatted_address')}
        payload = {'winner': processed_winner, 'all_results': all_api_results}
        if debug:
            payload['debug'] = debug_trace
        return payload

    finally:
        request_context_var.reset(token)

async def _post_process_winner(winner, user_id, parsed_original_address):
    """
    一个辅助函数，包含对获胜者的所有后处理步骤（坐标统一、逆地理编码等）。
    """
    # --- 坐标统一 ---
    # 确保在进行任何进一步处理（如逆地理编码）之前，WGS84和GCJ02坐标都存在。
    has_wgs = 'longitude_wgs84' in winner and winner['longitude_wgs84']
    has_gcj = 'longitude_gcj02' in winner and winner['longitude_gcj02']

    try:
        if not has_wgs and has_gcj:
            lng_wgs, lat_wgs = geo_transforms.gcj02_to_wgs84(winner['longitude_gcj02'], winner['latitude_gcj02'])
            winner['longitude_wgs84'] = lng_wgs
            winner['latitude_wgs84'] = lat_wgs
            current_app.logger.debug(f"坐标补全: 为 '{winner['source']}' 从 GCJ02 -> WGS84")
        elif not has_gcj and has_wgs:
            lng_gcj, lat_gcj = geo_transforms.wgs84_to_gcj02(winner['longitude_wgs84'], winner['latitude_wgs84'])
            winner['longitude_gcj02'] = lng_gcj
            winner['latitude_gcj02'] = lat_gcj
            current_app.logger.debug(f"坐标补全: 为 '{winner['source']}' 从 WGS84 -> GCJ02")
    except Exception as e:
        current_app.logger.error(f"在为 '{winner['source']}' 进行坐标补全时发生错误: {e}")

    # --- 逆地理编码 ---
    return await _perform_reverse_geocoding(winner, user_id, parsed_original_address)

async def _process_batch_geocoding_async(raw_addresses, user_id, debug: bool = False):
    """
    Asynchronous core logic for batch geocoding based on SOP.
    """
    # SOP 步骤 1: 对所有地址进行预处理 - 行政区划补全
    current_app.logger.info(f"SOP第1步：开始对 {len(raw_addresses)} 个地址进行预处理（行政区划补全）...")
    
    # 修改：同时获取补全后的地址和解析出的结构化信息
    pre_processed_data = [address_processing.complete_address_jionlp(addr, return_dict=True) for addr in raw_addresses]
    
    current_app.logger.info("SOP第1步：所有地址预处理完成。")
    
    # SOP Part A: 批量语义预分析（并行执行，但在主流程中同步等待）
    semantic_analysis_result = None
    try:
        current_app.logger.info("开始批量语义预分析...")
        completed_addresses = [item['completed_address'] for item in pre_processed_data]
        semantic_analysis_result = await llm_service.batch_semantic_analysis(completed_addresses)
        if semantic_analysis_result and not semantic_analysis_result.get('error'):
            current_app.logger.info(f"批量语义预分析完成，主题名称: {semantic_analysis_result.get('theme_name', '未知')}")
        else:
            current_app.logger.warning(f"批量语义预分析失败: {semantic_analysis_result.get('error') if semantic_analysis_result else '无结果'}")
        # 轮次汇总日志（Fast/Slow Path）
        if semantic_analysis_result:
            theme_name = semantic_analysis_result.get('theme_name', '地理编码任务')
            search_needed = semantic_analysis_result.get('search_needed', False)
            enhanced = semantic_analysis_result.get('enhanced', False)
            search_query = semantic_analysis_result.get('search_query')
            if not search_needed:
                current_app.logger.info(f"[语义预分析汇总] 第一轮(Fast)主题='{theme_name}'；未触发第二轮(无需联网搜索)")
            else:
                if enhanced:
                    current_app.logger.info(f"[语义预分析汇总] 第一轮(Fast)主题='{theme_name}'；第二轮(Slow)增强成功 (query='{search_query}')")
                else:
                    current_app.logger.warning(f"[语义预分析汇总] 第一轮(Fast)主题='{theme_name}'；第二轮(Slow)未增强/失败 (query='{search_query}', error='{semantic_analysis_result.get('error')}')")
    except Exception as e:
        current_app.logger.error(f"批量语义预分析异常: {e}")
        semantic_analysis_result = {
            'theme_name': '地理编码任务',
            'error': f"语义分析失败: {str(e)}"
        }

    # --- Start of Logging ---
    # 1. Create a GeocodingTask record for this batch job.
    log_task = None
    if user_id:
        try:
            user = User.query.get(user_id)
            is_admin = user.is_admin if user else False

            # Do not log tasks for admin users
            if is_admin:
                current_app.logger.info(f"User {user_id} is an admin, skipping task logging.")
                log_task = None
            else:
                task_name = semantic_analysis_result.get('theme_name', f"地理编码任务于 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                log_task = GeocodingTask(
                    user_id=user_id,
                    task_name=task_name
                )
                db.session.add(log_task)
                db.session.flush()  # Use flush to get the ID before full commit
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to create GeocodingTask for user {user_id}: {e}")
            log_task = None # Ensure task is None if creation fails
    # --- End of Preliminary Logging ---

    # Address-level parallel processing
    tasks = []
    total_addresses = len(pre_processed_data)
    for i, item in enumerate(pre_processed_data):
        log_prefix = f"[地址 {i+1}/{total_addresses}] "
        
        completed_address = item['completed_address']
        parsed_address = item['parsed_address']
        # 创建包含上下文设置的协程任务
        tasks.append(
            _get_best_geocode_result(completed_address, user_id, parsed_address, log_prefix, debug)
        )
        
    processed_results = await asyncio.gather(*tasks)

    # request_context_var.set('') <--- This is no longer needed here
    # Format final results for frontend
    all_results_for_frontend = []
    for i, result_pack in enumerate(processed_results):
        original_address = raw_addresses[i]
        parsed_parts = pre_processed_data[i]['parsed_address']

        winner = result_pack.get('winner', {})
        all_apis = result_pack.get('all_results', [])

        if 'error' in winner:
            all_results_for_frontend.append({
                'address': original_address,
                'selected_result': {'api': 'error', 'name': winner.get('error', 'Processing failed')},
                'api_results': all_apis
            })
            continue

        # 新策略：地理编码免费，取消扣分
        # if user_id:
        #     used_user_key = winner.get('key_type') == 'user'
        #     points_to_deduct = get_points_cost('geocoding', used_user_key)
        #     deduct_points(user_id, points_to_deduct)
        #     current_app.logger.info(f"计费：为地址 '{original_address}' 的成功解析扣除 {points_to_deduct} 积分。")

        # Reconstruct the nested structure expected by the frontend's displayCascadeResults function
        # 当优胜者为天地图/百度且逆地理失败时，不回退到原始地址，直接用“-”作为匹配地址
        winner_source = winner.get('source', 'N/A')
        is_baidu_or_tdt = isinstance(winner_source, str) and (winner_source.startswith('baidu') or winner_source.startswith('tianditu'))
        reverse_succeeded = isinstance(winner_source, str) and ('_re-geocoded' in winner_source or '_reverse' in winner_source)
        formatted_for_display = winner.get('formatted_address') or '-'
        if is_baidu_or_tdt and not reverse_succeeded:
            formatted_for_display = '-'

        final_result_item = {
            'address': original_address,
            'selected_result': {
                'result': {
                    'formatted_address': formatted_for_display,
                    'province': parsed_parts.get('province') or winner.get('province', ''),
                    'city': parsed_parts.get('city') or winner.get('city', ''),
                    'district': parsed_parts.get('county') or winner.get('district', ''),
                    'latitude_gcj02': winner.get('latitude_gcj02'),
                    'longitude_gcj02': winner.get('longitude_gcj02'),
                    'latitude_wgs84': winner.get('latitude_wgs84'),
                    'longitude_wgs84': winner.get('longitude_wgs84'),
                    'name': formatted_for_display
                },
                'api': winner_source,
                'source_api': winner_source,
                'confidence': winner.get('calculated_confidence', 0.0),
                'selection_method_note': 'SOP V3.0 Cascade'
            },
            'api_results': all_apis
        }
        all_results_for_frontend.append(final_result_item)
    
    # 构造包含语义分析结果的返回数据
    response_data = {
        'results': all_results_for_frontend,
        'semantic_analysis': semantic_analysis_result
    }
    if debug:
        # 把每个地址的调试跟踪也返回
        try:
            response_data['debug'] = [r.get('debug') for r in processed_results if isinstance(r, dict) and r.get('debug')]
        except Exception:
            pass
            
    # --- Start of Detailed Logging ---
    # 2. Log each address result to the AddressLog table.
    if log_task: # Only proceed if the parent task was created successfully
        try:
            logs_to_add = []
            for result_item in all_results_for_frontend:
                original_address = result_item.get('address')
                selected_result = result_item.get('selected_result', {})
                confidence = selected_result.get('confidence')

                if original_address:
                    log_entry = AddressLog(
                        task_id=log_task.id,
                        address_keyword=original_address,
                        confidence=confidence
                    )
                    logs_to_add.append(log_entry)
            
            if logs_to_add:
                db.session.bulk_save_objects(logs_to_add)
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to save AddressLog entries for task_id {log_task.id}: {e}")
    # --- End of Detailed Logging ---

    return response_data

@geocoding_bp.route('/process', methods=['POST'])
@login_required
def geocode_address_batch():
    """
    (SOP V3.0) Main batch geocoding API endpoint (Sync Wrapper).
    Orchestrates the entire process based on the SOP by calling the async core.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'results': [], 'message': '无效的请求数据'}), 400

        raw_addresses = data.get('addresses', [])
        if not raw_addresses:
            return jsonify({'success': False, 'results': [], 'message': 'Addresses list cannot be empty'}), 400

        user_id = current_user.id if current_user.is_authenticated else None

        # Debug flag
        debug = bool(data.get('debug'))
        # Run the async core logic
        response_data = asyncio.run(_process_batch_geocoding_async(raw_addresses, user_id, debug))
        
        # 构造响应，确保向后兼容
        return jsonify({
            'success': True, 
            'results': response_data.get('results', []),
            'semantic_analysis': response_data.get('semantic_analysis'),
            'debug': response_data.get('debug') if debug else None
        })

    except Exception as e:
        current_app.logger.error(f"批量地理编码主路由发生异常: {e}", exc_info=True)
        return jsonify({'success': False, 'results': [], 'message': f'服务器内部错误: {str(e)}'}), 500

# === Web Intelligence (三步骤) 路由 ===
@geocoding_bp.route('/web_intelligence/search_collate', methods=['POST'])
def wi_search_collate():
    try:
        data = request.get_json() or {}
        original_address = data.get('original_address', '').strip()
        if not original_address:
            return jsonify({'success': False, 'message': 'original_address 不能为空'}), 400

        current_app.logger.info(f"[WI-START] Starting web intelligence search for address: '{original_address}'")

        # 根据需求：直接跳过联网LLM与DuckDuckGo，走本地搜狗抓取
        sogou_items = search_sogou(original_address, max_results=8)

        # 针对每条结果：记录原文、构造LLM提示词、调用LLM做摘录、判断是否有效
        collated = []
        for idx, item in enumerate(sogou_items):
            raw_content = (item.get('raw_content') or '').strip()
            title = item.get('title') or ''
            url = item.get('url') or ''

            if not raw_content or len(raw_content) < 80:
                # 原文过短，跳过
                current_app.logger.info(f"[WI][Sogou][skip-short] #{idx+1} {title} {url}")
                continue

            # 构造提示词（按长度截断）
            truncated = raw_content[:2500]
            llm_prompt = (
                f"请仅从下方网页‘原文正文’中，逐条摘录与“{original_address}”相关的地理定位信息的‘原句’，不要改写。\n"
                f"覆盖要点（尽可能多地抓取，不编造）：\n"
                f"- 位置与行政区层级：位于/坐落/隶属/省市县区镇/街道/社区等\n"
                f"- 范围与边界：范围/边界描述/面积/范围内的道路或河流\n"
                f"- 相邻/关联地标与交通：附近地标/渡口/桥梁/道路/河流/方向关系\n"
                f"- 内部构成：范围内的街道、建筑、节点（如‘南胜街、西门街、城内街…’）\n"
                f"输出要求：\n"
                f"1) 只输出网页‘原文句子’，每条一行；\n"
                f"2) 优先含有‘位于/坐落/隶属/范围/边界/面积/渡口/大桥/街/路/河’等关键词；\n"
                f"3) 期望返回 5-12 条，若确无相关信息，仅输出：无相关信息。\n\n"
                f"[网页标题]\n{title}\n\n[原文正文节选]\n{truncated}"
            )

            # 调用LLM（使用现有的聊天接口而非联网搜索）
            try:
                llm_resp = asyncio.run(llm_service.call_llm_api(llm_prompt))
                llm_text = (llm_resp or {}).get('content') or ''
            except Exception as e:
                current_app.logger.error(f"[WI][Sogou][llm-fail] #{idx+1} {title}: {e}")
                llm_text = ''

            # 后台记录：原文、提示词、结果
            current_app.logger.info(
                f"\n[WI][Sogou][#{idx+1}] URL: {url}\n[RAW]\n{truncated}\n\n[PROMPT]\n{llm_prompt}\n\n[LLM]\n{llm_text}\n"
            )

            # 有效性判断（简单启发式）
            has_valid = False
            if llm_text and ('无相关信息' not in llm_text):
                if re.search(r"位于|坐落|地处|隶属|行政区|省|市|县|区|镇|乡|街道|大道|公路|道路|路|巷|村|社区|附近|坐标", llm_text):
                    has_valid = True

            if has_valid:
                collated.append({
                    'title': title,
                    'url': url,
                    'excerpt': llm_text.strip(),
                    'sources': [url] if url else [],
                    'debug': {
                        'raw_content': truncated,
                        'llm_prompt': llm_prompt,
                        'llm_output': llm_text
                    }
                })

        # 第二步：聚合去重（将前面所有摘录统一给LLM，去掉重复，合并相似，尽量保留不同信息）
        agg_input_lines = [f"- {itm.get('excerpt','').strip()}" for itm in collated if itm.get('excerpt')]
        agg_prompt = (
            f"以下是从多个网页中摘取的与“{original_address}”相关的‘原文句子’列表。\n"
            f"任务：去重并合并表述相同或近似的信息，尽量保留不同信息；若两句信息量不同，保留信息更全的一句；保持原文风格，不要改写或编造。\n"
            f"输出要求：\n"
            f"- 仅输出合并后的句子清单，每行一句；\n"
            f"- 建议返回 8-20 条；\n"
            f"- 若没有有效内容，请输出：无相关信息。\n\n"
            f"[原句列表]\n{chr(10).join(agg_input_lines)}"
        )

        final_lines: list[str] = []
        if agg_input_lines:
            try:
                agg_resp = asyncio.run(llm_service.call_llm_api(agg_prompt))
                agg_text = (agg_resp or {}).get('content') or ''
                final_lines = [ln.strip('- ').strip() for ln in agg_text.split('\n') if ln.strip() and '无相关信息' not in ln]
            except Exception as e:
                current_app.logger.error(f"[WI][Aggregate][llm-fail] {e}")

        # 将聚合结果映射回来源URL（简单子串匹配聚合来源）
        final_excerpts = []
        for line in final_lines:
            src_urls = []
            for itm in collated:
                ex = itm.get('excerpt','')
                if not ex:
                    continue
                if line in ex or ex in line:
                    for u in (itm.get('sources') or []):
                        if u and u not in src_urls:
                            src_urls.append(u)
            final_excerpts.append({'excerpt': line, 'sources': src_urls})

        dossier = {
            'original_address': original_address,
            'web_search_results_count': len(sogou_items),
            'collated_excerpts': final_excerpts if final_excerpts else collated,
            'source': 'sogou_local',
            'debug': {
                'aggregate_prompt': agg_prompt,
                'aggregate_input_count': len(agg_input_lines)
            }
        }

        # 新策略：网络搜索（本地搜狗抓取也视为“网络搜索”）按 2 分计费
        try:
            if current_user.is_authenticated:
                user_id = current_user.id
                points_to_deduct = get_points_cost('web_search', used_user_key=False)
                if points_to_deduct and points_to_deduct > 0:
                    deduct_points(user_id, points_to_deduct)
                    current_app.logger.info(f"计费：网络搜索 扣除 {points_to_deduct} 积分。")
        except Exception as e:
            current_app.logger.error(f"网络搜索扣分异常: {e}")

        if not (final_excerpts or collated):
            return jsonify({'success': False, 'dossier': dossier, 'message': '未提取到有效定位信息'}), 200
        return jsonify({'success': True, 'dossier': dossier, 'message': None})
    except Exception as e:
        current_app.logger.error(f"/web_intelligence/search_collate 异常: {e}")
        return jsonify({'success': False, 'message': f'服务器内部错误: {str(e)}'}), 500


@geocoding_bp.route('/web_intelligence/validate_candidates', methods=['POST'])
def wi_validate_candidates():
    try:
        data = request.get_json() or {}
        dossier = data.get('dossier') or {}
        poi_candidates = data.get('poi_candidates') or []
        if not poi_candidates:
            return jsonify({'success': False, 'message': 'poi_candidates 不能为空'}), 400

        original_address = dossier.get('original_address') or ''

        # 使用LLM结合情报进行验证
        decision = asyncio.run(llm_service.validate_poi_with_dossier(original_address, poi_candidates, dossier))

        response_payload = {
            'success': True,
            'has_match': bool(decision.get('has_match')),
            'best_match_index': decision.get('best_match_index'),
            'selected_poi': (poi_candidates[decision['best_match_index']] if (decision.get('has_match') and isinstance(decision.get('best_match_index'), int) and 0 <= decision['best_match_index'] < len(poi_candidates)) else None),
            'match_confidence': float(decision.get('match_confidence') or 0.0),
            'validation_reason': decision.get('validation_reason') or '',
            'mismatch_reasons': decision.get('mismatch_reasons') or []
        }
        # 新策略：本接口会触发一次 LLM 调用，按 2 分计费
        try:
            if current_user.is_authenticated:
                user_id = current_user.id
                points_to_deduct = get_points_cost('llm_call', used_user_key=False)
                if points_to_deduct and points_to_deduct > 0:
                    deduct_points(user_id, points_to_deduct)
                    current_app.logger.info(f"计费：POI验证 LLM 扣除 {points_to_deduct} 积分。")
                
                # 返回最新的用户信息
                updated_user = user_service.get_user_by_id(user_id)
                if updated_user:
                    response_payload['user'] = {
                        'points': updated_user.points
                    }
        except Exception as e:
            current_app.logger.error(f"POI验证扣分或刷新用户信息异常: {e}")

        return jsonify(response_payload)
    except Exception as e:
        current_app.logger.error(f"/web_intelligence/validate_candidates 异常: {e}")
        return jsonify({'success': False, 'message': f'服务器内部错误: {str(e)}'}), 500


@geocoding_bp.route('/web_intelligence/suggest_keywords', methods=['POST'])
def wi_suggest_keywords():
    try:
        data = request.get_json() or {}
        original_address = (data.get('original_address') or '').strip()
        dossier = data.get('dossier') or {}
        mismatch_reasons = data.get('mismatch_reasons') or []

        # 优先：调用LLM生成关键词（JSON）
        excerpts = []
        try:
            for it in (dossier.get('collated_excerpts') or [])[:15]:
                ex = (it.get('excerpt') or '').strip()
                if ex:
                    excerpts.append(f"- {ex}")
        except Exception:
            pass
        bg_str = "\n".join(excerpts) if excerpts else '（无）'

        # 解析行政区，便于生成完整可搜索地址
        try:
            parsed_admin = jio.parse_location(original_address)
        except Exception:
            parsed_admin = {}
        
        province = parsed_admin.get('province') or ''
        city = parsed_admin.get('city') or ''
        county = parsed_admin.get('county') or ''
        admin_parts = [part for part in [province, city, county] if part and part != 'None']
        admin_prefix = "".join(admin_parts)

        prompt = f"""
# 角色
你是一名专业的地理信息分析师，专门从非结构化文本中提取可用于地图POI检索的有效关键词。

# 目标
根据给定的“原始地址”和“网络搜集信息”，生成一个按“搜索成功率”从高到低排序的关键词列表。

# 背景信息
- **原始地址（已经尝试过但搜索失败）**: {original_address}
- **网络搜集信息**: 
{bg_str}
- **行政区划前缀（参考）**: {admin_prefix or '（无）'}
- **前序步骤失败原因（参考）**: {'; '.join(mismatch_reasons) if mismatch_reasons else '（无）'}

# 任务指令与约束
请严格按照以下步骤执行：

**第一步：提取所有潜在的地理位置候选词**
从“网络搜集信息”中，找出所有可能表示具体地点、街道、社区、区域的名称。

**第二步：评估与过滤候选词**
对上一步提取的每个候选词，根据以下规则进行评估和过滤：
1.  **【必须排除】与原始地址高度相似的词**: 如果候选词与“{original_address}”基本相同或只是简单的补充（例如，添加“历史文化街区”、“风景区”等描述性词语），则必须丢弃。
2.  **【必须排除】模糊或描述性的短语**: 丢弃那些描述地理特征但不是正式名称的词语（例如：“鱼骨状路网”、“商业中心”、“古城区”等）。
3.  **【优先保留】具体的、替代性的名称**: 优先保留与原始地址不同的、具体的名称。这包括：
    - 历史名称（例如：曾用名“中山路”、“胜利路”）。
    - 包含在内的更小行政单元（例如：“仰山社区”）。
    - 官方或当前使用的、与原始地址不同的名称。

**第三步：对有效关键词进行排序**
将通过过滤的关键词，按照预期搜索成功率从高到低进行排序。排序逻辑如下：
1.  **最高优先级 (P0)**: 历史上或现在明确使用的、不同的街道名（如“胜利路”、“中山路”）。
2.  **次高优先级 (P1)**: 地址所属的、更精确的社区或小区名（如“仰山社区”）。
3.  **较低优先级 (P2)**: 其他可能有用的、但范围可能更大或不确定的相关地名。

**第四步：格式化输出**
将最终排序好的关键词列表，以JSON对象格式输出。列表中每一项包含三个字段：
- `display_keyword`: 用于前端显示的、简洁的关键词（如：“胜利路”）。
- `full_address_for_search`: 用于后端POI搜索的、拼接了行政区划前缀的完整地址（如：“江西省抚州市金溪县胜利路”）。
- `reason`: **直接引用或概括**“网络搜集信息”中的关键句子作为推荐依据。例如：“信息中提到‘新中国成立后改称胜利路’”。

**输出JSON格式示例**:
```json
{{
  "suggestions": [
    {{
      "display_keyword": "胜利路",
      "full_address_for_search": "{admin_prefix}胜利路",
      "reason": "依据：‘...新中国成立后改称胜利路’"
    }},
    {{
      "display_keyword": "仰山社区",
      "full_address_for_search": "{admin_prefix}仰山社区",
      "reason": "依据：‘...位于秀谷镇仰山社区...’"
    }}
  ]
}}
```
"""
        
        suggestions = []
        try:
            llm_resp = asyncio.run(llm_service.call_llm_api(prompt))
            content = (llm_resp or {}).get('content') or ''
            m = re.search(r"```json\s*([\s\S]+?)\s*```", content)
            json_str = m.group(1) if m else content
            obj = json.loads(json_str)
            raw_sugs = obj.get('suggestions') or []
            
            for s in raw_sugs:
                display_kw = (s.get('display_keyword') or '').strip()
                full_addr = (s.get('full_address_for_search') or '').strip()
                
                if not display_kw or not full_addr:
                    continue
                
                # 后端再次过滤，确保不与原始地址重复
                if full_addr == original_address or full_addr in original_address or original_address in full_addr:
                    continue

                suggestions.append({
                    'display': display_kw[:30],
                    'query': full_addr[:120],
                    'reason': (s.get('reason') or '').strip()[:120] or '基于情报分析生成',
                })
        except Exception as e:
            current_app.logger.error(f"关键词LLM生成失败: {e}")

        # 兜底：从情报句子里抽取包含街/路/桥/渡/塔/山/河等词的短语
        if not suggestions:
            pattern = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,15}(?:街|路|巷|大道|大街|桥|渡|塔|山|公园|广场|河|湖|村|社区))")
            picked = []
            for line in excerpts:
                for m in pattern.finditer(line):
                    kw = m.group(1)
                    if kw and kw not in picked and kw not in original_address and original_address not in kw:
                        picked.append(kw)
            for kw in picked[:10]:
                full_kw = f"{admin_prefix}{kw}" if admin_prefix else kw
                suggestions.append({
                    'display': kw,
                    'query': full_kw,
                    'reason': '来源于情报句子的地标/街路等名词',
                })

        # 最终去重并限量
        uniq = []
        seen_queries = set()
        for s in suggestions:
            if s['query'] in seen_queries:
                continue
            uniq.append(s)
            seen_queries.add(s['query'])
        suggestions = uniq[:12]

        # 新策略：本接口会触发一次 LLM 调用，按 2 分计费
        try:
            if current_user.is_authenticated:
                user_id = current_user.id
                points_to_deduct = get_points_cost('llm_call', used_user_key=False)
                if points_to_deduct and points_to_deduct > 0:
                    deduct_points(user_id, points_to_deduct)
                    current_app.logger.info(f"计费：关键词建议 LLM 扣除 {points_to_deduct} 积分。")
        except Exception as e:
            current_app.logger.error(f"关键词建议扣分异常: {e}")

        response_data = {'success': True, 'keyword_suggestions': suggestions, 'mismatch_reasons': mismatch_reasons}
        if current_user.is_authenticated:
            updated_user = user_service.get_user_by_id(current_user.id)
            if updated_user:
                response_data['user'] = {'points': updated_user.points}

        return jsonify(response_data)
    except Exception as e:
        current_app.logger.error(f"/web_intelligence/suggest_keywords 异常: {e}")
        return jsonify({'success': False, 'message': f'服务器内部错误: {str(e)}'}), 500

@geocoding_bp.route('/poi_search', methods=['POST'])
@decorators.async_route
async def poi_search_route():
    """
    Handles POI search requests from different map providers.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'results': [], 'message': '无效的请求数据'}), 400

        keyword = data.get('keyword')
        source = data.get('source', 'amap') # Default to amap if not provided
        user_id = current_user.id if current_user.is_authenticated else None

        if not keyword:
            return jsonify({'success': False, 'results': [], 'message': '搜索关键词不能为空'}), 400
        
        # Get the appropriate searcher instance from the factory/service module
        searcher = poi_search.get_searcher(source, user_id)
        
        if searcher is None:
            return jsonify({'success': False, 'results': [], 'message': f"不支持的搜索源: {source}"}), 400

        # Perform the search
        results = await searcher.search(keyword)
        
        # The 'results' from the searcher should already be in the correct format.
        # It usually returns a dictionary like {'pois': [...]} or {'error': ...}
        if 'error' in results:
            return jsonify({'success': False, 'results': [], 'message': results['error']}), 500

        # 新策略：按源扣积分（天地图0，高德/百度2）
        try:
            if user_id:
                src = (source or '').lower()
                if src in ('amap', 'baidu', 'tianditu'):
                    task_key = f"poi_search_{src}"
                    used_user_key = False  # POI搜索不区分用户Key优惠，统一价
                    points_to_deduct = get_points_cost(task_key, used_user_key)
                    if points_to_deduct and points_to_deduct > 0:
                        deduct_points(user_id, points_to_deduct)
                        current_app.logger.info(f"计费：POI搜索[{src}] 扣除 {points_to_deduct} 积分。")
        except Exception as e:
            current_app.logger.error(f"POI搜索扣分异常: {e}")

        response_data = {'success': True, 'results': results.get('pois', [])}
        if user_id:
            updated_user = user_service.get_user_by_id(user_id)
            if updated_user:
                response_data['user'] = {'points': updated_user.points}

        return jsonify(response_data)

    except Exception as e:
        current_app.logger.error(f"POI搜索路由 /poi_search 发生异常: {e}", exc_info=True)
        return jsonify({'success': False, 'results': [], 'message': f'服务器内部错误: {str(e)}'}), 500

@geocoding_bp.route('/auto_select_point', methods=['POST'])
@decorators.async_route
async def auto_select_point_route():
    """
    智能自动选点路由。
    接收一个原始地址和一个POI列表，使用LLM来决策最佳匹配项。
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400

        # 兼容两种键名：优先使用规范的 'pois'，兼容历史前端 'poi_results'
        pois = data.get('pois') or data.get('poi_results')
        original_address = data.get('original_address')
        source_context = data.get('source_context', '无附加上下文')
        user_id = current_user.id if current_user.is_authenticated else None

        if not pois or not original_address:
            return jsonify({'success': False, 'message': '缺少POI列表或原始地址'}), 400

        # 调用LLM服务进行决策
        current_app.logger.info(f"开始LLM智能选点：原始地址='{original_address}', POI数量={len(pois)}, 来源上下文='{source_context}'")
        selected_poi = await llm_service.select_best_poi_from_search(
            original_address=original_address,
            poi_results=pois,
            user_id=user_id,
            source_context=source_context
        )
        current_app.logger.info(f"LLM选点结果：{json.dumps(selected_poi, ensure_ascii=False)}")

        if selected_poi and 'error' not in selected_poi:
            # 新策略：一次 LLM 调用扣 2 分
            try:
                if user_id:
                    points_to_deduct = get_points_cost('llm_call', used_user_key=False)
                    if points_to_deduct and points_to_deduct > 0:
                        deduct_points(user_id, points_to_deduct)
                        current_app.logger.info(f"计费：LLM选点 扣除 {points_to_deduct} 积分。")
            except Exception as e:
                current_app.logger.error(f"LLM选点扣分异常: {e}")

            # 使用LLM返回的索引信息
            index = selected_poi.get('selected_index')
            if index is not None and 0 <= index < len(pois):
                response_data = {
                    'success': True, 
                    'best_match_index': index,
                    'best_match': pois[index], # Return the full POI object as well
                    'reasoning': selected_poi.get('reasoning', '')
                }
                if user_id:
                    updated_user = user_service.get_user_by_id(user_id)
                    if updated_user:
                        response_data['user'] = {
                            'points': updated_user.points
                        }
                return jsonify(response_data)
            else:
                return jsonify({'success': False, 'message': 'LLM未返回有效的索引信息'})
        elif selected_poi and 'error' in selected_poi:
            # 如果LLM服务返回了一个特定的错误信息
            return jsonify({'success': False, 'message': selected_poi['error']})
        else:
            # 如果没有选出任何点
            return jsonify({'success': False, 'message': '未能决策出最佳匹配点'})

    except Exception as e:
        current_app.logger.error(f"路由 /auto_select_point 发生异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务器内部错误: {str(e)}'}), 500 

@geocoding_bp.route('/reverse_geocode', methods=['POST'])
@decorators.async_route
async def reverse_geocode_route():
    """
    逆地理编码路由。
    根据坐标获取地址信息。
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400

        lat = data.get('lat')
        lng = data.get('lng')
        source = data.get('source', 'amap')  # 默认使用高德
        
        if lat is None or lng is None:
            return jsonify({'success': False, 'message': '缺少坐标参数'}), 400

        user_id = current_user.id if current_user.is_authenticated else None
        
        # 使用统一的地理编码器工厂方法
        try:
            geocoder = geocoding_apis.get_geocoder(source, user_id)
        except ValueError as e:
            return jsonify({'success': False, 'message': f'不支持的坐标源: {source}'}), 400

        # 执行逆地理编码
        result = await geocoder.reverse_geocode(lat, lng)
        
        if 'error' in result:
            return jsonify({'success': False, 'message': result['error']}), 500
        
        return jsonify({
            'success': True,
            'formatted_address': result.get('formatted_address', ''),
            'address_components': {
                'province': result.get('province', ''),
                'city': result.get('city', ''),
                'district': result.get('district', '')
            }
        })

    except Exception as e:
        current_app.logger.error(f"逆地理编码路由 /reverse_geocode 发生异常: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'服务器内部错误: {str(e)}'}), 500

@geocoding_bp.route('/get_approved_suffixes', methods=['GET'])
def get_approved_suffixes():
    """获取所有已批准的地名后缀"""
    try:
        # Querying the model directly using SQLAlchemy
        approved_suffixes = db.session.query(LocationType.name).filter_by(status='approved').order_by(db.func.length(LocationType.name).desc()).all()
        # The result is a list of tuples, so we extract the first element of each tuple
        suffixes = [item[0] for item in approved_suffixes]
        return jsonify({'success': True, 'suffixes': suffixes})
    except Exception as e:
        current_app.logger.error(f"Error fetching approved suffixes: {e}")
        return jsonify({'success': False, 'message': '获取后缀列表失败'}), 500