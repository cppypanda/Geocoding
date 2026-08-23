import os
import logging
from flask import Flask, request, jsonify, render_template, send_file, session, url_for, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix  # Import ProxyFix
from werkzeug.exceptions import HTTPException
from .config import config_by_name
from zhipuai import ZhipuAI
from .utils.log_context import ContextFilter
from .utils.time_utils import to_beijing_time

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
# Redirect users to the main page to log in if they try to access a protected page
login_manager.login_view = 'main.index'

def create_app(config_name=None, config_overrides=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
        
    app = Flask(__name__,
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
                static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static')))
    
    # Register custom Jinja filters
    app.jinja_env.filters['to_beijing_time'] = to_beijing_time

    # Apply ProxyFix to trust headers from the reverse proxy (e.g., Render)
    # This is crucial for secure cookies to work correctly in production.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config.from_object(config_by_name[config_name])

    if config_name == 'production' and app.config.get('SECRET_KEY') == 'a_default_highly_secret_and_static_key_for_dev':
        raise RuntimeError('生产环境必须配置独立的 SECRET_KEY')

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
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from .services.error_center import capture_exception, init_error_center
    init_error_center(app)

    # Handle CSRF errors with JSON for API requests
    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        # If it's an AJAX/JSON request, return structured JSON to help the frontend
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'CSRF校验失败: {e.description}'}), 400
        # Fallback to a simple text response
        return jsonify({'success': False, 'message': 'CSRF校验失败'}), 400

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if isinstance(error, HTTPException):
            if error.code and error.code >= 500:
                capture_exception(error, source='http_exception')
            return error

        error_id = capture_exception(error, source='unhandled_exception', severity='critical')
        app.logger.error(
            '未处理的应用异常（错误记录ID: %s）',
            error_id or '记录失败',
            exc_info=(type(error), error, error.__traceback__),
            extra={'error_center_skip': True},
        )
        reference = f'ERR-{error_id}' if error_id else None
        if (
            request.is_json
            or request.path.startswith('/api/')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        ):
            return jsonify({
                'success': False,
                'message': '服务器内部错误，请稍后重试',
                'error_reference': reference,
            }), 500
        return render_template('500.html', error_reference=reference), 500

    # Handle Unauthorized (401) errors for AJAX requests to prevent redirect loops
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'success': False, 'message': '请先登录', 'login_required': True}), 401
        return redirect(url_for(login_manager.login_view, next=request.url))

    if app.config.get('ZHIPUAI_KEY'):
        app.extensions['zhipuai_client'] = ZhipuAI(api_key=app.config['ZHIPUAI_KEY'])
    else:
        app.extensions['zhipuai_client'] = None

    with app.app_context():
        # This will create tables from your models if they don't exist
        from . import models
        # db.create_all() # We will use migrations instead

        @login_manager.user_loader
        def load_user(user_id):
            user = db.session.get(models.User, int(user_id))
            return None if not user or user.is_deleted else user

        app.logger.info("SQLAlchemy tables created/verified.")
        app.logger.info("Flask application initialization complete.")

    # Register blueprints
    from .routes.main import main_bp
    from .routes.auth import auth_bp
    from .routes.user import user_bp
    from .routes.geocoding import geocoding_bp
    from .routes.task_routes import task_bp
    from .routes.payment_bp import payment_bp
    from .routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(geocoding_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(admin_bp)

    @app.route('/uploads/<path:filename>')
    def uploaded_file(filename):
        from flask import send_from_directory
        uploads_root = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'uploads')
        return send_from_directory(uploads_root, filename)

    @app.route('/api/client-errors', methods=['POST'])
    def report_client_error():
        from .services.error_center import capture_error

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'success': False, 'message': '无效的错误数据'}), 400

        message = str(payload.get('message') or '浏览器端未知错误')[:4000]
        error_type = str(payload.get('type') or 'ClientError')[:255]
        kind = str(payload.get('kind') or 'javascript')[:64]
        stack = str(payload.get('stack') or '')[:20000]
        location = str(payload.get('location') or '').split('?', 1)[0].split('#', 1)[0][:2000]
        traceback_text = '\n'.join(part for part in (location, stack) if part) or None
        capture_error(
            message,
            exception_type=error_type,
            severity='error',
            source=f'client:{kind}',
            traceback_text=traceback_text,
        )
        return ('', 204)

    @app.context_processor
    def inject_public_config():
        points_award = app.config.get('POINTS_AWARD_BY_SERVICE', {})
        min_award = min(v for k, v in points_award.items() if k != 'default' and v > 0) if any(v > 0 for k, v in points_award.items() if k != 'default') else 0
        max_award = max(points_award.values()) if points_award else 0

        return {
            'TIANDITU_KEY': app.config.get('TIANDITU_KEY'),
            'AMAP_KEY': app.config.get('AMAP_KEY'),
            'points_award_by_service': points_award,
            'referral_award': app.config.get('REFERRAL_AWARD', {}),
            'points_award_range': {'min': min_award, 'max': max_award},
            'recharge_packages': app.config.get('RECHARGE_PACKAGES', {})
        }

    return app

def has_no_empty_params(rule):
    defaults = rule.defaults if rule.defaults is not None else ()
    arguments = rule.arguments if rule.arguments is not None else ()
    return len(defaults) >= len(arguments)
