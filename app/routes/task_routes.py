from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.services import task_service
import datetime

# 创建一个名为 'tasks' 的蓝图
task_bp = Blueprint('tasks', __name__, url_prefix='/tasks')

@task_bp.route('/', methods=['GET'])
@login_required
def get_tasks():
    """
    获取当前登录用户的任务列表，支持分页。
    查询参数:
        - page (int): 页码，默认为1。
        - per_page (int): 每页数量，默认为10。
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    user_id = current_user.id
    tasks = task_service.get_tasks_by_user(user_id, page, per_page)
    
    # 为了在 JSON 响应中正确显示日期，需要将其格式化为字符串
    for task in tasks:
        if 'updated_at' in task and isinstance(task['updated_at'], datetime.datetime):
            task['updated_at'] = task['updated_at'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify(tasks)

@task_bp.route('/', methods=['POST'])
@login_required
def create_task():
    """
    为当前用户创建一个新任务。
    需要JSON负载: {"task_name": "我的任务", "result_data": {...}}
    """
    data = request.get_json()
    if not data or 'task_name' not in data or 'result_data' not in data:
        return jsonify({"error": "请求体中缺少 'task_name' 或 'result_data' 字段"}), 400

    task_name = data['task_name']
    result_data = data['result_data']
    if not isinstance(task_name, str) or not task_name.strip():
        return jsonify({"error": "任务名称无效"}), 400
    user_id = current_user.id
    
    try:
        task_id = task_service.create_task(user_id, task_name.strip(), result_data)
        return jsonify({"message": "任务保存成功", "task_id": task_id}), 201
    except ValueError as e:
        # 由 service 层捕获的 UNIQUE 约束冲突
        return jsonify({"error": str(e)}), 409 # 409 Conflict
    except Exception as e:
        # 捕获未预期错误，避免 500 泄露
        return jsonify({"error": f"保存失败: {str(e)}"}), 500

@task_bp.route('/<int:task_id>', methods=['GET'])
@login_required
def get_task_detail(task_id):
    """
    获取单个任务的详细信息。
    """
    user_id = current_user.id
    task = task_service.get_task_by_id(task_id, user_id)
    
    if task:
        # 日期时间字段同样需要格式化
        if 'created_at' in task and isinstance(task['created_at'], datetime.datetime):
            task['created_at'] = task['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        if 'updated_at' in task and isinstance(task['updated_at'], datetime.datetime):
            task['updated_at'] = task['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(task)
    else:
        return jsonify({"error": "找不到指定的任务或无访问权限"}), 404

@task_bp.route('/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    """
    更新一个已存在的任务。
    需要JSON负载: {"result_data": {...}}
    """
    data = request.get_json()
    if not data or 'result_data' not in data:
        return jsonify({"error": "请求体中缺少 'result_data' 字段"}), 400

    new_result_data = data['result_data']
    user_id = current_user.id
    
    rows_affected = task_service.update_task(task_id, user_id, new_result_data)
    
    if rows_affected > 0:
        return jsonify({"message": "任务更新成功"})
    else:
        return jsonify({"error": "找不到要更新的任务或无访问权限"}), 404

@task_bp.route('/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    """
    删除一个任务。
    """
    user_id = current_user.id
    rows_affected = task_service.delete_task(task_id, user_id)
    
    if rows_affected > 0:
        return jsonify({"message": "任务删除成功"})
    else:
        return jsonify({"error": "找不到要删除的任务或无访问权限"}), 404 