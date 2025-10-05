import { showToast, createAndAppendElement } from './utils.js';
import { ENDPOINTS } from './constants.js';

// This module handles user session management and related UI updates.

function updateUsernameCharCount() {
    const usernameInput = document.getElementById('settingsUsername');
    const charCount = document.getElementById('usernameCharCount');
    if (usernameInput && charCount) {
        charCount.textContent = `${usernameInput.value.length}/20`;
    }
}

/**
 * Updates the user bar UI based on login status.
 * @param {object|null} user - The user object, or null if logged out.
 */
export function updateUserBar(user = null) {
    const userUnsignedDiv = document.getElementById('user-unsigned');
    const userSignedDiv = document.getElementById('user-signed');
    const usernameDisplay = document.getElementById('username-display');
    const userPointsDisplay = document.getElementById('user-points');
    const settingsEmailInput = document.getElementById('settingsEmail');

    const existingAdminBtn = document.getElementById('admin-panel-btn');
    if (existingAdminBtn) {
        existingAdminBtn.remove();
    }

    if (!userUnsignedDiv || !userSignedDiv || !usernameDisplay || !userPointsDisplay) {
        return;
    }

    if (user) {
        userUnsignedDiv.classList.add('d-none');
        userSignedDiv.classList.remove('d-none');
        usernameDisplay.textContent = user.username || user.email.split('@')[0];
        userPointsDisplay.textContent = user.points !== undefined ? user.points : 0;
        if(settingsEmailInput) settingsEmailInput.value = user.email;

        if (user.is_admin === 1) {
            const adminBtn = createAndAppendElement('a', {
                href: '/admin/orders',
                className: 'btn btn-outline-danger btn-sm me-2',
                id: 'admin-panel-btn',
                textContent: '后台管理'
            });
            userSignedDiv.insertBefore(adminBtn, userSignedDiv.firstChild);
        }
    } else {
        userUnsignedDiv.classList.remove('d-none');
        userSignedDiv.classList.add('d-none');
        if(settingsEmailInput) settingsEmailInput.value = '';
    }
}

/**
 * Displays the login modal.
 */
export function showLoginModal() {
    const loginModalElement = document.getElementById('loginRegisterModal');
    if (!loginModalElement) return;
    const loginModal = new bootstrap.Modal(loginModalElement);
    loginModal.show();
}

/**
 * 刷新“API Key配置”面板的已配置状态显示
 * 从 /user/keys 获取已保存的 Key（掩码），并更新帮助文本
 */
async function refreshApiKeysStatus() {
    const helpIdByService = {
        amap: 'amapKeyHelpText',
        baidu: 'baiduKeyHelpText',
        tianditu: 'tiandituKeyHelpText',
        zhipuai: 'aiKeyHelpText'
    };
    
    // 从全局变量（由模板注入）或回退到空对象来获取奖励配置
    const pointsAwardConfig = window.__POINTS_AWARD_BY_SERVICE__ || {};

    // 先设置为默认文案（未配置）
    for (const [serviceName, helpId] of Object.entries(helpIdByService)) {
        const helpEl = document.getElementById(helpId);
        if (helpEl) {
            const award = pointsAwardConfig[serviceName] || 0;
            helpEl.textContent = `成功配置后，您将获得${award}积分。`;
            helpEl.classList.add('text-muted');
            helpEl.classList.remove('text-success');
        }
    }

    try {
        const resp = await fetch(ENDPOINTS.userKeys);
        if (resp.status === 401) return; // 未登录则忽略
        const data = await resp.json();
        if (!resp.ok || !data.success) return;

        const keyedByService = {};
        for (const item of (data.keys || [])) {
            keyedByService[item.service_name] = item;
        }

        for (const [serviceName, helpId] of Object.entries(helpIdByService)) {
            const helpEl = document.getElementById(helpId);
            if (!helpEl) continue;
            const item = keyedByService[serviceName];
            if (item && item.masked_key) {
                helpEl.textContent = `已保存：${item.masked_key}`;
                helpEl.classList.remove('text-muted');
                helpEl.classList.add('text-success');
            }
        }
    } catch (e) {
        // 静默失败，不阻塞页面
    }
}

/**
 * Checks the user's login status with the server.
 * @returns {Promise<object>} An object like { logged_in: boolean, user: object|null }.
 */
export async function checkLoginStatus() {
    try {
        const response = await fetch(ENDPOINTS.checkLogin);
        const data = await response.json();
        if (data.logged_in && data.user) {
            updateUserBar(data.user);
            return data; // 返回整个data对象 { logged_in: true, user: {...} }
        } else {
            updateUserBar(null);
            return { logged_in: false }; // 返回一个表示未登录的对象
        }
    } catch (error) {
        console.error("checkLoginStatus failed:", error);
        updateUserBar(null);
        return { logged_in: false }; // 出错时也返回一个表示未登录的对象
    }
}

/**
 * Handles the logout process.
 * @param {Event} [event] - The click event, if any.
 */
export async function handleLogout(event) {
    if (event) event.preventDefault();
    try {
        const response = await fetch(ENDPOINTS.logout);
        const data = await response.json();
        if (data.success) {
            updateUserBar(null);
            showToast('已退出登录', 'success');
        } else {
            showToast(data.message || '退出失败', 'error');
        }
    } catch (error) {
        showToast('退出请求失败', 'error');
    }
}

/**
 * Handles the account login form submission.
 */
async function handleAccountLogin(event) {
    event.preventDefault();
    const form = event.target;
    const usernameOrEmailInput = form.querySelector('#modalUsernameOrEmail');
    const passwordInput = form.querySelector('#modalPassword');

    const username_or_email = usernameOrEmailInput.value.trim();
    const password = passwordInput.value.trim();

    if (!username_or_email || !password) {
        showToast('邮箱/用户名和密码不能为空', 'warning');
        return;
    }

    try {
        const response = await fetch(ENDPOINTS.loginAccount, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username_or_email, password }),
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message || '登录成功', 'success');
            updateUserBar(data.user);
            // 登录成功后刷新API配置状态
            refreshApiKeysStatus();
            // 登录后尝试绑定推荐关系
            try { await tryBindReferralIfPresent(); } catch (e) {}
            const loginModal = bootstrap.Modal.getInstance(document.getElementById('loginRegisterModal'));
            if (loginModal) loginModal.hide();
        } else {
            showToast(data.message || '登录失败', 'error');
        }
    } catch (error) {
        showToast('登录过程中发生错误', 'error');
    }
}

/**
 * Handles the email login/register form submission.
 */
async function handleEmailLoginRegister(event) {
    event.preventDefault();
    const form = event.target;
    const emailInput = form.querySelector('#modalEmail');
    const codeInput = form.querySelector('#modalVerificationCode');
    const agreeTermsCheckbox = form.querySelector('#modalAgreeTerms');

    const email = emailInput.value.trim();
    const code = codeInput.value.trim();

    if (!email || !code) {
        showToast('邮箱和验证码不能为空', 'warning');
        return;
    }
    if (!agreeTermsCheckbox || !agreeTermsCheckbox.checked) {
        showToast('请阅读并同意用户服务协议和隐私政策', 'warning');
        return;
    }

    try {
        const response = await fetch(ENDPOINTS.loginRegisterEmail, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, code }),
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message || '操作成功', 'success');
            updateUserBar(data.user);
            // 登录成功后刷新API配置状态
            refreshApiKeysStatus();
            // 登录后尝试绑定推荐关系
            try { await tryBindReferralIfPresent(); } catch (e) {}
            const loginModal = bootstrap.Modal.getInstance(document.getElementById('loginRegisterModal'));
            if (loginModal) loginModal.hide();
        } else {
            showToast(data.message || '操作失败', 'error');
        }
    } catch (error) {
        showToast('操作过程中发生错误', 'error');
    }
}

/**
 * Handles the register/set password form submission.
 */
async function handleRegisterSetPassword(event) {
    event.preventDefault();
    const form = event.target;
    const emailInput = form.querySelector('#registerEmail');
    const codeInput = form.querySelector('#registerVerificationCode');
    const passwordInput = form.querySelector('#registerPassword');
    const confirmPasswordInput = form.querySelector('#registerConfirmPassword');
    const agreeTermsCheckbox = form.querySelector('#registerAgreeTerms');

    const email = emailInput.value.trim();
    const code = codeInput.value.trim();
    const password = passwordInput.value.trim();
    const confirm_password = confirmPasswordInput.value.trim();

    if (!email || !code || !password || !confirm_password) {
        showToast('所有字段都不能为空', 'warning');
        return;
    }
    if (password !== confirm_password) {
        showToast('两次输入的密码不一致', 'warning');
        return;
    }
    if (password.length < 6) {
        showToast('密码长度至少为6位', 'warning');
        return;
    }
    if (!agreeTermsCheckbox || !agreeTermsCheckbox.checked) {
        showToast('请阅读并同意用户服务协议和隐私政策', 'warning');
        return;
    }
    
    try {
        const response = await fetch(ENDPOINTS.registerSetPassword, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, code, password, username: email.split('@')[0] }), // Default username from email
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message || '注册成功', 'success');
            updateUserBar(data.user);
            const loginModal = bootstrap.Modal.getInstance(document.getElementById('loginRegisterModal'));
            if (loginModal) loginModal.hide();
        } else {
            showToast(data.message || '注册失败', 'error');
        }
    } catch (error) {
        showToast('注册过程中发生错误', 'error');
    }
}

/**
 * Handles sending verification code for the registration/set password form.
 */
async function handleSendVerificationCode(event) {
    const button = event.target;
    const purpose = button.dataset.purpose;
    let email = '';

    if (purpose === 'register_login') {
        email = document.getElementById('modalEmail')?.value.trim();
    } else if (purpose === 'register_or_set_password') {
        email = document.getElementById('registerEmail')?.value.trim();
    } else if (purpose === 'reset_password') {
        email = document.getElementById('forgotEmail')?.value.trim();
    }

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        showToast('请输入一个有效的邮箱地址', 'warning');
        return;
    }

    button.disabled = true;
    let countdown = 60;
    const originalText = button.textContent;
    button.textContent = `重新发送 (${countdown})`;

    const interval = setInterval(() => {
        countdown--;
        button.textContent = `重新发送 (${countdown})`;
        if (countdown <= 0) {
            clearInterval(interval);
            button.textContent = originalText;
            button.disabled = false;
        }
    }, 1000);

    try {
        const response = await fetch(ENDPOINTS.sendVerificationCode, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, purpose }),
        });
        const data = await response.json();
        if (!data.success) {
            showToast(data.message || '发送失败', 'error');
            clearInterval(interval);
            button.textContent = originalText;
            button.disabled = false;
        } else {
            showToast(data.message || '验证码已发送', 'success');
        }
    } catch (error) {
        showToast('发送验证码请求失败', 'error');
        clearInterval(interval);
        button.textContent = originalText;
        button.disabled = false;
    }
}

/**
 * Initializes event listeners for all authentication forms.
 * This should be called once on DOMContentLoaded.
 */
export function initializeAuthForms() {
    // 登录按钮事件监听器
    const showLoginModalBtn = document.getElementById('showLoginModalBtn');
    if (showLoginModalBtn) {
        showLoginModalBtn.addEventListener('click', () => {
            showLoginModal();
        });
    }
    
    // Switch between forms
    const switchToRegisterSetPasswordSms = document.getElementById('switchToRegisterSetPasswordFromEmail');
    const switchToRegisterSetPassword = document.getElementById('switchToRegisterSetPassword');
    const backToLoginLink = document.getElementById('backToLoginLink');
    const forgotPasswordLink = document.getElementById('forgotPasswordLink');
    const backToLoginFromForgotLink = document.getElementById('backToLoginFromForgotLink');
    
    const loginRegisterModalEl = document.getElementById('loginRegisterModal');
    const forgotPasswordModalEl = document.getElementById('forgotPasswordModal');

    if (loginRegisterModalEl) {
        const loginRegisterModal = new bootstrap.Modal(loginRegisterModalEl);
        
        const go_to_register_handler = (e) => {
            e.preventDefault();
            document.getElementById('loginRegisterTabContent').classList.add('d-none');
            document.getElementById('register-set-password-pane').classList.remove('d-none');
        };

        switchToRegisterSetPasswordSms?.addEventListener('click', go_to_register_handler);
        switchToRegisterSetPassword?.addEventListener('click', go_to_register_handler);

        backToLoginLink?.addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('loginRegisterTabContent').classList.remove('d-none');
            document.getElementById('register-set-password-pane').classList.add('d-none');
            // Manually show the first tab (account login) to re-initialize the component
            const firstTabEl = document.querySelector('#loginRegisterTabs button[data-bs-target="#account-login-pane"]');
            if(firstTabEl) {
                const firstTab = new bootstrap.Tab(firstTabEl);
                firstTab.show();
            }
        });
        
        forgotPasswordLink?.addEventListener('click', (e) => {
            e.preventDefault();
            const forgotPasswordModal = new bootstrap.Modal(forgotPasswordModalEl);
            loginRegisterModal.hide();
            forgotPasswordModal.show();
        });
    }

    if (forgotPasswordModalEl) {
        const forgotPasswordModal = new bootstrap.Modal(forgotPasswordModalEl);
        backToLoginFromForgotLink?.addEventListener('click', (e) => {
            e.preventDefault();
            const loginRegisterModal = new bootstrap.Modal(loginRegisterModalEl);
            forgotPasswordModal.hide();
            loginRegisterModal.show();
        });
    }

    // Form Submissions
    document.getElementById('loginModalForm')?.addEventListener('submit', handleEmailLoginRegister);
    document.getElementById('accountLoginForm')?.addEventListener('submit', handleAccountLogin);
    document.getElementById('registerSetPasswordForm')?.addEventListener('submit', handleRegisterSetPassword);
    document.getElementById('forgotPasswordForm')?.addEventListener('submit', handleResetPassword);

    // Send Code Buttons
    document.getElementById('modalSendVerificationCodeBtn')?.addEventListener('click', handleSendVerificationCode);
    document.getElementById('registerSendVerificationCodeBtn')?.addEventListener('click', handleSendVerificationCode);
    document.getElementById('sendForgotVerificationCodeBtn')?.addEventListener('click', handleSendVerificationCode);
    
    // Assign purpose to buttons
    if (document.getElementById('modalSendVerificationCodeBtn')) document.getElementById('modalSendVerificationCodeBtn').dataset.purpose = 'register_login';
    if (document.getElementById('registerSendVerificationCodeBtn')) document.getElementById('registerSendVerificationCodeBtn').dataset.purpose = 'register_or_set_password';
    if (document.getElementById('sendForgotVerificationCodeBtn')) document.getElementById('sendForgotVerificationCodeBtn').dataset.purpose = 'reset_password';

    // Settings form
    document.getElementById('saveSettingsBtn')?.addEventListener('click', handleUpdateProfile);
    document.getElementById('settingsUsername')?.addEventListener('input', updateUsernameCharCount);

    // 修改密码按钮
    document.getElementById('changePasswordBtn')?.addEventListener('click', handleChangePassword);

    // API Keys 面板：保存按钮
    document.getElementById('saveApiKeysBtn')?.addEventListener('click', handleSaveApiKeys);

    // 如果设置模态已经存在，则在显示时刷新 Key 状态
    const settingsModalEl = document.getElementById('settingsModal');
    if (settingsModalEl) {
        settingsModalEl.addEventListener('shown.bs.modal', () => {
            // 只有当切换到 apikeys-pane 时才刷新，但简单起见，每次打开都刷新一次
            refreshApiKeysStatus();
        });
    }

    // 当“Key配置”Tab被激活时刷新状态，避免用户先打开设置再点到Key页签时未刷新
    const apikeysTabBtnForRefresh = document.getElementById('apikeys-tab');
    if (apikeysTabBtnForRefresh) {
        apikeysTabBtnForRefresh.addEventListener('shown.bs.tab', () => {
            refreshApiKeysStatus();
        });
    }

    // 从“免费赚积分”入口直接打开 Key 配置页
    document.getElementById('openApiKeysTabBtn')?.addEventListener('click', handleOpenApiKeysTab);

    // 初始化“分享推荐”卡片逻辑
    initializeReferralCard();
}

/**
 * Handles the reset password form submission.
 */
async function handleResetPassword(event) {
    event.preventDefault();
    const form = event.target;
    const emailInput = form.querySelector('#forgotEmail');
    const codeInput = form.querySelector('#forgotVerificationCode');
    const newPasswordInput = form.querySelector('#newPassword');
    const confirmPasswordInput = form.querySelector('#confirmNewPassword');
    
    const email = emailInput.value.trim();
    const code = codeInput.value.trim();
    const new_password = newPasswordInput.value.trim();
    const confirm_password = confirmPasswordInput.value.trim();

    if (!email || !code || !new_password || !confirm_password) {
        showToast('所有字段都不能为空', 'warning');
        return;
    }
    if (new_password !== confirm_password) {
        showToast('两次输入的密码不一致', 'warning');
        return;
    }
    if (new_password.length < 6) {
        showToast('新密码长度至少为6位', 'warning');
        return;
    }

    try {
        const response = await fetch(ENDPOINTS.resetPassword, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, code, new_password }),
        });
        const data = await response.json();
        if (data.success) {
            showToast('密码重置成功', 'success');
            const forgotPasswordModal = bootstrap.Modal.getInstance(document.getElementById('forgotPasswordModal'));
            if(forgotPasswordModal) forgotPasswordModal.hide();
            showLoginModal();
        } else {
            showToast(data.message || '密码重置失败', 'error');
        }
    } catch (error) {
        showToast('密码重置过程中发生错误', 'error');
    }
}

/**
 * 处理“设置-修改密码”提交
 */
async function handleChangePassword() {
    const oldPassword = document.getElementById('oldPassword')?.value.trim() || '';
    const newPassword = document.getElementById('newPasswordInSettings')?.value.trim() || '';
    const confirmPassword = document.getElementById('confirmNewPasswordInSettings')?.value.trim() || '';

    if (!oldPassword || !newPassword || !confirmPassword) {
        showToast('所有字段都不能为空', 'warning');
        return;
    }
    if (newPassword !== confirmPassword) {
        showToast('两次输入的新密码不一致', 'warning');
        return;
    }
    if (newPassword.length < 6) {
        showToast('新密码长度至少为6位', 'warning');
        return;
    }

    const btn = document.getElementById('changePasswordBtn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="bi bi-hourglass-split"></i> 保存中...';
    }

    try {
        const resp = await fetch(ENDPOINTS.changePassword, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword, confirm_password: confirmPassword })
        });
        const data = await resp.json().catch(() => ({ success: false, message: '请求失败' }));
        if (!resp.ok || !data.success) {
            showToast(data.message || '修改密码失败', 'error');
        } else {
            showToast(data.message || '密码已更新', 'success');
            // 关闭设置窗口并清空输入
            try {
                document.getElementById('oldPassword').value = '';
                document.getElementById('newPasswordInSettings').value = '';
                document.getElementById('confirmNewPasswordInSettings').value = '';
            } catch (e) {}
            const settingsModal = bootstrap.Modal.getInstance(document.getElementById('settingsModal')) || new bootstrap.Modal(document.getElementById('settingsModal'));
            settingsModal && settingsModal.hide && settingsModal.hide();
            // 建议用户重新登录
            setTimeout(() => {
                showLoginModal();
            }, 400);
        }
    } catch (e) {
        showToast('修改密码请求失败', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '保存新密码';
        }
    }
}

async function handleUpdateProfile(event) {
    event.preventDefault();
    const newUsername = document.getElementById('settingsUsername').value.trim();
    if (!newUsername) {
        showToast('用户名不能为空', 'warning');
        return;
    }

    try {
        const response = await fetch('/update_user_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: newUsername }),
        });
        const data = await response.json();
        if (data.success) {
            showToast('用户信息更新成功', 'success');
            updateUserBar(data.user);
            const settingsModal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
            if(settingsModal) settingsModal.hide();
        } else {
            showToast(data.message || '更新失败', 'error');
        }
    } catch (error) {
        showToast('更新过程中发生错误', 'error');
    }
}

/**
 * 打开设置模态并切换到 API Keys 面板
 */
function handleOpenApiKeysTab() {
    try {
        // 关闭“免费赚积分”模态
        const freePointsModalEl = document.getElementById('freePointsModal');
        if (freePointsModalEl) {
            const freePointsModal = bootstrap.Modal.getInstance(freePointsModalEl) || new bootstrap.Modal(freePointsModalEl);
            freePointsModal.hide();
        }
    } catch (e) {}

    const settingsModalEl = document.getElementById('settingsModal');
    if (!settingsModalEl) return;
    const settingsModal = bootstrap.Modal.getInstance(settingsModalEl) || new bootstrap.Modal(settingsModalEl);
    settingsModal.show();

    // 激活 Key 配置 Tab
    setTimeout(() => {
        const apikeysTabBtn = document.getElementById('apikeys-tab');
        if (apikeysTabBtn) {
            try {
                const bsTab = new bootstrap.Tab(apikeysTabBtn);
                bsTab.show();
            } catch (e) {}
        }
        // 将焦点定位到第一个 Key 输入框，便于输入
        document.getElementById('settingsAmapKey')?.focus();
        // 刷新当前用户已配置的 Key 状态
        refreshApiKeysStatus();
    }, 50);
}

/**
 * 初始化“分享推荐”展示与复制、绑定逻辑
 */
function initializeReferralCard() {
    const codeText = document.getElementById('referralCodeText');
    const linkInput = document.getElementById('referralLinkInput');
    const copyCodeBtn = document.getElementById('copyReferralCodeBtn');
    const copyLinkBtn = document.getElementById('copyReferralLinkBtn');
    const statsText = document.getElementById('referralStatsText');

    if (!codeText || !linkInput) return;

    // 加载用户推荐信息
    (async () => {
        try {
            const resp = await fetch(ENDPOINTS.referralInfo);
            if (resp.status === 401) return; // 未登录则不处理
            const data = await resp.json();
            if (!resp.ok || !data.success) return;
            codeText.textContent = data.referral_code || '--';
            linkInput.value = data.share_link || '';
            if (statsText && data.stats) {
                const n = Number(data.stats.total_invitees || 0);
                statsText.textContent = `已成功邀请 ${n} 人`;
            }
        } catch (e) {}
    })();

    // 通用复制方法（带回退）
    async function copyTextWithFallback(text, fallbackElement) {
        const content = (text || '').toString();
        if (!content) return false;
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(content);
                return true;
            }
        } catch (e) { /* 回退到execCommand */ }

        try {
            if (fallbackElement && typeof fallbackElement.select === 'function') {
                const prevReadOnly = fallbackElement.readOnly;
                try { fallbackElement.readOnly = false; } catch (e) {}
                fallbackElement.focus();
                fallbackElement.select();
                const ok = document.execCommand && document.execCommand('copy');
                try { fallbackElement.setSelectionRange(0, 0); } catch (e) {}
                try { fallbackElement.blur(); } catch (e) {}
                try { fallbackElement.readOnly = prevReadOnly; } catch (e) {}
                if (ok) return true;
            }
        } catch (e) { /* 继续用临时textarea */ }

        try {
            const ta = document.createElement('textarea');
            ta.value = content;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            const ok = document.execCommand && document.execCommand('copy');
            document.body.removeChild(ta);
            return !!ok;
        } catch (e) {
            return false;
        }
    }

    copyCodeBtn && copyCodeBtn.addEventListener('click', async () => {
        const text = (codeText.textContent || '').trim();
        if (!text) { showToast('推荐码尚未生成，请稍后重试', 'warning'); return; }
        const ok = await copyTextWithFallback(text, null);
        showToast(ok ? '推荐码已复制' : '复制失败，请手动选择复制', ok ? 'success' : 'error');
    });

    copyLinkBtn && copyLinkBtn.addEventListener('click', async () => {
        const link = (linkInput.value || '').trim();
        if (!link) { showToast('邀请链接尚未生成，请登录后重试', 'warning'); return; }
        const ok = await copyTextWithFallback(link, linkInput);
        showToast(ok ? '邀请链接已复制' : '复制失败，请手动选择复制', ok ? 'success' : 'error');
    });
}

/**
 * 登录成功后，若URL或本地存储存在推荐码，则尝试绑定
 */
async function tryBindReferralIfPresent() {
    try {
        // 优先从URL读取 ?ref=CODE
        const params = new URLSearchParams(window.location.search || '');
        let code = (params.get('ref') || '').trim();
        if (!code) {
            // 其次从localStorage
            code = (localStorage.getItem('pending_referral_code') || '').trim();
        }
        if (!code) return;

        const resp = await fetch(ENDPOINTS.referralBind, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ referral_code: code })
        });
        const data = await resp.json().catch(() => ({ success: false }));
        if (data && data.success) {
            showToast('已绑定推荐关系，积分将稍后到账', 'success');
            // 清理URL与localStorage
            try {
                const url = new URL(window.location.href);
                url.searchParams.delete('ref');
                window.history.replaceState({}, '', url.toString());
            } catch (e) {}
            try { localStorage.removeItem('pending_referral_code'); } catch (e) {}
        } else if (resp.status === 409) {
            // 已绑定过，不重复提示
        } else if (resp.status === 404) {
            // 无效推荐码，不提示
        }
    } catch (e) {}
}

/**
 * 保存 API Keys（逐项提交到 /user/keys）
 */
async function handleSaveApiKeys() {
    const saveBtn = document.getElementById('saveApiKeysBtn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 保存中...';
    }

    // 收集所有带 data-service-name 的输入
    const pane = document.getElementById('apikeys-pane');
    const inputs = pane ? Array.from(pane.querySelectorAll('input[data-service-name]')) : [];
    if (!inputs.length) {
        showToast('未找到可保存的 Key 输入项', 'warning');
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = '保存API Keys';
        }
        return;
    }

    let anySuccess = false;
    let awardedPointsTotal = 0;
    const helpIdByService = {
        amap: 'amapKeyHelpText',
        baidu: 'baiduKeyHelpText',
        tianditu: 'tiandituKeyHelpText',
        zhipuai: 'aiKeyHelpText'
    };

    // 逐项保存（串行，便于逐条提示与配额控制）
    for (const input of inputs) {
        const serviceName = input.dataset.serviceName;
        const apiKey = (input.value || '').trim();
        if (!serviceName || !apiKey) continue; // 空值跳过，不做清空逻辑

        try {
            const resp = await fetch(ENDPOINTS.userKeys, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ service_name: serviceName, api_key: apiKey })
            });

            if (resp.status === 401) {
                showToast('请先登录后再保存 Key', 'warning');
                break;
            }

            const data = await resp.json();
            if (!resp.ok || !data.success) {
                showToast(data.message || `${serviceName} Key 保存失败`, 'error');
                continue;
            }

            anySuccess = true;
            const awarded = Number(data.points_awarded || 0) || 0;
            awardedPointsTotal += awarded;
            showToast(data.message || `${serviceName} Key 保存成功`, 'success');
            // 成功后清空输入并在帮助文本处展示掩码
            try {
                input.value = '';
                const helpId = helpIdByService[serviceName];
                const helpEl = helpId ? document.getElementById(helpId) : null;
                if (helpEl && data.masked_key) {
                    helpEl.textContent = `已保存：${data.masked_key}${awarded > 0 ? `（本次 +${awarded} 积分）` : ''}`;
                }
            } catch (e) {}
        } catch (err) {
            showToast(`${serviceName} Key 保存请求失败`, 'error');
        }
    }

    // 刷新用户栏积分和API配置状态
    try {
        if (anySuccess) {
            const res = await fetch(ENDPOINTS.checkLogin);
            const json = await res.json();
            if (json && json.logged_in && json.user) {
                updateUserBar(json.user);
            }
            // 刷新API配置状态显示
            refreshApiKeysStatus();
        }
    } catch (e) {}

    if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = '保存API Keys';
    }
}
