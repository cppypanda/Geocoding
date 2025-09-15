import sqlite3
import json # 用于美化打印 JSON 字符串

DB_NAME = 'user_data.db'

def view_feedback_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    print("--- Feedback Table Data ---")
    cursor.execute("SELECT id, user_id, description, image_paths, contact_email, submitted_at, status FROM feedback")
    rows = cursor.fetchall()
    if not rows:
        print("No data in feedback table.")
    for row in rows:
        image_paths_str = row[3]
        try:
            # 尝试将 image_paths 解析为 JSON 并美化打印
            image_paths_list = json.loads(image_paths_str) if image_paths_str else []
            image_paths_formatted = json.dumps(image_paths_list, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            image_paths_formatted = image_paths_str # 如果不是合法的JSON，直接显示原始字符串
        
        print(f"ID: {row[0]}, User ID: {row[1]}, Description: {row[2][:50]}..., Image Paths: {image_paths_formatted}, Contact: {row[4]}, Submitted: {row[5]}, Status: {row[6]}")
    conn.close()

def view_users_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    print("\\n--- Users Table Data ---")
    cursor.execute("SELECT id, phone_number, username, points, registration_date, last_login_at FROM users")
    rows = cursor.fetchall()
    if not rows:
        print("No data in users table.")
    for row in rows:
        print(f"ID: {row[0]}, Phone: {row[1]}, Username: {row[2]}, Points: {row[3]}, Registered: {row[4]}, Last Login: {row[5]}")
    conn.close()

if __name__ == '__main__':
    view_feedback_data()
    view_users_data()