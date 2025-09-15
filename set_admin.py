import sqlite3
import argparse
import os

# --- 配置 ---
# 数据库文件的路径，与您的Flask应用配置保持一致
DB_PATH = os.path.join('database', 'user_data.db') 
# --- 配置结束 ---

def set_user_as_admin(email):
    """
    通过邮箱地址查找用户，并将其设置为管理员。
    """
    if not os.path.exists(DB_PATH):
        print(f"错误：数据库文件未找到，请确认路径 '{DB_PATH}' 是否正确。")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 检查用户是否存在
        cursor.execute("SELECT id, username, is_admin FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if user is None:
            print(f"错误：未找到邮箱为 '{email}' 的用户。")
            return

        user_id, username, current_status = user

        if current_status == 1:
            print(f"用户 '{username}' (Email: {email}) 已经是管理员了。")
            return

        # 更新用户状态
        cursor.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        conn.commit()

        print(f"成功！用户 '{username}' (Email: {email}) 现在已被设置为管理员。")
        print("该用户下次登录后，即可访问管理员后台。")

    except sqlite3.Error as e:
        print(f"数据库操作失败: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="将一个用户设置为管理员。")
    parser.add_argument("email", type=str, help="要设置为管理员的用户的注册邮箱地址。")
    
    args = parser.parse_args()
    
    set_user_as_admin(args.email) 