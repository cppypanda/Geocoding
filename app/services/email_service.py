import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from flask import current_app

def send_email(to_email, subject, body_html):
    """
    使用 SMTP 发送邮件。
    """
    # 从 Flask 配置中获取邮件服务器信息
    mail_server = current_app.config.get('MAIL_SERVER')
    mail_port = current_app.config.get('MAIL_PORT')
    use_ssl = current_app.config.get('MAIL_USE_SSL')
    mail_username = current_app.config.get('MAIL_USERNAME')
    mail_password = current_app.config.get('MAIL_PASSWORD')
    sender_email = current_app.config.get('MAIL_DEFAULT_SENDER')

    if not all([mail_server, mail_port, mail_username, mail_password]):
        current_app.logger.error("邮件服务配置不完整 (SMTP)。")
        raise ValueError("邮件服务未完整配置。")

    # 创建邮件内容
    message = MIMEText(body_html, 'html', 'utf-8')
    # 修复发件人名称编码问题：使用邮箱地址而不是中文名称避免编码问题
    # 如果 MAIL_DEFAULT_SENDER 包含中文，使用 MAIL_USERNAME 作为发件人
    try:
        # 尝试编码发件人地址以检测是否有中文字符
        sender_email.encode('ascii')
        sender_name = "GeoCo"  # 使用英文名称
    except UnicodeEncodeError:
        # 如果发件人地址包含非ASCII字符，使用用户名
        sender_name = "GeoCo"
        sender_email = mail_username
    
    message['From'] = formataddr((sender_name, sender_email))
    message['To'] = to_email
    message['Subject'] = Header(subject, 'utf-8')

    try:
        # 启用详细的调试日志
        current_app.logger.debug(f"准备连接SMTP服务器: {mail_server}:{mail_port}")
        
        # 连接到 SMTP 服务器
        if use_ssl:
            smtp_client = smtplib.SMTP_SSL(mail_server, mail_port, timeout=10)
        else:
            smtp_client = smtplib.SMTP(mail_server, mail_port, timeout=10)
        
        # 开启调试模式，日志会打印在控制台
        smtp_client.set_debuglevel(1)

        if not use_ssl:
            smtp_client.starttls() # 如果不是SSL端口，尝试使用TLS加密

        # 登录并发送邮件
        current_app.logger.debug(f"使用用户名 {mail_username} 登录...")
        smtp_client.login(mail_username, mail_password)
        
        current_app.logger.debug(f"邮件准备发送至 {to_email}...")
        # 修复中文编码问题：使用 as_bytes() 方法处理包含中文的邮件
        smtp_client.sendmail(sender_email, [to_email], message.as_bytes())
        current_app.logger.debug("邮件已发送，正在关闭SMTP连接。")
        smtp_client.quit()
        
        # 修改日志信息，使其更准确
        current_app.logger.info(f"邮件已成功提交至SMTP服务器，收件人: {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        current_app.logger.error("SMTP认证失败。请检查邮箱地址和授权码。")
        raise Exception("SMTP认证失败，请检查配置。")
    except Exception as e:
        current_app.logger.error(f"通过SMTP发送邮件时发生错误: {e}")
        raise Exception(f"邮件发送失败: {e}") 