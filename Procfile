web: python -m flask --app run.py db upgrade && gunicorn --workers 1 --bind 0.0.0.0:$PORT run:app
