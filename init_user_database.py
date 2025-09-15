import os
# 确保脚本可以找到 app 模块
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.db_setup import init_user_db, init_recharge_orders_db
from app.config import Config

def setup_database():
    """
    初始化用户相关的数据库表。
    """
    db_path = Config.USER_DB_NAME
    
    # 确保数据库目录存在
    db_dir = os.path.dirname(db_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"Created database directory: {db_dir}")

    print("Initializing user database...")
    init_user_db(db_path)
    
    print("Initializing recharge orders database...")
    init_recharge_orders_db(db_path)
    
    print("\nDatabase setup complete.")
    print(f"User database is at: {db_path}")

if __name__ == '__main__':
    setup_database() 