import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join('database', 'geocoding.db')

def check_if_migration_needed(cursor):
    """通过检查列是否存在来判断是否需要迁移。"""
    try:
        # 如果这个查询成功，说明表结构已经是新的
        cursor.execute("SELECT name, status, usage_count, last_used_at FROM location_types LIMIT 1")
        return False
    except sqlite3.OperationalError as e:
        # 如果失败是因为列不存在，则需要迁移
        if "no such column" in str(e):
            return True
        else:
            # 其他数据库错误，直接抛出
            raise e

def migrate_location_types_table():
    """
    对 location_types 表执行非破坏性迁移。
    它会重命名旧表，创建新表，复制数据，然后删除旧表。
    """
    if not os.path.exists(DB_FILE):
        print(f"数据库文件 '{DB_FILE}' 不存在，无需迁移。应用启动时将创建新表。")
        return

    print(f"正在连接数据库 '{DB_FILE}'...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        if not check_if_migration_needed(cursor):
            print("表 'location_types' 结构已是最新，无需迁移。")
            return

        print("检测到旧的 'location_types' 表结构，开始执行迁移...")

        # 步骤 1: 将旧表重命名
        print("  [1/4] 重命名旧表为 'old_location_types'...")
        cursor.execute("ALTER TABLE location_types RENAME TO old_location_types")

        # 步骤 2: 创建新表
        print("  [2/4] 创建新的 'location_types' 表...")
        cursor.execute('''
            CREATE TABLE location_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                source TEXT NOT NULL DEFAULT 'user_generated' CHECK(source IN ('user_generated', 'system_default')),
                usage_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL
            )
        ''')

        # 步骤 3: 从旧表复制数据到新表
        print("  [3/4] 从旧表向新表迁移数据...")
        cursor.execute("SELECT type, created_at FROM old_location_types")
        old_data = cursor.fetchall()

        for row in old_data:
            type_name, created_at_str = row
            if not created_at_str:
                 created_at_str = datetime.utcnow().isoformat()
            # 使用 created_at 作为 last_used_at 的默认值
            cursor.execute("""
                INSERT INTO location_types (name, created_at, last_used_at)
                VALUES (?, ?, ?)
            """, (type_name, created_at_str, created_at_str))

        # 步骤 4: 删除旧表
        print("  [4/4] 删除旧的临时表...")
        cursor.execute("DROP TABLE old_location_types")

        conn.commit()
        print("\n迁移成功！数据库表 'location_types' 已更新至最新结构。")
        print("现在您可以正常启动Web应用了。")

    except Exception as e:
        print(f"\n迁移过程中发生错误: {e}")
        print("操作已自动回滚，数据库未被修改。")
        conn.rollback()
    finally:
        print("关闭数据库连接。")
        conn.close()

if __name__ == "__main__":
    migrate_location_types_table() 