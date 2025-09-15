import sqlite3

def view_schema(db_name):
    """
    连接到指定的 SQLite 数据库并打印所有表的结构。
    """
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print(f"数据库 '{db_name}' 中没有找到任何表。")
            return

        print(f"数据库 '{db_name}' 的表结构:")
        for table_name in tables:
            table_name = table_name[0]
            print(f"\n-- 表: {table_name} --")
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            for column in columns:
                print(f"  {column[1]} {column[2]} {'PRIMARY KEY' if column[5] else ''}")

    except sqlite3.Error as e:
        print(f"读取数据库时发生错误: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    view_schema('user_data.db')
    view_schema('geocoding.db') # 也检查一下另一个数据库 