import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a_default_highly_secret_and_static_key_for_dev')
    
    # Database paths
    USER_DB_NAME = os.path.join(_PROJECT_ROOT, 'database', 'user_data.db')

    # SQLAlchemy a configuration
    # Read the database URL from an environment variable, with a fallback to a local SQLite DB for development
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 
                                             'sqlite:///' + os.path.join(_PROJECT_ROOT, 'database', 'local_dev.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Other paths
    FEEDBACK_UPLOAD_FOLDER = os.path.join(_PROJECT_ROOT, 'uploads', 'feedback')
    LOCATION_TYPES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'location_types.json')

    # API Keys (read from environment variables)
    AMAP_KEY = os.environ.get('AMAP_KEY')
    BAIDU_KEY = os.environ.get('BAIDU_KEY')
    TIANDITU_KEY = os.environ.get('TIANDITU_KEY')
    ZHIPUAI_KEY = os.environ.get('ZHIPUAI_KEY')
    
    # Application constants
    REQUIRED_CONFIDENCE_THRESHOLD = 0.9
    NO_PASSWORD_PLACEHOLDER = 'NO_PASSWORD_SMS_LOGIN'
    
    # SMTP 邮件服务配置
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'true').lower() in ['true', '1', 't']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

    # To be configured in subclasses
    DEBUG = False
    TESTING = False

    # 积分相关配置
    POINTS_AWARD_FOR_KEY = 100
    POINTS_COST_STANDARD = 2
    POINTS_COST_DISCOUNT = 1

    # =================================================
    # V2 精细化积分配置 (运营核心)
    # =================================================
    POINTS_AWARD_BY_SERVICE = {
        'amap': 100,
        'baidu': 80,
        'tianditu': 120,
        'zhipuai': 150,
        'default': 50
    }
    POINTS_COST_BY_TASK = {
        'geocoding':              {'standard': 0, 'discount': 0},
        'reverse_geocoding':      {'standard': 0, 'discount': 0},
        'poi_search_amap':        {'standard': 2, 'discount': 2},
        'poi_search_baidu':       {'standard': 2, 'discount': 2},
        'poi_search_tianditu':    {'standard': 0, 'discount': 0},
        'llm_call':               {'standard': 2, 'discount': 2},
        'web_search':             {'standard': 2, 'discount': 2},
    }
    REFERRAL_AWARD = {
        'referrer': 50,
        'invitee': 50
    }

    # SQLAlchemy engine options
    # - pool_pre_ping: avoid stale connections on platform proxies
    # - For Render Postgres: force SSL to fix "SSL error: decryption failed or bad record mac"
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }
    _db_uri_lower = (SQLALCHEMY_DATABASE_URI or '').lower()
    if _db_uri_lower.startswith('postgres://') or _db_uri_lower.startswith('postgresql://'):
        # psycopg2 respects sslmode in connect args
        SQLALCHEMY_ENGINE_OPTIONS['connect_args'] = {'sslmode': 'require'}

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration."""
    pass

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 