from app import create_app

app = create_app()

if __name__ == '__main__':
    # The debug flag is now controlled by the configuration loaded via create_app
    app.run(host='0.0.0.0', port=5000)
