import os
from datetime import datetime
import json
import requests
import zhipuai
import secrets
import string

from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.utils import secure_filename

from .. import db
from ..models import (User, Feedback, GeocodingHistory, Notification, 
                      UserApiKey, Referral, Task, LocationType)
from ..services import user_service, llm_service
from ..utils.auth import login_required

user_bp = Blueprint('user', __name__, url_prefix='/user')

REFERRAL_POINTS_PER_SIDE = 50

@user_bp.route('/profile', methods=['GET'])
@login_required
def get_profile():
    user = user_service.get_user_by_id(session['user_id'])
    if user:
        user_info = {
            'id': user.id,
            'email': user.email,
            'username': user.username or user.email.split('@')[0],
            'points': user.points,
            'avatar_url': user.avatar_url,
            'amap_key': user.amap_key,
            'baidu_key': user.baidu_key,
            'tianditu_key': user.tianditu_key,
            'ai_key': user.ai_key
        }
        # Note: Daily request count logic needs to be re-implemented if required,
        # as the original implementation was tied to the old DB structure.
        # For now, returning an empty dict.
        user_info['daily_requests'] = {}
        return jsonify({'success': True, 'user': user_info})
    return jsonify({'success': False, 'message': '用户未找到'}), 404

@user_bp.route('/feedback', methods=['POST'])
@login_required
def submit_feedback():
    data = request.json
    feedback_text = data.get('feedback_text')
    
    if not feedback_text:
        return jsonify({'success': False, 'message': '反馈内容不能为空'}), 400

    new_feedback = Feedback(
        user_id=session['user_id'],
        description=feedback_text,
        image_paths=data.get('image_paths', '[]'),
        category=data.get('category', 'general'),
        metadata_json=data.get('metadata', '{}') # Use the corrected field name
    )
    
    try:
        db.session.add(new_feedback)
        db.session.commit()
        return jsonify({'success': True, 'message': '反馈已提交，感谢您的宝贵意见！'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting feedback: {e}")
        return jsonify({'success': False, 'message': '提交反馈失败'}), 500

@user_bp.route('/social_share_copy', methods=['POST'])
@login_required
def generate_social_share_copy():
    """根据用户最近的使用上下文与可选项目描述，生成个性化社交平台推广文案。"""
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    project_context = (data.get('project_context') or '').strip()
    target_platforms = data.get('platforms') or []
    tone = (data.get('tone') or 'friends').strip()
    current_task_name = (data.get('current_task_name') or '').strip()

    # 收集上下文：优先基于任务名称（当前/最近），否则回退到历史表
    conn = db.session # Use db.session for SQLAlchemy
    recent_summary = ''
    task_name_context = ''
    try:
        # 若未传当前任务名，则取最近任务
        if not current_task_name:
            try:
                tn_row = conn.query(Task.task_name).filter(Task.user_id == user_id).order_by(Task.updated_at.desc(), Task.created_at.desc()).limit(1).first()
                if tn_row and tn_row[0]:
                    task_name_context = tn_row[0]
            except Exception:
                task_name_context = ''
        else:
            task_name_context = current_task_name

        # 检查表结构
        try:
            cols = [r[1] for r in conn.query(GeocodingHistory.c).first()] # Assuming GeocodingHistory is a table
        except Exception:
            cols = []

        row = None
        if 'original_address' in cols and 'geocoded_results_json' in cols:
            row = conn.query(GeocodingHistory.original_address, GeocodingHistory.geocoded_results_json, GeocodingHistory.created_at).filter(GeocodingHistory.user_id == user_id).order_by(GeocodingHistory.created_at.desc()).limit(1).first()
            if row:
                orig = row[0]
                try:
                    results = json.loads(row[1]) if row[1] else []
                except Exception:
                    results = []
                count = len(results) if isinstance(results, list) else 0
                recent_summary = f"最近一次处理：原始地址样例《{(orig or '')[:30]}...》，生成 {count} 条候选并完成校准。"
        elif 'address' in cols:
            row = conn.query(GeocodingHistory.address, GeocodingHistory.created_at).filter(GeocodingHistory.user_id == user_id).order_by(GeocodingHistory.created_at.desc()).limit(1).first()
            if row:
                orig = row[0]
                recent_summary = f"最近一次处理：原始地址样例《{(orig or '')[:30]}...》，完成地理编码并导出结果。"
        else:
            # 未找到历史表或列，保持空摘要
            pass
    finally:
        conn.close() # Close the session

    platforms_str = ', '.join([str(p) for p in target_platforms]) if target_platforms else '社交平台'
    base_intro = (
        "陆梧GeoCo是一款智能地理编码与地点信息处理工具，支持多源融合、智能校准、批量导出等。"
    )

    # 组装提示词（默认朋友圈口吻，去广告化）
    if tone == 'friends':
        prompt = f"""
请为{platforms_str}撰写1-2段中文朋友圈口吻的分享文案，避免硬广与夸张形容，不要带官方广告语。
已知信息：
1) 平台介绍：{base_intro}
2) 用户上下文：{recent_summary or '无最近记录'}
3) 若存在任务名称，请在开头自然融入（例如：“刚刚对《{task_name_context or '某地名录'}》进行地理编码”）：{task_name_context or '无'}
3) 用户补充描述：{project_context or '无'}

要求：
- 用第一人称，像对朋友分享“我刚发现一个特别好用的……”
- 具体描述使用场景/感受（如“批量处理省了我不少时间”“智能校准很稳”）
- 自然、可信，适度口语化，可适当使用少量emoji（不必强求）
- 每段≤120字；不要使用Markdown
- 末尾不出现强CTA广告词，可用“有需要可以了解/私聊我”这类柔和收尾
"""
    else:
        prompt = f"""
请为{platforms_str}撰写1-2段中文推广文案，风格亲和且具体，包含明确行动建议。
已知信息：
1) 平台介绍：{base_intro}
2) 用户上下文：{recent_summary or '无最近记录'}
3) 若存在任务名称，可自然提及作为案例背景：{task_name_context or '无'}
3) 用户补充描述：{project_context or '无'}

要求：
- 突出“批量处理、智能校准、多源融合、导出SHP/KML/Excel”等亮点
- 每段≤120字；不要使用Markdown
- 末尾包含温和的行动建议（例如：可搜索了解或试用）
"""

    try:
        # 同步调用异步LLM封装
        result = llm_service.call_llm_api
        import asyncio
        llm_resp = asyncio.run(result(prompt))
        content = (llm_resp or {}).get('content') or ''
        if not content:
            content = (
                "我刚用陆梧GeoCo处理地理数据，批量+智能校准挺省心的，效率提升不少。需要做地址定位/导出的可以了解下。"
            )

        return jsonify({'success': True, 'copy': content})
    except Exception as e:
        current_app.logger.error(f"generate_social_share_copy error: {e}")
        fallback = (
            "我刚发现一个处理地理数据的工具（陆梧GeoCo），能多源融合和智能校准，使用下来挺顺手的。需要的朋友可以了解一下。"
        )
        return jsonify({'success': True, 'copy': fallback})

@user_bp.route('/upload_feedback_image', methods=['POST'])
@login_required
def upload_feedback_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': '没有文件部分'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        # 确保 uploads/feedback 目录存在
        # os.path.join(current_app.root_path, config.FEEDBACK_UPLOAD_FOLDER)
        # config.FEEDBACK_UPLOAD_FOLDER 已经是一个绝对路径
        upload_path = current_app.config['FEEDBACK_UPLOAD_FOLDER'] # 使用应用配置中的绝对路径
        os.makedirs(upload_path, exist_ok=True)
        
        filepath = os.path.join(upload_path, filename)
        file.save(filepath)
        # 返回相对于项目根目录的路径，或者直接返回绝对路径
        # 这里返回一个相对于 uploads 目录的路径，前端可能期望这样的路径
        relative_path = os.path.join('uploads', 'feedback', filename).replace('\\', '/') # 统一斜杠方向
        return jsonify({'success': True, 'message': '图片上传成功', 'image_url': f'/{relative_path}'})
    return jsonify({'success': False, 'message': '文件上传失败'}), 500

@user_bp.route('/history', methods=['GET'])
@login_required
def get_history():
    user_id = session['user_id']
    history_records = GeocodingHistory.query.filter_by(user_id=user_id).order_by(GeocodingHistory.created_at.desc()).limit(50).all()
    
    history_list = []
    for record in history_records:
        history_list.append({
            'id': record.id,
            'original_address': record.address, # Assuming 'address' field stores the original
            # The model needs to be updated if geocoded_results_json and selected_result_index are required
            'geocoded_results': [], # Placeholder
            'selected_result_index': None, # Placeholder
            'selected_result': None, # Placeholder
            'created_at': record.created_at.isoformat()
        })
    return jsonify({'success': True, 'history': history_list})


@user_bp.route('/delete_history', methods=['POST'])
@login_required
def delete_history():
    user_id = session['user_id']
    history_id = request.json.get('history_id')

    if not history_id:
        return jsonify({'success': False, 'message': '历史记录ID不能为空'}), 400

    record_to_delete = GeocodingHistory.query.filter_by(id=history_id, user_id=user_id).first()
    
    if record_to_delete:
        try:
            db.session.delete(record_to_delete)
            db.session.commit()
            return jsonify({'success': True, 'message': '历史记录删除成功'})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting history: {e}")
            return jsonify({'success': False, 'message': '删除失败'}), 500
    else:
        return jsonify({'success': False, 'message': '历史记录未找到或无权限删除'}), 404

@user_bp.route('/get_session_results', methods=['GET'])
def get_session_results_route():
    original_address = request.args.get('address')
    if not original_address:
        return jsonify({'success': False, 'message': '地址不能为空'}), 400

    session_id = session.sid
    if not session_id:
        return jsonify({'success': False, 'message': '会话ID不存在'}), 400

    # This function was not part of the original file's imports, so it's commented out.
    # If it's meant to be re-added, its imports and logic would need to be restored.
    # For now, returning a placeholder response.
    return jsonify({'success': False, 'message': '会话结果获取功能待实现'}), 501

@user_bp.route('/save_calibration_result', methods=['POST'])
@login_required
def save_calibration_result():
    user_id = session['user_id']
    data = request.json
    original_address = data.get('original_address')
    selected_result_index = data.get('selected_result_index')

    if not original_address or selected_result_index is None:
        return jsonify({'success': False, 'message': '原始地址和选中结果索引不能为空'}), 400

    session_id = session.sid
    if not session_id:
        return jsonify({'success': False, 'message': '会话ID不存在'}), 400
    
    # 从缓存中加载所有地理编码结果
    # This function was not part of the original file's imports, so it's commented out.
    # If it's meant to be re-added, its imports and logic would need to be restored.
    # For now, returning a placeholder response.
    all_geocoded_results = [] # Placeholder

    if not all_geocoded_results or not (0 <= selected_result_index < len(all_geocoded_results)):
        return jsonify({'success': False, 'message': '无效的会话或选中的结果索引'}), 400

    # 确保 geocoded_results_json 存储的是完整的列表，而不是单个选中的结果
    geocoded_results_json = json.dumps(all_geocoded_results, ensure_ascii=False)

    new_history_record = GeocodingHistory(
        user_id=user_id,
        address=original_address,
        geocoded_results_json=geocoded_results_json,
        selected_result_index=selected_result_index
    )
    
    try:
        db.session.add(new_history_record)
        db.session.commit()
        return jsonify({'success': True, 'message': '校准结果保存成功'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving calibration result: {e}")
        return jsonify({'success': False, 'message': f'保存校准结果失败: {e}'}), 500

@user_bp.route('/get_notifications', methods=['GET'])
@login_required
def get_notifications():
    user_id = session['user_id']
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    
    pagination = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).paginate(page=page, per_page=limit, error_out=False)
    notifications = pagination.items
    
    notifications_list = [{
        'id': n.id,
        'message': n.message,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat(),
        'link': n.link
    } for n in notifications]
    
    return jsonify({'success': True, 'notifications': notifications_list})

@user_bp.route('/notifications/unread_count', methods=['GET'])
@login_required
def get_unread_notifications_count():
    user_id = session['user_id']
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({'success': True, 'unread_count': unread_count})

@user_bp.route('/mark_notifications_as_read', methods=['POST'])
@login_required
def mark_notifications_as_read():
    user_id = session['user_id']
    notification_ids = request.json.get('ids', [])

    if not notification_ids or not isinstance(notification_ids, list):
        return jsonify({'success': False, 'message': '无效的通知ID'}), 400

    try:
        Notification.query.filter(
            Notification.user_id == user_id,
            Notification.id.in_(notification_ids)
        ).update({'is_read': True}, synchronize_session=False)
        db.session.commit()
        return jsonify({'success': True, 'message': '通知已标记为已读'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error marking notifications as read: {e}")
        return jsonify({'success': False, 'message': '更新通知状态失败'}), 500

@user_bp.route('/keys', methods=['GET'])
@login_required
def get_user_api_keys():
    user_id = session['user_id']
    keys = UserApiKey.query.filter_by(user_id=user_id).all()
    
    masked_keys = []
    for key in keys:
        key_value = key.key_value
        if not key_value: continue
        masked_key = f"{key_value[:4]}...{key_value[-4:]}" if len(key_value) > 8 else key_value
        masked_keys.append({
            "service_name": key.provider,
            "masked_key": masked_key,
            "points_awarded": key.earned_points,
            "status": key.status
        })
    return jsonify(success=True, keys=masked_keys)

def _validate_amap_key(api_key):
    """使用高德地理编码API验证高德Key的有效性。"""
    url = f"https://restapi.amap.com/v3/geocode/geo?address=北京市&output=json&key={api_key}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data.get('status') == '1':
            return True, ""
        else:
            error_message = data.get('info', '未知错误')
            return False, error_message
    except requests.RequestException as e:
        return False, f"请求高德API失败: {e}"

def _validate_baidu_key(api_key):
    """使用百度地理编码API验证百度Key的有效性。"""
    url = f"http://api.map.baidu.com/geocoding/v3/?address=北京市&output=json&ak={api_key}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        # 百度API成功时status为0，失败时为其他值
        if data.get('status') == 0:
            return True, ""
        else:
            # 根据经验，错误信息在 message 字段
            error_message = data.get('message', '未知错误')
            return False, error_message
    except requests.RequestException as e:
        return False, f"请求百度API失败: {e}"

def _validate_tianditu_key(api_key):
    """使用天地图地理编码API验证天地图Key的有效性。"""
    url = "http://api.tianditu.gov.cn/geocoder"
    # 天地图的API文档中 POST 请求参数为 postStr，其值为一个JSON字符串
    post_data = {
        'postStr': f'{{"keyWord":"北京市"}}',
        'tk': api_key
    }
    try:
        response = requests.post(url, data=post_data, timeout=5)
        
        # 检查是否是认证错误, e.g. "key's domain is not allowed", "IP anuthorization failed"
        # "IP a" for "IP authorization failed"
        if "domain" in response.text or "IP a" in response.text:
            return False, "Key的配置未包含当前网站域或IP，请检查天地图开发者后台的白名单设置"
        if response.status_code == 401: # Unauthorized
             return False, "Key无效或无权限"

        response.raise_for_status() # 抛出其他HTTP错误
        data = response.json()

        # 天地图API成功时status为'0'
        if data.get('status') == '0':
            return True, ""
        else:
            # 正常返回但status不为'0'的情况
            error_message = data.get('msg', '未知错误')
            return False, error_message
    except requests.HTTPError as e:
        return False, f"请求天地图API时发生HTTP错误: {e.response.text if e.response else e}"
    except requests.RequestException as e:
        return False, f"请求天地图API失败: {e}"
    except json.JSONDecodeError:
        return False, f"解析天地图API响应失败。响应内容: {response.text}"

def _validate_zhipuai_key(api_key):
    """使用智谱AI SDK验证Key的有效性。"""
    try:
        # 使用提供的key初始化一个新的客户端实例
        client = zhipuai.ZhipuAI(api_key=api_key)
        # 发送一个非常简单的请求来触发验证
        client.chat.completions.create(
            model="glm-3-turbo", # 使用最新的稳定模型
            messages=[{"role": "user", "content": "你好"}],
            max_tokens=2,
            temperature=0.1,
            timeout=10,
        )
        # 如果没有抛出异常，说明key是有效的
        return True, ""
    except zhipuai.core._errors.APIAuthenticationError as e:
        # 捕获特定的认证失败异常
        return False, "API Key无效或已过期"
    except Exception as e:
        # 其他异常（如网络问题）不应视为key无效
        # 但为了用户体验，我们还是返回一个通用错误
        return False, f"验证时发生未知错误: {str(e)}"
        
@user_bp.route('/keys', methods=['POST'])
@login_required
def save_user_api_key():
    user_id = session['user_id']
    data = request.json
    service_name = data.get('service_name')
    api_key = data.get('api_key')

    if not service_name or not api_key:
        return jsonify(success=False, message="参数不完整"), 400

    # Key validation logic... (omitted for brevity, remains the same)
    validators = {
        'amap': _validate_amap_key,
        'baidu': _validate_baidu_key,
        'tianditu': _validate_tianditu_key,
        'zhipuai': _validate_zhipuai_key
    }
    validator = validators.get(service_name)
    if not validator:
        return jsonify(success=False, message="不支持的服务类型"), 400

    is_valid, error_message = validator(api_key)
    if not is_valid:
        return jsonify(success=False, message=f"API Key无效: {error_message}"), 400

    # Save or update key
    existing_key = UserApiKey.query.filter_by(user_id=user_id, provider=service_name).first()
    was_new = False
    if existing_key:
        existing_key.key_value = api_key
        existing_key.status = 'active'
        existing_key.fail_count = 0
    else:
        was_new = True
        award_config = current_app.config['POINTS_AWARD_BY_SERVICE']
        points_to_award = award_config.get(service_name, award_config.get('default', 50))
        
        new_key = UserApiKey(
            user_id=user_id,
            provider=service_name,
            key_value=api_key,
            earned_points=points_to_award
        )
        db.session.add(new_key)
        if was_new:
            user_service.add_points(user_id, points_to_award)

    try:
        db.session.commit()
        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else api_key
        if was_new:
             message = f"API Key保存成功，恭喜您获得 {points_to_award} 积分！"
             return jsonify(success=True, message=message, points_awarded=points_to_award, service_name=service_name, masked_key=masked_key, status='active')
        else:
             message = "API Key更新成功！"
             return jsonify(success=True, message=message, points_awarded=0, service_name=service_name, masked_key=masked_key, status='active')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving API key: {e}")
        return jsonify(success=False, message="保存失败，请稍后重试。"), 500

def _generate_unique_referral_code():
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = ''.join(secrets.choice(alphabet) for _ in range(8))
        if not User.query.filter_by(referral_code=code).first():
            return code
    # Fallback with timestamp entropy
    return f"R{int(datetime.utcnow().timestamp())}"

@user_bp.route('/referral/info', methods=['GET'])
@login_required
def get_referral_info():
    user = user_service.get_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': '用户未找到'}), 404

    # Ensure referral code exists
    if not user.referral_code:
        try:
            user.referral_code = _generate_unique_referral_code()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"generate referral code error: {e}")
            return jsonify({'success': False, 'message': '生成推荐码失败'}), 500

    # Assemble share link
    base = request.host_url  # ends with '/'
    share_link = f"{base}?ref={user.referral_code}"

    # Stats
    total_invitees = Referral.query.filter_by(referrer_user_id=user.id).count()

    return jsonify({
        'success': True,
        'referral_code': user.referral_code,
        'share_link': share_link,
        'stats': {
            'total_invitees': total_invitees
        }
    })

@user_bp.route('/referral/bind', methods=['POST'])
@login_required
def bind_referral():
    data = request.get_json(silent=True) or {}
    code = (data.get('referral_code') or '').strip()
    if not code:
        return jsonify({'success': False, 'message': '推荐码不能为空'}), 400

    invitee = user_service.get_user_by_id(session['user_id'])
    if not invitee:
        return jsonify({'success': False, 'message': '用户未找到'}), 404

    referrer = User.query.filter_by(referral_code=code).first()
    if not referrer:
        return jsonify({'success': False, 'message': '无效的推荐码'}), 404

    if referrer.id == invitee.id:
        return jsonify({'success': False, 'message': '不能使用自己的推荐码'}), 400

    # Only bind once per invitee
    existing = Referral.query.filter_by(invitee_user_id=invitee.id).first()
    if existing or invitee.referrer_id:
        return jsonify({'success': False, 'message': '已绑定过推荐人'}), 409

    try:
        invitee.referrer_id = referrer.id
        db.session.add(Referral(referrer_user_id=referrer.id, invitee_user_id=invitee.id))
        # Award points for both sides
        try:
            user_service.add_points(referrer.id, REFERRAL_POINTS_PER_SIDE)
            user_service.add_points(invitee.id, REFERRAL_POINTS_PER_SIDE)
        except Exception as e:
            current_app.logger.warning(f"add_points failed during referral bind: {e}")
        db.session.commit()
        return jsonify({'success': True, 'message': '推荐绑定成功'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"bind_referral error: {e}")
        return jsonify({'success': False, 'message': '绑定失败'}), 500

@user_bp.route('/referral/stats', methods=['GET'])
@login_required
def referral_stats():
    user_id = session['user_id']
    total_invitees = Referral.query.filter_by(referrer_user_id=user_id).count()
    return jsonify({'success': True, 'stats': {'total_invitees': total_invitees}})