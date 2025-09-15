import sqlite3
import os

DB_FILE = os.path.join('database', 'geocoding.db')

def approve_all_pending_suffixes():
    """
    将 location_types 表中所有 status 为 'pending' 的记录更新为 'approved'。
    这是一个一次性的辅助脚本，用于批量批准由旧版本迁移过来的数据。
    """
    if not os.path.exists(DB_FILE):
        print(f"数据库文件 '{DB_FILE}' 不存在，无需执行。")
        return

    print(f"正在连接数据库 '{DB_FILE}'...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        print("正在查询待批准 (pending) 的后缀数量...")
        cursor.execute("SELECT COUNT(*) FROM location_types WHERE status = 'pending'")
        count = cursor.fetchone()[0]

        if count == 0:
            print("没有找到待批准的后缀，无需执行操作。")
            return

        print(f"找到 {count} 个待批准的后缀。现在开始执行批量批准...")
        cursor.execute("UPDATE location_types SET status = 'approved' WHERE status = 'pending'")
        
        conn.commit()
        
        print(f"\n成功！已将 {cursor.rowcount} 个后缀的状态更新为 'approved'。")
        print("现在您可以刷新或重启Web应用来查看效果了。")

    except Exception as e:
        print(f"\n操作过程中发生错误: {e}")
        conn.rollback()
    finally:
        print("关闭数据库连接。")
        conn.close()

if __name__ == "__main__":
    approve_all_pending_suffixes() 