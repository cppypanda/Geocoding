from alipay import AliPay
from flask import current_app

def get_alipay_client():
    """
    获取支付宝支付客户端实例。
    通过 current_app 从 Flask 的配置中动态获取支付宝相关配置，
    并初始化 AliPay SDK。
    """
    # 从 Flask app context 中获取配置
    # 这种方式可以确保我们总是在 app 的上下文中获取最新的配置
    app_private_key_string = (
        current_app.config.get('ALIPAY_PRIVATE_KEY')
        or current_app.config.get('APP_PRIVATE_KEY')
    )
    alipay_public_key_string = current_app.config.get('ALIPAY_PUBLIC_KEY')
    app_id = current_app.config.get('ALIPAY_APP_ID')

    if not all([app_private_key_string, alipay_public_key_string, app_id]):
        missing_keys = []
        if not app_id: missing_keys.append('ALIPAY_APP_ID')
        if not app_private_key_string: missing_keys.append('ALIPAY_PRIVATE_KEY/APP_PRIVATE_KEY')
        if not alipay_public_key_string: missing_keys.append('ALIPAY_PUBLIC_KEY')
        # 抛出更明确的异常，方便调试
        raise RuntimeError(f"支付宝配置缺失，请检查 .env 文件或环境变量: {', '.join(missing_keys)}")
    
    alipay = AliPay(
        appid=app_id,
        app_notify_url=None,  # 异步通知 url，后续在支付请求中单独指定
        app_private_key_string=app_private_key_string,
        alipay_public_key_string=alipay_public_key_string,
        sign_type="RSA2",  # RSA2 签名方式
        debug=current_app.config.get('ALIPAY_DEBUG', False)  # 使用独立的配置项控制支付宝环境
    )
    return alipay
