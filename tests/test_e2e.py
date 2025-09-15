import pytest
from playwright.sync_api import Page, expect

def test_user_can_login(live_server, page: Page, test_user):
    """
    测试一个真实用户可以通过前端界面成功登录。
    """
    # 1. 访问应用首页
    page.goto(live_server.url)

    # 2. 点击 "登录" 按钮以弹出登录模态框
    page.locator("#showLoginModalBtn").click()

    # 3. **终极解决方案**: 通过文本定位并点击 "账号密码登录" Tab
    # 这能确保我们切换到了正确的登录表单
    account_login_tab = page.locator("a:has-text('账号密码登录')")
    expect(account_login_tab).to_be_visible()
    account_login_tab.click()

    # 4. 等待用户名输入框出现并填写表单
    username_input = page.locator("#modalUsernameOrPhone")
    password_input = page.locator("#modalPassword")
    
    expect(username_input).to_be_visible()
    username_input.fill(test_user['username'])
    password_input.fill(test_user['password'])

    # 5. 点击 "账号密码登录" 按钮
    page.locator("#login-account-btn").click()

    # 6. 验证登录是否成功
    welcome_message = page.locator("#username-display")
    expect(welcome_message).to_have_text(test_user['username'])
    expect(page.locator("#showLoginModalBtn")).to_be_hidden() 