import uuid
import json
from flask import Blueprint, request, jsonify, current_app, render_template, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime
from .. import db, csrf
from ..models import User, RechargeOrder, Notification, Feedback
from .admin import admin_required

from app.utils.alipay import get_alipay_client

payment_bp = Blueprint('payment_bp', __name__)

def create_notification(user_id, message, link=None):
    """Creates a new notification for a user using SQLAlchemy."""
    try:
        notification = Notification(user_id=user_id, message=message, link=link)
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to create notification for user {user_id}: {e}")

# In a real app, this might come from a database. For now, using config.
RECHARGE_PACKAGES_CONFIG_KEY = 'RECHARGE_PACKAGES'

@payment_bp.route('/create_recharge_order', methods=['POST'])
@login_required
def create_recharge_order():
    """Creates a new recharge order and returns the order number."""
    user_id = current_user.id

    data = request.get_json()
    package_id = data.get('package_id')
    payment_method = data.get('payment_method') # e.g., 'alipay', 'wechat'

    recharge_packages = current_app.config.get(RECHARGE_PACKAGES_CONFIG_KEY, {})

    if not package_id or package_id not in recharge_packages:
        return jsonify({'success': False, 'message': '无效的套餐'}), 400

    package = recharge_packages[package_id]

    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        todays_order_count = RechargeOrder.query.filter(db.func.date(RechargeOrder.created_at) == today_str).count()
        
        date_part = datetime.now().strftime('%Y%m%d')
        order_number = f"{date_part}-{todays_order_count + 1}"

        new_order = RechargeOrder(
            user_id=user_id,
            order_number=order_number,
            package_name=package['name'],
            amount=package['price'],
            points=package['points'],
            status='PENDING',
            payment_method=payment_method
        )
        db.session.add(new_order)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'order_number': order_number,
            'amount': package['price']
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Database error on order creation: {e}")
        return jsonify({'success': False, 'message': '创建订单失败'}), 500

@payment_bp.route('/initiate_payment', methods=['POST'])
@login_required
def initiate_payment():
    """Receives a request to create an Alipay payment link for an order."""
    user_id = current_user.id

    data = request.get_json()
    order_number = data.get('order_number')
    if not order_number:
        return jsonify({'success': False, 'message': '缺少订单号'}), 400

    order = RechargeOrder.query.filter_by(order_number=order_number, user_id=user_id, status='PENDING').first()

    if not order:
        return jsonify({'success': False, 'message': '订单不存在或已处理'}), 404

    alipay = get_alipay_client()
    return_url = url_for('main.index', _external=True) 
    notify_url = url_for('payment_bp.alipay_notify', _external=True)

    try:
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order.order_number,
            total_amount=float(order.amount),
            subject=f"积分充值 - {order.package_name}",
            return_url=return_url,
            notify_url=notify_url
        )
        payment_url = alipay._gateway + "?" + order_string
        return jsonify({'success': True, 'payment_url': payment_url})
    except Exception as e:
        current_app.logger.error(f"Failed to create Alipay payment URL for order {order_number}: {e}")
        return jsonify({'success': False, 'message': '创建支付链接失败'}), 500

@payment_bp.route('/payment/alipay_notify', methods=['POST'])
@csrf.exempt
def alipay_notify():
    """Alipay asynchronous notification callback."""
    data = request.form.to_dict()
    signature = data.pop("sign")
    current_app.logger.info(f"Received Alipay notification for data: {data}")

    alipay = get_alipay_client()
    success = alipay.verify(data, signature)

    if success and data["trade_status"] in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        order_number = data.get('out_trade_no')
        
        try:
            order = RechargeOrder.query.filter_by(order_number=order_number).first()
            if not order:
                current_app.logger.warning(f"Alipay notify: Order {order_number} not found.")
                return "failure", 404
            
            if order.status == 'COMPLETED':
                current_app.logger.info(f"Alipay notify: Order {order_number} already completed.")
                return "success", 200

            order.status = 'COMPLETED'
            order.payment_method = 'alipay' # Confirm payment method
            order.updated_at = datetime.utcnow()
            
            user = User.query.get(order.user_id)
            if user:
                user.points += order.points
            
            db.session.commit()
            
            create_notification(order.user_id, f"您的订单 {order_number} 已支付成功，{order.points} 积分已到账！")
            current_app.logger.info(f"Order {order_number} processed successfully.")
            return "success", 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Database error processing order {order_number}: {e}")
            return "failure", 500
    else:
        current_app.logger.error(f"Alipay signature verification failed for data: {data}")
        return "failure", 400

@payment_bp.route('/admin/orders')
@admin_required
def admin_orders():
    status = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = RechargeOrder.query.join(User).order_by(RechargeOrder.created_at.desc())

    if status != 'ALL':
        query = query.filter(RechargeOrder.status == status)

    orders_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/orders.html', orders_pagination=orders_pagination, selected_status=status)

@payment_bp.route('/admin/orders/batch_action', methods=['POST'])
@admin_required
def admin_batch_action():
    data = request.get_json()
    order_ids = data.get('order_ids')
    action = data.get('action')

    if not order_ids or not action:
        return jsonify({'success': False, 'message': '缺少参数'}), 400

    if action not in ['delete', 'confirm', 'cancel']:
        return jsonify({'success': False, 'message': '无效的操作'}), 400

    processed_count = 0
    errors = []

    for order_id in order_ids:
        try:
            order = RechargeOrder.query.get(order_id)
            if not order:
                errors.append(f"订单ID {order_id} 不存在")
                continue
            
            if action == 'delete':
                db.session.delete(order)
            elif action == 'confirm':
                if order.status == 'PENDING':
                    user = User.query.get(order.user_id)
                    if user:
                        user.points += order.points
                    order.status = 'COMPLETED'
                    order.updated_at = datetime.utcnow()
                    create_notification(order.user_id, f"您的 {order.amount} 元充值已到账，{order.points} 积分已发放！")
                else:
                    errors.append(f"订单 {order.order_number} 状态不正确，无法确认")
                    continue
            elif action == 'cancel':
                if order.status == 'PENDING':
                    order.status = 'CANCELLED'
                    order.updated_at = datetime.utcnow()
                else:
                    errors.append(f"订单 {order.order_number} 状态不正确，无法取消")
                    continue

            processed_count += 1
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"批量操作失败，订单ID {order_id}，操作: {action}，错误: {e}")
            return jsonify({'success': False, 'message': f'处理订单ID {order_id} 时发生内部错误'}), 500

    db.session.commit()

    message = f"成功处理 {processed_count} 个订单。"
    if errors:
        message += " 部分订单处理失败：" + "；".join(errors)
    
    flash(message, 'success' if not errors else 'warning')
    return jsonify({'success': True, 'message': message})


@payment_bp.route('/admin/feedback')
@admin_required
def admin_feedback_list():
    status_filter = request.args.get('status')
    query = Feedback.query.join(User, Feedback.user_id == User.id).order_by(Feedback.submitted_at.desc())

    if status_filter:
        query = query.filter(Feedback.status == status_filter)

    feedback_list = query.all()
    
    for item in feedback_list:
        if item.image_paths:
            try:
                # Assuming it's a JSON string of a list
                parsed_paths = json.loads(item.image_paths)
                if isinstance(parsed_paths, list):
                    item.image_paths = parsed_paths
                else:
                    # If it's not a list, wrap it in a list
                    item.image_paths = [str(parsed_paths)]
            except json.JSONDecodeError:
                # If it's not a valid JSON, treat it as a single path string
                item.image_paths = [item.image_paths]
        else:
            item.image_paths = []
            
        # Parse replies JSON
        if item.replies_json:
            try:
                item.replies = json.loads(item.replies_json)
            except json.JSONDecodeError:
                item.replies = [] # Corrupted JSON, show empty
        else:
            item.replies = []

    return render_template('admin/feedback.html', feedback=feedback_list, status_filter=status_filter)

@payment_bp.route('/admin/feedback/<int:feedback_id>/status', methods=['POST'])
@admin_required
def admin_feedback_update_status(feedback_id: int):
    new_status = request.form.get('status', '').strip().lower()
    if new_status not in {'new', 'in_progress', 'resolved', 'archived'}:
        flash('无效的状态值', 'danger')
        return redirect(url_for('payment_bp.admin_feedback_list'))

    try:
        feedback_item = Feedback.query.get(feedback_id)
        if not feedback_item:
            flash('反馈不存在或已被删除', 'warning')
        else:
            feedback_item.status = new_status
            db.session.commit()
            flash('状态已更新', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating feedback {feedback_id} status: {e}")
        flash('更新状态时发生数据库错误', 'danger')
    
    return redirect(url_for('payment_bp.admin_feedback_list'))

@payment_bp.route('/admin/feedback/<int:feedback_id>/reply', methods=['POST'])
@admin_required
def admin_feedback_reply(feedback_id: int):
    reply_text = (request.form.get('reply') or '').strip()
    if not reply_text:
        flash('回复内容不能为空', 'warning')
        return redirect(url_for('payment_bp.admin_feedback_list'))

    try:
        feedback_item = Feedback.query.get(feedback_id)
        if not feedback_item or not feedback_item.user_id:
            flash('反馈不存在或无归属用户', 'danger')
            return redirect(url_for('payment_bp.admin_feedback_list'))

        # Save the reply to the feedback item
        current_replies = json.loads(feedback_item.replies_json or '[]')
        new_reply = {
            'message': reply_text,
            'timestamp': datetime.utcnow().isoformat(),
            'admin_id': current_user.id,
            'admin_name': current_user.username or current_user.email
        }
        current_replies.append(new_reply)
        feedback_item.replies_json = json.dumps(current_replies)

        create_notification(feedback_item.user_id, reply_text)
        
        if feedback_item.status == 'new':
            feedback_item.status = 'in_progress'
        db.session.commit()
        
        flash('已发送消息给用户', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error replying feedback {feedback_id}: {e}")
        flash('发送消息失败：数据库错误', 'danger')

    return redirect(url_for('payment_bp.admin_feedback_list'))

@payment_bp.route('/admin/feedback/<int:feedback_id>/delete', methods=['POST'])
@admin_required
def admin_feedback_delete(feedback_id: int):
    try:
        feedback_item = Feedback.query.get(feedback_id)
        if not feedback_item:
            return jsonify({'success': False, 'error': 'Feedback not found'}), 404
        
        db.session.delete(feedback_item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Feedback deleted successfully'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting feedback {feedback_id}: {e}")
        return jsonify({'success': False, 'error': 'Database error during deletion'}), 500

@payment_bp.route('/admin/notify', methods=['GET', 'POST'])
@admin_required
def admin_notify():
    if request.method == 'GET':
        return render_template('admin/notify.html')

    target = request.form.get('target', 'all').strip()
    email = request.form.get('email', '').strip()
    message = request.form.get('message', '').strip()

    if not message:
        flash('消息内容不能为空', 'warning')
        return redirect(url_for('payment_bp.admin_notify'))

    try:
        user_ids = []
        if target == 'all':
            user_ids = [user.id for user in User.query.all()]
        elif email:
            user = User.query.filter_by(email=email).first()
            if not user:
                flash('指定邮箱的用户不存在', 'danger')
                return redirect(url_for('payment_bp.admin_notify'))
            user_ids = [user.id]
        else:
            flash('请输入目标用户邮箱', 'warning')
            return redirect(url_for('payment_bp.admin_notify'))

        created = 0
        for uid in user_ids:
            try:
                create_notification(uid, message)
                created += 1
            except Exception as e:
                current_app.logger.error(f"Failed to notify user {uid}: {e}")
        
        flash(f'已发送通知给 {created} 位用户', 'success')
    except Exception as e:
        current_app.logger.error(f"Broadcast notify failed: {e}")
        flash('发送失败：数据库错误', 'danger')

    return redirect(url_for('payment_bp.admin_notify'))

@payment_bp.route('/admin/points', methods=['GET'])
@admin_required
def admin_points():
    q = request.args.get('q', '').strip()
    query = User.query.order_by(User.created_at.desc())

    if q:
        like_pattern = f"%{q}%"
        query = query.filter(db.or_(User.email.like(like_pattern), User.username.like(like_pattern)))

    users = query.all()
    total_user_count = User.query.count()
    return render_template('admin/points.html', users=users, q=q, total_user_count=total_user_count)

@payment_bp.route('/admin/points/grant', methods=['POST'])
@admin_required
def admin_points_grant():
    try:
        amount = int(request.form.get('amount', '0').strip())
    except ValueError:
        amount = 0

    if amount <= 0:
        flash('积分数量必须为正整数', 'warning')
        return redirect(url_for('payment_bp.admin_points'))

    reason = request.form.get('reason', '').strip()
    target = request.form.get('target', 'selected').strip()
    
    user_ids = []
    try:
        if target == 'all':
            user_ids = [user.id for user in User.query.all()]
        elif target == 'emails':
            emails_raw = request.form.get('emails', '').strip()
            emails = [e.strip() for e in emails_raw.split(',') if e.strip()]
            if not emails:
                flash('请填写至少一个邮箱', 'warning')
                return redirect(url_for('payment_bp.admin_points'))
            users = User.query.filter(User.email.in_(emails)).all()
            user_ids = [user.id for user in users]
            if not user_ids:
                flash('未找到对应邮箱的用户', 'warning')
        elif target == 'selected':
            selected_ids_raw = request.form.get('selected_ids', '').strip()
            user_ids = [int(x) for x in selected_ids_raw.split(',') if x.strip()]
        else:
            flash('无效的目标类型', 'danger')
    except (ValueError, TypeError):
        flash('无效的用户ID格式', 'danger')
        return redirect(url_for('payment_bp.admin_points'))

    if not user_ids:
        flash('未选择任何用户', 'warning')
        return redirect(url_for('payment_bp.admin_points'))

    try:
        User.query.filter(User.id.in_(user_ids)).update({'points': User.points + amount}, synchronize_session=False)
        db.session.commit()

        sent = 0
        for uid in user_ids:
            try:
                msg = f"系统赠送 {amount} 积分" + (f"：{reason}" if reason else '')
                create_notification(uid, msg)
                sent += 1
            except Exception as e:
                current_app.logger.error(f"Grant points notify failed for {uid}: {e}")
        
        flash(f'已为 {len(user_ids)} 位用户增加 {amount} 积分（通知成功 {sent}）', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Grant points update failed: {e}")
        flash('加积分失败：数据库错误', 'danger')

    return redirect(url_for('payment_bp.admin_points'))