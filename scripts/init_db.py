import sqlite3
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def init_db():
    # 连接到数据库
    conn = sqlite3.connect('api_keys.db')
    cursor = conn.cursor()
    
    # 删除旧表（如果存在）
    cursor.execute('DROP TABLE IF EXISTS api_keys')
    
    # 创建新表
    cursor.execute('''
    CREATE TABLE api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service TEXT NOT NULL,
        api_key TEXT NOT NULL,
        qps INTEGER DEFAULT 3,
        daily_limit INTEGER DEFAULT 10000,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 插入默认的API密钥
    default_keys = [
        ('amap', os.getenv('AMAP_KEY', '')),
        ('baidu', os.getenv('BAIDU_KEY', '')),
        ('tianditu', os.getenv('TIANDITU_KEY', ''))
    ]
    
    for service, key in default_keys:
        if key:  # 只插入非空的密钥
            cursor.execute('''
            INSERT INTO api_keys (service, api_key)
            VALUES (?, ?)
            ''', (service, key))
    
    # 提交更改并关闭连接
    conn.commit()
    conn.close()
    
    print("数据库初始化完成！")

if __name__ == '__main__':
    init_db() 