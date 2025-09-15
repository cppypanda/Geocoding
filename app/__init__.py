import os
import logging
from flask import Flask, request, jsonify, render_template, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from .config import config_by_name
from zhipuai import ZhipuAI
from .utils.log_context import ContextFilter

# Initialize extensions
db = SQLAlchemy()

def create_app(config_name=None, config_overrides=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
        
    app = Flask(__name__,
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
                static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static')))

    app.config.from_object(config_by_name[config_name])

    # --- Logging setup ---
    app.logger.addFilter(ContextFilter())
    log_format = '[%(asctime)s] %(levelname)s in %(module)s: %(context)s%(message)s'
    formatter = logging.Formatter(log_format)
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)
    
    if config_overrides:
        app.config.update(config_overrides)

    # Initialize extensions with the app
    db.init_app(app)

    if app.config.get('ZHIPUAI_KEY'):
        app.extensions['zhipuai_client'] = ZhipuAI(api_key=app.config['ZHIPUAI_KEY'])
    else:
        app.extensions['zhipuai_client'] = None

    with app.app_context():
        # This will create tables from your models if they don't exist
        from . import models
        db.create_all()
        app.logger.info("SQLAlchemy tables created/verified.")
        app.logger.info("Flask application initialization complete.")

    # Register blueprints
    from .routes.main import main_bp
    app.register_blueprint(main_bp)
    from .routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    from .routes.geocoding import geocoding_bp
    app.register_blueprint(geocoding_bp)
    from .routes.user import user_bp
    app.register_blueprint(user_bp)
    from .routes.payment_bp import payment_bp
    app.register_blueprint(payment_bp)
    from .routes.task_routes import task_bp
    app.register_blueprint(task_bp)

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        from flask import send_from_directory
        uploads_root = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'uploads')
        return send_from_directory(uploads_root, filename)

    @app.context_processor
    def inject_public_config():
        return {
            'TIANDITU_KEY': app.config.get('TIANDITU_KEY'),
            'AMAP_KEY': app.config.get('AMAP_KEY'),
        }

    return app

def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)