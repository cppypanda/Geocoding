import sqlite3
import os
from werkzeug.security import generate_password_hash

# 数据库文件名
DB_NAME = 'user_data.db'

def init_user_data_db():
    """
    初始化用户数据库，创建 users 和 tasks 表。
    如果表已存在，则不会重复创建。
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 创建 users 表 (如果不存在)
    # 假设的 users 表结构，请根据实际情况调整
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 创建 tasks 表 (如果不存在)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        result_data TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        UNIQUE (user_id, name)
    )
    ''')

    # 添加一个默认的 admin 用户 (如果不存在)
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if cursor.fetchone() is None:
        admin_password = os.getenv('ADMIN_PASSWORD', 'admin') # 强烈建议通过环境变量设置密码
        hashed_password = generate_password_hash(admin_password)
        cursor.execute('''
        INSERT INTO users (username, password, is_admin)
        VALUES (?, ?, ?)
        ''', ('admin', hashed_password, 1))
        print("默认 admin 用户已创建。")

    conn.commit()
    conn.close()
    print(f"数据库 '{DB_NAME}' 初始化/检查完成。")

if __name__ == '__main__':
    init_user_data_db() 