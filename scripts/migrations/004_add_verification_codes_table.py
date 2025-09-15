import sqlite3

def upgrade():
    # 连接到用户数据库
    # 注意：这里的路径可能需要根据您的项目结构进行调整
    # 假设脚本从项目根目录运行
    conn = sqlite3.connect('database/user_data.db')
    cursor = conn.cursor()

    # 创建 verification_codes 表
    # email: 接收验证码的邮箱地址
    # purpose: 验证码的用途，例如 'register_login', 'reset_password'
    # code: 验证码本身
    # expires_at: 验证码的过期时间戳 (UTC)
    # used: 标记验证码是否已被使用 (0 for false, 1 for true)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            purpose TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        )
    ''')
    
    # 为 email 和 purpose 列创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_email_purpose ON verification_codes (email, purpose)')

    conn.commit()
    conn.close()
    print("数据库升级完成：已创建 'verification_codes' 表。")

if __name__ == '__main__':
    upgrade()
