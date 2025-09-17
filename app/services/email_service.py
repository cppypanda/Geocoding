import os
import resend
from flask import current_app

def send_email(to_email, subject, body_html):
    """
    使用 Resend API 发送邮件。
    """
    # 从环境变量中获取 Resend API Key
    api_key = os.getenv('RESEND_API_KEY')
    sender_email = os.getenv('MAIL_DEFAULT_SENDER')
    
    if not api_key:
        current_app.logger.error("RESEND_API_KEY 环境变量未设置")
        raise ValueError("Resend API Key 未配置")
    
    if not sender_email:
        current_app.logger.error("MAIL_DEFAULT_SENDER 环境变量未设置")
        raise ValueError("发件人邮箱地址未配置")
    
    # 设置 Resend API Key
    resend.api_key = api_key
    
    try:
        current_app.logger.debug(f"准备通过 Resend 发送邮件至 {to_email}")
        
        # 调用 Resend API 发送邮件
        response = resend.emails.send({
            "from": sender_email,
            "to": [to_email],
            "subject": subject,
            "html": body_html,
        })
        
        current_app.logger.info(f"邮件已成功通过 Resend 发送，收件人: {to_email}, 邮件ID: {response.get('id', 'N/A')}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"通过 Resend 发送邮件时发生错误: {e}")
        raise Exception(f"邮件发送失败: {e}") 