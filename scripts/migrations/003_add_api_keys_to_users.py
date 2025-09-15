import sqlite3
import os

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../database/user_data.db'))

def add_api_keys_columns():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    alter_statements = []
    if 'amap_key' not in columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN amap_key TEXT;")
    if 'baidu_key' not in columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN baidu_key TEXT;")
    if 'tianditu_key' not in columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN tianditu_key TEXT;")
    if 'ai_key' not in columns:
        alter_statements.append("ALTER TABLE users ADD COLUMN ai_key TEXT;")

    for stmt in alter_statements:
        print(f"执行: {stmt.strip()}")
        cursor.execute(stmt)
    
    if alter_statements:
        conn.commit()
        print("字段添加完成！")
    else:
        print("所有字段已存在，无需更改。")
    conn.close()

if __name__ == '__main__':
    add_api_keys_columns() 