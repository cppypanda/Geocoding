import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a_default_highly_secret_and_static_key_for_dev')
    ADMIN_EMAILS = [email.strip() for email in os.environ.get('ADMIN_EMAILS', '').split(',') if email.strip()]
    
    # SQLAlchemy a configuration
    # Read the database URL from an environment variable.
    # This will raise a KeyError if the environment variable is not set,
    # ensuring the application fails fast in case of misconfiguration.
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # This local folder is no longer used for uploads, but might be kept for other purposes.
    # We are switching to Cloudflare R2 for persistent storage.
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

    # Cloudflare R2 Storage Configuration
    # Read from environment variables to keep credentials secure
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
    R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
    R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
    # Custom domain or public R2 URL for accessing files
    R2_PUBLIC_URL_BASE = os.environ.get('R2_PUBLIC_URL_BASE')

    # ==============================================================================
    # 支付宝支付配置
    # ==============================================================================
    ALIPAY_APP_ID = os.environ.get('ALIPAY_APP_ID')
    # 应用私钥，请确保证书文件路径正确或直接从环境变量读取密钥字符串
    APP_PRIVATE_KEY = os.environ.get('APP_PRIVATE_KEY')
    # 支付宝公钥，同上
    ALIPAY_PUBLIC_KEY = os.environ.get('ALIPAY_PUBLIC_KEY')
    
    # ==============================================================================
    # 积分与奖励配置 (运营核心)
    # ==============================================================================

    # 1. 新用户初始积分
    # ------------------------------------------------------------------------------
    # 定义一个新注册用户首次登录时自动获得的初始积分数量。
    NEW_USER_REWARD_POINTS = 100

    # 2. 贡献API密钥奖励
    # ------------------------------------------------------------------------------
    # 用户在个人中心提交自己申请的API密钥并通过验证后，可以获得一次性积分奖励。
    # 您可以为不同服务商的密钥设定不同的奖励值，以鼓励用户贡献稀缺或高价值的密钥。
    POINTS_AWARD_BY_SERVICE = {
        'amap': 100,      # 贡献高德地图API Key的奖励积分
        'baidu': 80,       # 贡献百度地图API Key的奖励积分
        'tianditu': 10,   # 贡献天地图API Key的奖励积分
        'zhipuai': 150,    # 贡献智谱AI API Key的奖励积分
        'default': 50      # 贡献其他未指定类型Key的默认奖励积分
    }

    # 3. 功能消耗积分定价
    # ------------------------------------------------------------------------------
    # 定义各项服务或功能单次调用的积分消耗。
    # 'standard' 为标准定价, 'discount' 通常用于用户使用自己的API Key时的优惠定价。
    POINTS_COST_BY_TASK = {
        # 核心功能 (当前免费)
        'geocoding':              {'standard': 0, 'discount': 0},  # 地理编码 (地址 -> 坐标)
        'reverse_geocoding':      {'standard': 0, 'discount': 0},  # 逆地理编码 (坐标 -> 地址)
        
        # POI 搜索功能
        'poi_search_amap':        {'standard': 1, 'discount': 0},  # 使用 高德进行POI搜索
        'poi_search_baidu':       {'standard': 1, 'discount': 0},  # 使用百度进行POI搜索
        'poi_search_tianditu':    {'standard': 0, 'discount': 0},  # 使用天地图进行POI搜索 (通常是免费或有有条件限制)

        # 增值智能服务
        'llm_call':               {'standard': 2, 'discount': 2},  # 任何一次对大语言模型的调用 (例如：智能选点、智能纠错等)
        'web_search':             {'standard': 2, 'discount': 2},  # 网络智能搜索功能

        # 导出功能
        'export_xlsx':            {'standard': 5, 'discount': 5},  # 导出为 XLSX 文件
        'export_kml':             {'standard': 5, 'discount': 5},  # 导出为 KML 文件
        'export_shp':             {'standard': 5, 'discount': 5},  # 导出为 SHP 文件
    }

    # 4. 用户推荐奖励
    # ------------------------------------------------------------------------------
    # 当用户通过推荐链接邀请新朋友注册成功后，双方可以获得的积分奖励。
    REFERRAL_AWARD = {
        'referrer': 50,    # 推荐人 (邀请方) 获得的积分
        'invitee': 50      # 被推荐人 (新用户) 获得的积分
    }

    # 5. 充值套餐配置
    # ------------------------------------------------------------------------------
    # 定义用户可以购买的积分套餐，键为套餐ID，值为一个包含名称、积分和价格的字典。
    # ID建议使用 pkg_PRICE 格式，方便前端识别。
    RECHARGE_PACKAGES = {
        'pkg_10': {'name': '入门套餐', 'points': 100, 'price': 10.00},
        'pkg_50': {'name': '标准套餐', 'points': 600, 'price': 50.00},
        'pkg_100': {'name': '高级套餐', 'points': 1500, 'price': 100.00},
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
    # In development, prioritize DEV_DATABASE_URL, but fall back to the main DATABASE_URL.
    # The SQLite fallback is removed to enforce PostgreSQL usage across all environments.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL', os.environ.get('DATABASE_URL'))
    ALIPAY_DEBUG = True

class ProductionConfig(Config):
    """Production configuration."""
    ALIPAY_GATEWAY_URL = 'https://openapi.alipay.com/gateway.do' # 生产环境
    DEBUG = False
    pass

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
} 