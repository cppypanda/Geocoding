import json
import os
from flask import current_app
from ..models import LocationType
from .. import db

_location_types_data = None

def get_location_types_data():
    """
    Lazily loads approved location types data from the database.
    Caches the data after the first load for the application's lifetime.
    """
    global _location_types_data
    if _location_types_data is not None:
        return _location_types_data

    location_types_list = []
    try:
        # This needs an app context to access the database
        with current_app.app_context():
            approved_types = db.session.query(LocationType.name).filter_by(status='approved').order_by(db.func.length(LocationType.name).desc()).all()
            location_types_list = [item[0] for item in approved_types]
        print(f"成功从数据库加载 {len(location_types_list)} 个已批准的地名后缀。")
    except Exception as e:
        print(f"从数据库加载地名类型时发生错误: {e}")
        # Fallback to JSON file if database fails
        file_path = ""
        try:
            file_path = current_app.config['LOCATION_TYPES_FILE']
            with open(file_path, 'r', encoding='utf-8') as f:
                location_types_list = json.load(f)
            print(f"数据库加载失败，回退到JSON文件加载: {file_path}")
        except Exception as e_json:
            print(f"回退加载JSON文件也失败了: {e_json}")

    _location_types_data = location_types_list
    return _location_types_data 