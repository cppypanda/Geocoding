import uuid
import json
import secrets
import string
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify, current_app, render_template, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func, update
from datetime import datetime, timedelta, timezone
from .. import db, csrf
from ..models import User, RechargeOrder, Notification, Feedback, RechargeCard
from ..services.payment_service import (
    PaymentConfirmation,
    PaymentProviderError,
    create_yungou_alipay_payment,
    get_yungou_config,
    parse_yungou_notify,
    query_yungou_order,
)
from ..utils.alipay import get_alipay_client
from .admin import admin_required

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

def generate_card_code(length=16):
    """Generate a random alphanumeric card code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _external_payment_url(endpoint):
    configured_base = (current_app.config.get('PAYMENT_PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if configured_base:
        return f"{configured_base}{url_for(endpoint)}"
    return url_for(endpoint, _external=True, _scheme='https' if current_app.config.get('SESSION_COOKIE_SECURE') else None)


def _order_payload(order):
    return {
        'order_number': order.order_number,
        'package_name': order.package_name,
        'amount': float(order.amount),
        'points': order.points,
        'status': order.status,
        'payment_method': order.payment_method,
        'payment_url': order.payment_url,
        'paid_at': order.paid_at.isoformat() if order.paid_at else None,
    }


def _parse_paid_at(value):
    if not value:
        return datetime.utcnow()
    text = str(value).strip().replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        # 支付宝与 YunGouOS 的无时区时间均按北京时间返回。
        return parsed - timedelta(hours=8)
    except ValueError:
        return datetime.utcnow()


def _complete_recharge_order(confirmation: PaymentConfirmation):
    """Atomically mark an order paid and grant its points exactly once."""
    order = (
        RechargeOrder.query
        .filter_by(order_number=confirmation.order_number)
        .with_for_update()
        .first()
    )
    if not order:
        raise PaymentProviderError('支付订单不存在')
    if order.status == 'COMPLETED':
        return order, True

    try:
        expected = Decimal(str(order.amount)).quantize(Decimal('0.01'))
        received = Decimal(str(confirmation.amount_cny)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError) as exc:
        raise PaymentProviderError('支付金额无效') from exc
    if expected != received:
        raise PaymentProviderError('支付金额与订单不匹配')

    user = db.session.get(User, order.user_id)
    if not user:
        raise PaymentProviderError('支付订单所属用户不存在')

    user.points = (user.points or 0) + order.points
    order.status = 'COMPLETED'
    order.provider_trade_no = confirmation.provider_trade_no
    order.buyer_logon_id = confirmation.buyer_logon_id
    order.notify_payload = confirmation.notify_payload
    order.paid_at = _parse_paid_at(confirmation.paid_at)
    order.updated_at = datetime.utcnow()
    db.session.add(Notification(
        user_id=user.id,
        message=f"您的 {order.amount:.2f} 元充值已到账，{order.points} 积分已发放！",
    ))
    db.session.commit()
    return order, False


@payment_bp.route('/api/pay/recharge/setup', methods=['GET'])
def recharge_payment_setup():
    yungou = get_yungou_config(
        current_app.config,
        _external_payment_url('payment_bp.yungouos_notify'),
    )
    alipay_ready = all(current_app.config.get(name) for name in (
        'ALIPAY_APP_ID', 'ALIPAY_PRIVATE_KEY', 'ALIPAY_PUBLIC_KEY'
    ))
    return jsonify({
        'success': True,
        'ready': bool(yungou or alipay_ready),
        'provider': 'yungouos' if yungou else ('alipay' if alipay_ready else None),
    })


@payment_bp.route('/api/pay/recharge/create', methods=['POST'])
@login_required
def create_recharge_payment():
    data = request.get_json(silent=True) or {}
    package_id = (data.get('package_id') or '').strip()
    packages = current_app.config.get('RECHARGE_PACKAGES', {})
    package = packages.get(package_id)
    if not package:
        return jsonify({'success': False, 'message': '充值套餐无效'}), 400

    yungou_notify_url = _external_payment_url('payment_bp.yungouos_notify')
    yungou = get_yungou_config(current_app.config, yungou_notify_url)
    alipay_ready = all(current_app.config.get(name) for name in (
        'ALIPAY_APP_ID', 'ALIPAY_PRIVATE_KEY', 'ALIPAY_PUBLIC_KEY'
    ))
    if not yungou and not alipay_ready:
        return jsonify({'success': False, 'message': '支付服务尚未配置'}), 503

    provider = 'yungouos' if yungou else 'alipay'
    order = RechargeOrder(
        user_id=current_user.id,
        order_number=f"GEO{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(100000):05d}",
        package_name=package['name'],
        amount=float(package['price']),
        points=int(package['points']),
        status='PENDING',
        payment_method=provider,
    )
    db.session.add(order)
    try:
        db.session.flush()
        subject = f"GeoCoUI {package['name']} {package['points']}积分"
        if yungou:
            payment_url = create_yungou_alipay_payment(
                order_number=order.order_number,
                amount_cny=order.amount,
                subject=subject,
                points=order.points,
                config=yungou,
            )
        else:
            alipay = get_alipay_client()
            order_string = alipay.api_alipay_trade_page_pay(
                subject=subject,
                out_trade_no=order.order_number,
                total_amount=f"{order.amount:.2f}",
                return_url=url_for('main.index', _external=True),
                notify_url=(current_app.config.get('ALIPAY_NOTIFY_URL') or _external_payment_url('payment_bp.alipay_notify')),
            )
            payment_url = f"{alipay._gateway}?{order_string}"
        order.payment_url = payment_url
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error('创建充值支付订单失败: %s', exc, exc_info=True)
        message = str(exc) if isinstance(exc, PaymentProviderError) else '创建支付订单失败，请稍后重试'
        return jsonify({'success': False, 'message': message}), 502

    return jsonify({'success': True, 'order': _order_payload(order)})


@payment_bp.route('/api/pay/recharge/order', methods=['GET'])
@login_required
def recharge_payment_order():
    order_number = (request.args.get('order_number') or '').strip()
    order = RechargeOrder.query.filter_by(order_number=order_number, user_id=current_user.id).first()
    if not order:
        return jsonify({'success': False, 'message': '支付订单不存在'}), 404

    warning = None
    if order.status == 'PENDING':
        try:
            confirmation = None
            if order.payment_method == 'yungouos':
                config = get_yungou_config(
                    current_app.config,
                    _external_payment_url('payment_bp.yungouos_notify'),
                )
                if config:
                    confirmation = query_yungou_order(order.order_number, config)
            elif order.payment_method == 'alipay':
                result = get_alipay_client().api_alipay_trade_query(out_trade_no=order.order_number)
                if isinstance(result, dict) and result.get('trade_status') in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
                    confirmation = PaymentConfirmation(
                        order_number=order.order_number,
                        amount_cny=float(result.get('total_amount') or result.get('receipt_amount') or 0),
                        paid=True,
                        provider_trade_no=result.get('trade_no'),
                        buyer_logon_id=result.get('buyer_logon_id'),
                        paid_at=result.get('send_pay_date'),
                        notify_payload=json.dumps(result, ensure_ascii=False),
                    )
            if confirmation and confirmation.paid:
                order, _ = _complete_recharge_order(confirmation)
        except Exception as exc:
            db.session.rollback()
            warning = '支付状态查询暂时不可用，将继续等待支付回调'
            current_app.logger.warning('查询充值订单 %s 失败: %s', order.order_number, exc)

    user = db.session.get(User, current_user.id)
    return jsonify({
        'success': True,
        'order': _order_payload(order),
        'total_points': user.points if user else None,
        'warning': warning,
    })


@payment_bp.route('/api/pay/yungouos/notify', methods=['POST'])
@csrf.exempt
def yungouos_notify():
    def respond(text):
        return current_app.response_class(text, status=200, mimetype='text/plain')

    config = get_yungou_config(
        current_app.config,
        _external_payment_url('payment_bp.yungouos_notify'),
    )
    if not config:
        current_app.logger.warning('YunGouOS 回调失败：支付服务未配置')
        return respond('fail')
    try:
        confirmation = parse_yungou_notify(request.form.to_dict(flat=True), config)
        if confirmation.paid:
            _complete_recharge_order(confirmation)
        return respond('SUCCESS')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('YunGouOS 回调失败: %s', exc)
        return respond('fail')


@payment_bp.route('/payment/alipay_notify', methods=['POST'])
@csrf.exempt
def alipay_notify():
    def respond(text):
        return current_app.response_class(text, status=200, mimetype='text/plain')

    data = request.form.to_dict(flat=True)
    signature = data.pop('sign', '')
    try:
        if data.get('app_id') and data['app_id'] != current_app.config.get('ALIPAY_APP_ID'):
            raise PaymentProviderError('支付回调应用 ID 不匹配')
        if not signature or not get_alipay_client().verify(data, signature):
            raise PaymentProviderError('支付回调签名验证失败')
        status = data.get('trade_status')
        if status in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
            _complete_recharge_order(PaymentConfirmation(
                order_number=data.get('out_trade_no', ''),
                amount_cny=float(data.get('total_amount') or data.get('receipt_amount') or 0),
                paid=True,
                provider_trade_no=data.get('trade_no'),
                buyer_logon_id=data.get('buyer_logon_id'),
                paid_at=data.get('gmt_payment'),
                notify_payload=json.dumps(data, ensure_ascii=False),
            ))
        elif status == 'TRADE_CLOSED':
            order = RechargeOrder.query.filter_by(order_number=data.get('out_trade_no', '')).first()
            if order and order.status == 'PENDING':
                order.status = 'CANCELLED'
                order.notify_payload = json.dumps(data, ensure_ascii=False)
                db.session.commit()
        return respond('success')
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning('支付宝回调失败: %s', exc)
        return respond('fail')

@payment_bp.route('/redeem_card', methods=['POST'])
@login_required
def redeem_card():
    """User redeems a recharge card code for points."""
    data = request.get_json()
    code = (data.get('code') or '').strip().upper()

    if not code:
        return jsonify({'success': False, 'message': '请输入卡密'}), 400

    card = RechargeCard.query.filter_by(code=code).first()

    if not card:
        return jsonify({'success': False, 'message': '卡密无效'}), 404

    if card.is_used:
        return jsonify({'success': False, 'message': '该卡密已被使用'}), 400

    if card.expires_at and card.expires_at < datetime.utcnow():
        return jsonify({'success': False, 'message': '该卡密已过期'}), 400

    try:
        claimed = db.session.execute(
            update(RechargeCard)
            .where(RechargeCard.id == card.id, RechargeCard.is_used.is_(False))
            .values(is_used=True, used_by=current_user.id, used_at=datetime.utcnow())
        )
        if claimed.rowcount != 1:
            db.session.rollback()
            return jsonify({'success': False, 'message': '该卡密已被使用'}), 409
        db.session.execute(
            update(User)
            .where(User.id == current_user.id)
            .values(points=func.coalesce(User.points, 0) + card.points)
        )
        db.session.add(Notification(
            user_id=current_user.id,
            message=f"卡密兑换成功，{card.points} 积分已到账！",
        ))
        db.session.commit()
        total_points = db.session.get(User, current_user.id).points

        return jsonify({
            'success': True,
            'message': f'兑换成功！获得 {card.points} 积分',
            'points_added': card.points,
            'total_points': total_points
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Card redemption failed for code {code}: {e}")
        return jsonify({'success': False, 'message': '兑换失败，请稍后重试'}), 500

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
                    user = db.session.get(User, order.user_id)
                    if user:
                        user.points += order.points
                    order.status = 'COMPLETED'
                    order.updated_at = datetime.utcnow()
                    db.session.add(Notification(
                        user_id=order.user_id,
                        message=f"您的 {order.amount} 元充值已到账，{order.points} 积分已发放！",
                    ))
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


@payment_bp.route('/admin/cards', methods=['GET', 'POST'])
@admin_required
def admin_cards():
    """Admin page to generate and manage recharge cards."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'generate':
            try:
                count = int(request.form.get('count', '1').strip())
                points = int(request.form.get('points', '100').strip())
                expires_days = request.form.get('expires_days', '').strip()
            except ValueError:
                flash('参数格式错误', 'danger')
                return redirect(url_for('payment_bp.admin_cards'))

            if count < 1 or count > 1000:
                flash('单次生成数量必须在 1-1000 之间', 'warning')
                return redirect(url_for('payment_bp.admin_cards'))

            if points < 1:
                flash('积分必须大于 0', 'warning')
                return redirect(url_for('payment_bp.admin_cards'))

            expires_at = None
            if expires_days:
                try:
                    days = int(expires_days)
                    if days > 0:
                        expires_at = datetime.utcnow() + timedelta(days=days)
                except ValueError:
                    pass

            generated = []
            for _ in range(count):
                for _attempt in range(10):
                    code = generate_card_code()
                    existing = RechargeCard.query.filter_by(code=code).first()
                    if not existing:
                        break
                else:
                    flash('卡密生成失败，请重试', 'danger')
                    return redirect(url_for('payment_bp.admin_cards'))

                card = RechargeCard(
                    code=code,
                    points=points,
                    expires_at=expires_at
                )
                db.session.add(card)
                generated.append(code)

            try:
                db.session.commit()
                flash(f'成功生成 {len(generated)} 张卡密', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Card generation failed: {e}")
                flash('生成卡密时发生数据库错误', 'danger')

            return redirect(url_for('payment_bp.admin_cards'))

        elif action == 'delete':
            card_id = request.form.get('card_id')
            if card_id:
                card = RechargeCard.query.get(card_id)
                if card:
                    db.session.delete(card)
                    db.session.commit()
                    flash('卡密已删除', 'success')
                else:
                    flash('卡密不存在', 'warning')
            return redirect(url_for('payment_bp.admin_cards'))

    status_filter = request.args.get('status', 'ALL')
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = RechargeCard.query.outerjoin(User, RechargeCard.used_by == User.id).order_by(RechargeCard.created_at.desc())

    if status_filter == 'unused':
        query = query.filter(RechargeCard.is_used == False)
    elif status_filter == 'used':
        query = query.filter(RechargeCard.is_used == True)

    cards_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template('admin/cards.html', cards_pagination=cards_pagination, selected_status=status_filter, now=datetime.utcnow())

@payment_bp.route('/admin/cards/export')
@admin_required
def admin_cards_export():
    """Export unused cards as CSV."""
    import csv
    import io

    status = request.args.get('status', 'unused')
    query = RechargeCard.query.order_by(RechargeCard.created_at.desc())
    if status == 'unused':
        query = query.filter_by(is_used=False)
    elif status == 'used':
        query = query.filter_by(is_used=True)

    cards = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['卡密', '积分', '状态', '创建时间', '过期时间'])
    for card in cards:
        writer.writerow([
            card.code,
            card.points,
            '已使用' if card.is_used else '未使用',
            card.created_at.strftime('%Y-%m-%d %H:%M:%S') if card.created_at else '',
            card.expires_at.strftime('%Y-%m-%d %H:%M:%S') if card.expires_at else '永不过期'
        ])

    output.seek(0)
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=recharge_cards_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        }
    )


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
        query = query.filter(db.or_(
            User.email.like(like_pattern),
            User.username.like(like_pattern),
            User.phone.like(like_pattern),
            User.urpa_user_id.like(like_pattern),
        ))

    users = query.all()
    total_user_count = User.query.count()
    urpa_linked_count = User.query.filter(User.urpa_user_id.isnot(None)).count()
    return render_template(
        'admin/points.html',
        users=users,
        q=q,
        total_user_count=total_user_count,
        urpa_linked_count=urpa_linked_count,
    )

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
