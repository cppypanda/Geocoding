import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import sqlite3
from app.models import LocationType
from app import create_app, db
import json


def migrate_suffixes():
    """将JSON文件中的地名后缀迁移到数据库中"""
    app = create_app()
    with app.app_context():
        print("开始迁移地名类型后缀...")

        # 读取JSON文件
        json_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'location_types.json')
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                suffixes = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"错误: 无法读取或解析 aoo/location_types.json: {e}")
            return

        existing_suffixes = {s.name for s in LocationType.query.all()}
        new_suffixes_to_add = []

        for suffix_name in suffixes:
            if suffix_name not in existing_suffixes:
                new_loc_type = LocationType(
                    name=suffix_name,
                    status='approved',
                    source='system_default',
                    usage_count=0 
                )
                new_suffixes_to_add.append(new_loc_type)
        
        if new_suffixes_to_add:
            db.session.bulk_save_objects(new_suffixes_to_add)
            db.session.commit()
            print(f"成功迁移 {len(new_suffixes_to_add)} 个新的地名后缀到数据库。")
        else:
            print("数据库中已存在所有JSON文件中的后缀，无需迁移。")

        print("地名后缀迁移完成。")

if __name__ == "__main__":
    migrate_suffixes() 