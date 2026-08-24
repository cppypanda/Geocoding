from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func, or_

from ..models import LocationType, User, GeocodingTask, AddressLog, Task, ErrorRecord
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

@admin_bp.route('/geocoding_logs')
@admin_required
def geocoding_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    tasks_pagination = GeocodingTask.query.order_by(GeocodingTask.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/geocoding_logs.html', tasks_pagination=tasks_pagination)

@admin_bp.route('/geocoding_logs/<int:task_id>')
@admin_required
def geocoding_log_details(task_id):
    task = GeocodingTask.query.get_or_404(task_id)
    page = request.args.get('page', 1, type=int)
    per_page = 50
    addresses_pagination = AddressLog.query.filter_by(task_id=task.id).order_by(AddressLog.id.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/geocoding_log_details.html', task=task, addresses_pagination=addresses_pagination)

@admin_bp.route('/user_tasks')
@admin_required
def user_tasks():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    tasks_pagination = Task.query.order_by(Task.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/user_tasks.html', tasks_pagination=tasks_pagination)

@admin_bp.route('/user_tasks/<int:task_id>')
@admin_required
def user_task_details(task_id):
    task = Task.query.get_or_404(task_id)
    return render_template('admin/user_task_details.html', task=task)


@admin_bp.route('/errors')
@admin_required
def error_center():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'open').strip()
    severity_filter = request.args.get('severity', '').strip().lower()
    keyword = request.args.get('q', '').strip()

    query = ErrorRecord.query
    if status_filter in {'open', 'in_progress', 'resolved', 'ignored'}:
        query = query.filter(ErrorRecord.status == status_filter)
    if severity_filter in {'warning', 'error', 'critical'}:
        query = query.filter(ErrorRecord.severity == severity_filter)
    if keyword:
        pattern = f'%{keyword}%'
        query = query.filter(or_(
            ErrorRecord.message.ilike(pattern),
            ErrorRecord.exception_type.ilike(pattern),
            ErrorRecord.request_path.ilike(pattern),
            ErrorRecord.source.ilike(pattern),
            ErrorRecord.fingerprint.ilike(pattern),
        ))

    pagination = query.order_by(ErrorRecord.last_seen_at.desc()).paginate(
        page=page, per_page=30, error_out=False
    )
    status_counts = dict(
        db.session.query(ErrorRecord.status, func.count(ErrorRecord.id))
        .group_by(ErrorRecord.status)
        .all()
    )
    total_occurrences = db.session.query(func.coalesce(func.sum(ErrorRecord.occurrence_count), 0)).scalar()

    return render_template(
        'admin/errors.html',
        pagination=pagination,
        status_filter=status_filter,
        severity_filter=severity_filter,
        keyword=keyword,
        status_counts=status_counts,
        total_occurrences=total_occurrences,
    )


@admin_bp.route('/errors/<int:error_id>')
@admin_required
def error_detail(error_id):
    error_record = ErrorRecord.query.get_or_404(error_id)
    return render_template('admin/error_detail.html', error=error_record)


@admin_bp.route('/errors/<int:error_id>/status', methods=['POST'])
@admin_required
def update_error_status(error_id):
    error_record = ErrorRecord.query.get_or_404(error_id)
    status = request.form.get('status', '').strip()
    if status not in {'open', 'in_progress', 'resolved', 'ignored'}:
        flash('无效的错误处理状态。', 'danger')
        return redirect(url_for('admin.error_detail', error_id=error_id))

    error_record.status = status
    error_record.resolution_notes = request.form.get('resolution_notes', '').strip()[:10000] or None
    if status in {'resolved', 'ignored'}:
        error_record.resolved_at = datetime.utcnow()
        error_record.resolved_by_id = current_user.id
    else:
        error_record.resolved_at = None
        error_record.resolved_by_id = None
    db.session.commit()
    flash('错误状态已更新。', 'success')
    return redirect(url_for('admin.error_detail', error_id=error_id))
