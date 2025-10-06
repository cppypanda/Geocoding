from app import create_app

app = create_app('production')

if __name__ == '__main__':
    # 在生产环境中，应该通过 Gunicorn 等 WSGI 服务器启动，而不是 app.run()
    # 为了直接运行进行测试，这里我们暂时关闭 debug 模式
    # 正式部署时请使用 Gunicorn: gunicorn -w 4 -b 127.0.0.1:5000 run:app
    app.run(debug=False, host='0.0.0.0', port=5000)
