import json
import os
from flask import current_app

_location_types_data = None

def get_location_types_data():
    """
    Lazily loads location types data from the JSON file specified in the config.
    Caches the data after the first load.
    """
    global _location_types_data
    if _location_types_data is not None:
        return _location_types_data

    location_types = {}
    file_path = ""
    try:
        file_path = current_app.config['LOCATION_TYPES_FILE']
        with open(file_path, 'r', encoding='utf-8') as f:
            location_types = json.load(f)
        print(f"成功加载地点类型配置: {file_path}")
    except FileNotFoundError:
        print(f"错误: 地点类型文件未找到: {file_path}")
    except json.JSONDecodeError as e:
        print(f"错误: 解析地点类型文件失败: {file_path} - {e}")
    except Exception as e:
        # This will catch errors if current_app is not available, or other unexpected errors
        print(f"加载地点类型文件时发生未知错误: {e}")

    _location_types_data = location_types
    return _location_types_data 