import os
from app import create_app

# Fallback to development when running CLI if DATABASE_URL missing
default_config = 'development'

# 1. Explicitly set to production via env var
if os.environ.get('FLASK_CONFIG') == 'production':
    default_config = 'production'
# 2. Automatically detect Render environment
elif os.environ.get('RENDER'):
    default_config = 'production'

app = create_app(default_config)
print(f" * Application running in {default_config} mode")

if __name__ == '__main__':
    # 在生产环境中，应该通过 Gunicorn 等 WSGI 服务器启动，而不是 app.run()
    # 为了直接运行进行测试，这里我们暂时关闭 debug 模式
    # 正式部署时请使用 Gunicorn: gunicorn -w 4 -b 127.0.0.1:5000 run:app
    app.run(debug=False, host='0.0.0.0', port=5000)
