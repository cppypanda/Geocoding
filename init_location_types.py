import sqlite3

def init_location_types():
    """将默认的地名类型后缀导入到数据库中"""
    
    print("开始初始化地名类型后缀...")
    
    conn = sqlite3.connect('geocoding.db')
    c = conn.cursor()
    
    # 创建地名类型后缀表(如果不存在)
    c.execute('''CREATE TABLE IF NOT EXISTS location_types
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  type TEXT UNIQUE,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # 检查数据库中是否已有后缀数据
    c.execute('SELECT COUNT(*) FROM location_types')
    count = c.fetchone()[0]
    
    # 如果数据库中没有后缀数据，添加默认后缀列表
    if count == 0:
        # 默认后缀列表，与前端JS中相同
        default_suffixes = [
            "历史文化街区", "农业科技园区", "经济技术开发区", "高新技术产业开发区", 
            "产业园区", "国家公园", "风景名胜区", "自然保护区", "示范区", 
            "工业园区", "文化街区", "开发区", "商业区", "科技园", "公园", 
            "校区", "景区", "园区", "街区"
        ]
        
        # 将默认后缀插入数据库
        for suffix in default_suffixes:
            c.execute('INSERT OR IGNORE INTO location_types (type) VALUES (?)', (suffix,))
        
        print(f"已将 {len(default_suffixes)} 个默认地名类型后缀添加到数据库")
    else:
        print(f"数据库中已有 {count} 个地名类型后缀，无需初始化")
    
    conn.commit()
    conn.close()
    
    print("地名类型后缀初始化完成")

if __name__ == "__main__":
    init_location_types() 