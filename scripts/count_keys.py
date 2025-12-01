import sys
import os

# 将项目根目录添加到 Python 路径，确保能导入 app 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, UserApiKey
from sqlalchemy import func

def check_keys():
    # 使用开发环境配置初始化 app
    app = create_app('development')
    
    with app.app_context():
        print("="*50)
        print("API Key 存储统计报告")
        print("="*50)
        
        # 1. 统计 UserApiKey 表 (主要存储位置)
        total_keys = UserApiKey.query.count()
        print(f"\n[UserApiKey 表] 总计 Key 数量: {total_keys}")
        
        # 按服务商分组统计
        key_stats = db.session.query(
            UserApiKey.service_name, 
            func.count(UserApiKey.id)
        ).group_by(UserApiKey.service_name).all()
        
        if key_stats:
            print("按服务商分布:")
            for service, count in key_stats:
                print(f"  - {service}: {count} 个")
        else:
            print("  (暂无数据)")

        # 2. 检查 Users 表中的字段 (旧版/兼容存储)
        print("\n[User 表] 字段存储情况 (检查冗余/兼容字段):")
        users_with_amap = User.query.filter(User.amap_key.isnot(None), User.amap_key != '').count()
        users_with_baidu = User.query.filter(User.baidu_key.isnot(None), User.baidu_key != '').count()
        users_with_tianditu = User.query.filter(User.tianditu_key.isnot(None), User.tianditu_key != '').count()
        users_with_ai = User.query.filter(User.ai_key.isnot(None), User.ai_key != '').count()
        
        print(f"  - 有高德 Key 的用户数: {users_with_amap}")
        print(f"  - 有百度 Key 的用户数: {users_with_baidu}")
        print(f"  - 有天地图 Key 的用户数: {users_with_tianditu}")
        print(f"  - 有 AI Key 的用户数: {users_with_ai}")

        # 3. 列出具体详情 (可选)
        # print("\n[详情] 用户 Key 列表:")
        # keys = UserApiKey.query.all()
        # for k in keys:
        #     u = User.query.get(k.user_id)
        #     username = u.username if u else f"Unknown(ID:{k.user_id})"
        #     print(f"  - 用户: {username}, 服务: {k.service_name}, 状态: {k.status}")
        
        print("\n" + "="*50)

if __name__ == "__main__":
    check_keys()

