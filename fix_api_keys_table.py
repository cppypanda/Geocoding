import sqlite3

db_path = 'database/api_keys.db'  # 按实际路径修改

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

def add_column_if_not_exists(table, column, coltype):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [info[1] for info in cursor.fetchall()]
    if column not in columns:
        print(f"Adding column: {column} {coltype}")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

add_column_if_not_exists('api_keys', 'user_id', 'INTEGER')
add_column_if_not_exists('api_keys', 'service_name', 'TEXT')
add_column_if_not_exists('api_keys', 'status', "TEXT DEFAULT 'active'")
add_column_if_not_exists('api_keys', 'cooldown_until', 'TIMESTAMP')
add_column_if_not_exists('api_keys', 'last_used_time', 'TIMESTAMP')
add_column_if_not_exists('api_keys', 'failure_count', 'INTEGER DEFAULT 0')
add_column_if_not_exists('api_keys', 'initial_points_awarded', 'INTEGER DEFAULT 0')
add_column_if_not_exists('api_keys', 'created_at', "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

conn.commit()
conn.close()
print("api_keys表结构已修复") 