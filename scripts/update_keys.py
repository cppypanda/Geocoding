import sqlite3
import os

print("更新API密钥数据库...")

# 示例密钥 - 这些是无效的示例值，实际使用时需要替换为有效的API密钥
AMAP_KEY = "这里替换为高德地图密钥"  # 需要替换为真实的密钥
BAIDU_KEY = "这里替换为百度地图密钥"  # 需要替换为真实的密钥
TIANDITU_KEY = "这里替换为天地图密钥"  # 需要替换为真实的密钥

try:
    conn = sqlite3.connect('api_keys.db')
    cursor = conn.cursor()
    
    # 创建表（如果不存在）
    cursor.execute('''CREATE TABLE IF NOT EXISTS api_keys
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     service TEXT NOT NULL,
                     api_key TEXT NOT NULL,
                     qps INTEGER DEFAULT 3,
                     daily_limit INTEGER DEFAULT 10000,
                     is_active INTEGER DEFAULT 1,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 添加或更新密钥
    services = [
        ('amap', AMAP_KEY),
        ('baidu', BAIDU_KEY),
        ('tianditu', TIANDITU_KEY)
    ]
    
    for service, key in services:
        # 先检查是否已存在
        cursor.execute("SELECT id FROM api_keys WHERE service = ?", (service,))
        row = cursor.fetchone()
        
        if row:
            # 更新现有记录
            cursor.execute("UPDATE api_keys SET api_key = ?, is_active = 1 WHERE service = ?", 
                         (key, service))
            print(f"更新 {service} API密钥")
        else:
            # 添加新记录
            cursor.execute("INSERT INTO api_keys (service, api_key) VALUES (?, ?)", 
                         (service, key))
            print(f"添加 {service} API密钥")
    
    conn.commit()
    print("API密钥数据库更新成功")
    
    # 创建.env文件
    with open('.env', 'w') as f:
        f.write(f"AMAP_KEY={AMAP_KEY}\n")
        f.write(f"BAIDU_KEY={BAIDU_KEY}\n")
        f.write(f"TIANDITU_KEY={TIANDITU_KEY}\n")
    print(".env文件创建成功")
    
except Exception as e:
    print(f"错误: {e}")
    conn.rollback()
finally:
    conn.close() 