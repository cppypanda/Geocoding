from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from ..models import LocationType, User
from .. import db
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('您没有权限访问此页面。', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    return render_template('admin/dashboard.html')

@admin_bp.route('/suffixes')
@admin_required
def manage_suffixes():
    suffixes = LocationType.query.all()
    return render_template('admin/suffixes.html', suffixes=suffixes)

@admin_bp.route('/suffixes/add', methods=['POST'])
@admin_required
def add_suffix():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': '无效的请求或数据格式不正确。'}), 400
        
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'message': '后缀名称不能为空。'}), 400
    
    existing = LocationType.query.filter_by(name=name).first()
    if existing:
        return jsonify({'success': False, 'message': '该后缀已存在。'}), 400

    new_suffix = LocationType(
        name=name,
        status='approved',
        source='admin_added',
        usage_count=0
    )
    db.session.add(new_suffix)
    db.session.commit()
    return jsonify({'success': True, 'message': '后缀添加成功。', 'suffix': {'id': new_suffix.id, 'name': new_suffix.name, 'status': new_suffix.status, 'source': new_suffix.source}})

@admin_bp.route('/suffixes/update', methods=['POST'])
@admin_required
def update_suffix():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': '无效的请求或数据格式不正确。'}), 400

    suffix_id = data.get('id')
    name = data.get('name')
    status = data.get('status')

    if not suffix_id or not name or not status:
        return jsonify({'success': False, 'message': '缺少必要参数。'}), 400

    suffix = LocationType.query.get(suffix_id)
    if not suffix:
        return jsonify({'success': False, 'message': '未找到指定的后缀。'}), 404
    
    # 检查新名称是否已被其他后缀占用
    existing_with_same_name = LocationType.query.filter(
        LocationType.name == name,
        LocationType.id != suffix_id
    ).first()

    if existing_with_same_name:
        return jsonify({'success': False, 'message': f'名称为 "{name}" 的后缀已存在。'}), 409

    suffix.name = name
    suffix.status = status
    db.session.commit()
    return jsonify({'success': True, 'message': '后缀更新成功。'})

@admin_bp.route('/suffixes/delete', methods=['POST'])
@admin_required
def delete_suffix():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': '无效的请求或数据格式不正确。'}), 400
        
    suffix_id = data.get('id')
    if not suffix_id:
        return jsonify({'success': False, 'message': '缺少ID。'}), 400

    suffix = LocationType.query.get(suffix_id)
    if not suffix:
        return jsonify({'success': False, 'message': '未找到指定的后缀。'}), 404

    db.session.delete(suffix)
    db.session.commit()
    return jsonify({'success': True, 'message': '后缀删除成功。'})
