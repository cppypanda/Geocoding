import os
import resend
from resend import Emails
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
        
        # 调用 Resend API 发送邮件（兼容字符串或列表形式的收件人）
        to_list = to_email if isinstance(to_email, list) else [to_email]
        response = Emails.send({
            "from": sender_email,
            "to": to_list,
            "subject": subject,
            "html": body_html,
        })

        email_id = getattr(response, 'id', None)
        if email_id is None and isinstance(response, dict):
            email_id = response.get('id')
        current_app.logger.info(f"邮件已成功通过 Resend 发送，收件人: {to_list}, 邮件ID: {email_id or 'N/A'}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"通过 Resend 发送邮件时发生错误: {e}")
        raise Exception(f"邮件发送失败: {e}") 