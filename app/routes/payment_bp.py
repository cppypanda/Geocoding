import uuid
from flask import Blueprint, request, jsonify, session, current_app, render_template, abort, flash, redirect, url_for
from datetime import datetime
import sqlite3

payment_bp = Blueprint('payment_bp', __name__)

def get_db_connection():
    """Gets a database connection for user_data.db."""
    db_path = current_app.config['USER_DB_NAME']
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def create_notification(user_id, message, link=None):
    """Creates a new notification for a user."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO notifications (user_id, message, link) VALUES (?, ?, ?)",
            (user_id, message, link)
        )
        conn.commit()
    except sqlite3.Error as e:
        current_app.logger.error(f"Failed to create notification for user {user_id}: {e}")
    finally:
        if conn:
            conn.close()

# Define the recharge packages. In a real app, this might come from a database.
RECHARGE_PACKAGES = {
    'pkg_10': {'name': '入门套餐', 'points': 1000, 'price': 10.00},
    'pkg_50': {'name': '标准套餐', 'points': 5500, 'price': 50.00},
    'pkg_100': {'name': '高级套餐', 'points': 12000, 'price': 100.00},
}

@payment_bp.route('/create_recharge_order', methods=['POST'])
def create_recharge_order():
    """
    Creates a new recharge order and returns the order number.
    """
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': '用户未登录'}), 401

    data = request.get_json()
    package_id = data.get('package_id')

    if not package_id or package_id not in RECHARGE_PACKAGES:
        return jsonify({'success': False, 'message': '无效的套餐'}), 400

    package = RECHARGE_PACKAGES[package_id]

    # Generate a simplified, easy-to-read order number
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Get the count of orders for today to generate the sequence number
        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(id) FROM recharge_orders WHERE DATE(created_at) = ?", (today_str,))
        todays_order_count = cursor.fetchone()[0]
        
        # Format: YYYYMMDD-sequence
        date_part = datetime.now().strftime('%Y%m%d')
        order_number = f"{date_part}-{todays_order_count + 1}"

        cursor.execute(
            """
            INSERT INTO recharge_orders (user_id, order_number, package_name, amount, points, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, order_number, package['name'], package['price'], package['points'], 'PENDING')
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.close()
        current_app.logger.error(f"Database error on order creation: {e}")
        return jsonify({'success': False, 'message': '创建订单失败'}), 500
    finally:
        if conn:
            conn.close()

    return jsonify({
        'success': True,
        'order_number': order_number,
        'amount': package['price']
    })

@payment_bp.route('/admin/orders')
def admin_orders():
    if session.get('is_admin') != 1:
        abort(403) # Forbidden access

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Fetch pending orders along with user information
        cursor.execute("""
            SELECT o.id, o.order_number, o.package_name, o.amount, o.points, o.status, o.created_at, u.username, u.email
            FROM recharge_orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.status = 'PENDING'
            ORDER BY o.created_at DESC
        """)
        pending_orders_raw = cursor.fetchall()

        # Convert timestamp strings to datetime objects
        pending_orders = []
        for order in pending_orders_raw:
            order_dict = dict(order)
            if order_dict.get('created_at'):
                try:
                    # SQLite stores timestamp as string, convert it to datetime object
                    order_dict['created_at'] = datetime.strptime(order_dict['created_at'].split('.')[0], '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    # Handle cases where the format is unexpected or it's not a string
                    pass # Keep the original value if conversion fails
            pending_orders.append(order_dict)

    finally:
        if conn:
            conn.close()
    
    return render_template('admin/orders.html', orders=pending_orders)

@payment_bp.route('/admin/confirm_order/<int:order_id>', methods=['POST'])
def admin_confirm_order(order_id):
    if session.get('is_admin') != 1:
        abort(403)

    conn = get_db_connection()
    try:
        # Transaction-like control
        cursor = conn.cursor()
        
        # 1. Get order details and lock the row for update
        cursor.execute("SELECT user_id, points, status, amount FROM recharge_orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()

        if not order:
            flash('订单不存在', 'danger')
            return redirect(url_for('payment_bp.admin_orders'))

        if order['status'] != 'PENDING':
            flash('订单状态不正确，可能已被处理', 'warning')
            return redirect(url_for('payment_bp.admin_orders'))
            
        # 2. Update user points
        cursor.execute("UPDATE users SET points = points + ? WHERE id = ?", (order['points'], order['user_id']))
        
        # 3. Update order status
        cursor.execute("UPDATE recharge_orders SET status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
        
        conn.commit()

        # 4. Create a notification for the user
        try:
            notification_message = f"您的 {order['amount']} 元充值已到账，{order['points']} 积分已发放！"
            create_notification(order['user_id'], notification_message)
        except Exception as e:
            current_app.logger.error(f"Failed to create notification after order confirmation for order {order_id}: {e}")
        
        flash(f"订单 {order_id} 已确认，积分已成功充值!", 'success')

    except sqlite3.Error as e:
        if conn:
            conn.rollback() # Rollback on error
        current_app.logger.error(f"Error confirming order {order_id}: {e}")
        flash('处理订单时发生数据库错误', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('payment_bp.admin_orders'))

@payment_bp.route('/admin/cancel_order/<int:order_id>', methods=['POST'])
def admin_cancel_order(order_id):
    if session.get('is_admin') != 1:
        abort(403)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Check if the order exists and is pending
        cursor.execute("SELECT status FROM recharge_orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()

        if not order:
            flash('订单不存在', 'danger')
            return redirect(url_for('payment_bp.admin_orders'))

        if order['status'] != 'PENDING':
            flash('订单状态不正确，无法取消', 'warning')
            return redirect(url_for('payment_bp.admin_orders'))
            
        # Update order status to CANCELLED
        cursor.execute("UPDATE recharge_orders SET status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))
        conn.commit()
        flash(f"订单 {order_id} 已成功取消。", 'info')

    except sqlite3.Error as e:
        current_app.logger.error(f"Error cancelling order {order_id}: {e}")
        flash('处理订单时发生数据库错误', 'danger')
    finally:
        if conn:
            conn.close()
            
    return redirect(url_for('payment_bp.admin_orders')) 

# ------------------ Admin Feedback Management ------------------

@payment_bp.route('/admin/feedback')
def admin_feedback_list():
    if session.get('is_admin') != 1:
        abort(403)

    status_filter = request.args.get('status')  # optional: 'new', 'in_progress', 'resolved', 'archived'

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        base_query = (
            """
            SELECT f.id, f.description, f.image_paths, f.contact_email, f.submitted_at, f.status,
                   u.username, u.email
            FROM feedback f
            LEFT JOIN users u ON f.user_id = u.id
            {where}
            ORDER BY f.submitted_at DESC
            """
        )

        params = []
        where_clause = ""
        if status_filter:
            where_clause = "WHERE f.status = ?"
            params.append(status_filter)

        cursor.execute(base_query.format(where=where_clause), tuple(params))
        rows = cursor.fetchall()
        feedback_list = []
        for row in rows:
            item = dict(row)
            # Normalize image_paths JSON to list
            try:
                import json
                paths = json.loads(item.get('image_paths') or '[]')
                # Ensure list of strings
                if isinstance(paths, list):
                    item['image_paths'] = [p for p in paths if isinstance(p, str)]
                else:
                    item['image_paths'] = []
            except Exception:
                item['image_paths'] = []
            feedback_list.append(item)
    finally:
        if conn:
            conn.close()

    return render_template('admin/feedback.html', feedback=feedback_list, status_filter=status_filter)


@payment_bp.route('/admin/feedback/<int:feedback_id>/status', methods=['POST'])
def admin_feedback_update_status(feedback_id: int):
    if session.get('is_admin') != 1:
        abort(403)

    new_status = request.form.get('status', '').strip().lower()
    allowed_status = {'new', 'in_progress', 'resolved', 'archived'}
    if new_status not in allowed_status:
        flash('无效的状态值', 'danger')
        return redirect(url_for('payment_bp.admin_feedback_list'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE feedback SET status = ? WHERE id = ?", (new_status, feedback_id))
        if cursor.rowcount == 0:
            flash('反馈不存在或已被删除', 'warning')
        else:
            conn.commit()
            flash('状态已更新', 'success')
    except sqlite3.Error as e:
        current_app.logger.error(f"Error updating feedback {feedback_id} status: {e}")
        flash('更新状态时发生数据库错误', 'danger')
    finally:
        if conn:
            conn.close()

    return redirect(url_for('payment_bp.admin_feedback_list'))


@payment_bp.route('/admin/feedback/<int:feedback_id>/reply', methods=['POST'])
def admin_feedback_reply(feedback_id: int):
    if session.get('is_admin') != 1:
        abort(403)

    reply_text = (request.form.get('reply') or '').strip()
    if not reply_text:
        flash('回复内容不能为空', 'warning')
        return redirect(url_for('payment_bp.admin_feedback_list'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # 找到反馈对应的用户
        cursor.execute("SELECT user_id FROM feedback WHERE id = ?", (feedback_id,))
        row = cursor.fetchone()
        if not row or not row['user_id']:
            flash('反馈不存在或无归属用户', 'danger')
            return redirect(url_for('payment_bp.admin_feedback_list'))

        user_id = row['user_id']

        # 创建通知消息
        create_notification(user_id, reply_text)

        # 可选：把反馈状态标记为已处理进行中
        try:
            cursor.execute("UPDATE feedback SET status = CASE WHEN status='new' THEN 'in_progress' ELSE status END WHERE id = ?", (feedback_id,))
            conn.commit()
        except Exception:
            pass

        flash('已发送消息给用户', 'success')
    except sqlite3.Error as e:
        current_app.logger.error(f"Error replying feedback {feedback_id}: {e}")
        flash('发送消息失败：数据库错误', 'danger')
    finally:
        if conn:
            conn.close()

    return redirect(url_for('payment_bp.admin_feedback_list'))


# ------------------ Admin Broadcast Notifications ------------------

@payment_bp.route('/admin/notify', methods=['GET', 'POST'])
def admin_notify():
    if session.get('is_admin') != 1:
        abort(403)

    if request.method == 'GET':
        return render_template('admin/notify.html')

    # POST
    target = (request.form.get('target') or '').strip()  # 'all' or 'email'
    email = (request.form.get('email') or '').strip()
    message = (request.form.get('message') or '').strip()

    if not message:
        flash('消息内容不能为空', 'warning')
        return redirect(url_for('payment_bp.admin_notify'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        user_ids = []
        if target == 'all':
            cursor.execute("SELECT id FROM users")
            user_ids = [row['id'] for row in cursor.fetchall()]
        else:
            if not email:
                flash('请输入目标用户邮箱', 'warning')
                return redirect(url_for('payment_bp.admin_notify'))
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if not row:
                flash('指定邮箱的用户不存在', 'danger')
                return redirect(url_for('payment_bp.admin_notify'))
            user_ids = [row['id']]

        # 批量创建通知
        created = 0
        for uid in user_ids:
            try:
                create_notification(uid, message)
                created += 1
            except Exception as e:
                current_app.logger.error(f"Failed to notify user {uid}: {e}")

        flash(f'已发送通知给 {created} 位用户', 'success')
    except sqlite3.Error as e:
        current_app.logger.error(f"Broadcast notify failed: {e}")
        flash('发送失败：数据库错误', 'danger')
    finally:
        if conn:
            conn.close()

    return redirect(url_for('payment_bp.admin_notify'))


# ------------------ Admin Points Management ------------------

@payment_bp.route('/admin/points', methods=['GET'])
def admin_points():
    if session.get('is_admin') != 1:
        abort(403)

    q = (request.args.get('q') or '').strip()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if q:
            like = f"%{q}%"
            cursor.execute(
                "SELECT id, email, username, points, last_login_at, created_at FROM users WHERE email LIKE ? OR username LIKE ? ORDER BY created_at DESC",
                (like, like)
            )
        else:
            cursor.execute(
                "SELECT id, email, username, points, last_login_at, created_at FROM users ORDER BY created_at DESC"
            )
        users = [dict(row) for row in cursor.fetchall()]
    finally:
        if conn:
            conn.close()

    return render_template('admin/points.html', users=users, q=q)


@payment_bp.route('/admin/points/grant', methods=['POST'])
def admin_points_grant():
    if session.get('is_admin') != 1:
        abort(403)

    target = (request.form.get('target') or '').strip()  # 'all' | 'emails' | 'selected'
    emails_raw = (request.form.get('emails') or '').strip()
    selected_ids_raw = (request.form.get('selected_ids') or '').strip()
    reason = (request.form.get('reason') or '').strip()
    amount_raw = (request.form.get('amount') or '').strip()

    try:
        amount = int(amount_raw)
    except Exception:
        amount = 0

    if amount <= 0:
        flash('积分数量必须为正整数', 'warning')
        return redirect(url_for('payment_bp.admin_points'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        user_ids = []
        if target == 'all':
            cursor.execute("SELECT id FROM users")
            user_ids = [row['id'] for row in cursor.fetchall()]
        elif target == 'emails':
            emails = [e.strip() for e in emails_raw.split(',') if e.strip()]
            if not emails:
                flash('请填写至少一个邮箱', 'warning')
                return redirect(url_for('payment_bp.admin_points'))
            placeholders = ','.join(['?'] * len(emails))
            cursor.execute(f"SELECT id FROM users WHERE email IN ({placeholders})", tuple(emails))
            user_ids = [row['id'] for row in cursor.fetchall()]
            if not user_ids:
                flash('未找到对应邮箱的用户', 'warning')
                return redirect(url_for('payment_bp.admin_points'))
        elif target == 'selected':
            try:
                user_ids = [int(x) for x in selected_ids_raw.split(',') if x.strip()]
            except Exception:
                user_ids = []
            if not user_ids:
                flash('请选择至少一个用户', 'warning')
                return redirect(url_for('payment_bp.admin_points'))
        else:
            flash('无效的目标类型', 'danger')
            return redirect(url_for('payment_bp.admin_points'))

        # 批量加积分
        placeholders = ','.join(['?'] * len(user_ids))
        try:
            cursor.execute(f"UPDATE users SET points = points + ? WHERE id IN ({placeholders})", tuple([amount] + user_ids))
            conn.commit()
        except sqlite3.Error as e:
            current_app.logger.error(f"Grant points update failed: {e}")
            flash('加积分失败：数据库错误', 'danger')
            return redirect(url_for('payment_bp.admin_points'))

        # 发送通知
        sent = 0
        for uid in user_ids:
            try:
                msg = f"系统赠送 {amount} 积分" + (f"：{reason}" if reason else '')
                create_notification(uid, msg)
                sent += 1
            except Exception as e:
                current_app.logger.error(f"Grant points notify failed for {uid}: {e}")

        flash(f'已为 {len(user_ids)} 位用户增加 {amount} 积分（通知成功 {sent}）', 'success')
    finally:
        if conn:
            conn.close()

    return redirect(url_for('payment_bp.admin_points'))