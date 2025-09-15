// Notifications module: load list, render dropdown, update unread badge, mark as read
import { ENDPOINTS } from './constants.js';
import { showToast } from './utils.js';

let isLoading = false;
let pollTimer = null;

async function fetchJSON(url, options = {}) {
    try {
        const resp = await fetch(url, options);
        if (resp.status === 401) {
            // 当传入 __silent401 标记时，静默处理未登录（用于后台轮询）
            if (!options.__silent401) {
                handleUnauthorized();
            }
            return null;
        }
        const data = await resp.json();
        return data;
    } catch (e) {
        return null;
    }
}

function handleUnauthorized() {
    try {
        const loginModalElement = document.getElementById('loginRegisterModal');
        if (loginModalElement) {
            const loginModal = new bootstrap.Modal(loginModalElement);
            loginModal.show();
        } else {
            showToast('请先登录', 'warning');
        }
    } catch (e) {
        showToast('请先登录', 'warning');
    }
}

function setDropdownLoading() {
    const menu = document.getElementById('notification-dropdown-menu');
    if (!menu) return;
    menu.innerHTML = '<li><span class="dropdown-item-text text-muted text-center d-block">正在加载...</span></li>';
}

function renderNotificationsList(notifications) {
    const menu = document.getElementById('notification-dropdown-menu');
    if (!menu) return;
    menu.innerHTML = '';

    if (!Array.isArray(notifications) || notifications.length === 0) {
        menu.innerHTML = '<li><span class="dropdown-item-text text-muted text-center d-block">暂无通知</span></li>';
        return;
    }

    notifications.forEach((n) => {
        const li = document.createElement('li');
        const item = document.createElement('a');
        item.href = n.link || '#';
        item.className = 'dropdown-item d-flex align-items-start gap-2';
        item.style.whiteSpace = 'normal';

        const dot = document.createElement('span');
        dot.className = 'mt-1';
        dot.textContent = n.is_read ? '' : '•';
        dot.style.color = n.is_read ? '#ccc' : '#0d6efd';

        const contentWrap = document.createElement('div');
        contentWrap.className = 'flex-grow-1';

        const msg = document.createElement('div');
        msg.textContent = n.message || '';
        msg.style.wordBreak = 'break-word';

        const time = document.createElement('small');
        time.className = 'text-muted d-block';
        time.textContent = n.created_at || '';

        contentWrap.appendChild(msg);
        contentWrap.appendChild(time);

        item.appendChild(dot);
        item.appendChild(contentWrap);

        if (n.link) {
            item.addEventListener('click', (e) => {
                // Let default navigation happen; close dropdown
                try {
                    const dropdown = bootstrap.Dropdown.getInstance(document.getElementById('notification-bell-container'));
                    dropdown && dropdown.hide && dropdown.hide();
                } catch (err) {}
            });
        } else {
            item.addEventListener('click', (e) => e.preventDefault());
        }

        li.appendChild(item);
        menu.appendChild(li);
    });
}

function updateUnreadBadge(count) {
    const badge = document.getElementById('notification-badge');
    if (!badge) return;
    const c = Number(count) || 0;
    if (c > 0) {
        badge.classList.remove('d-none');
        badge.textContent = c > 99 ? '99+' : String(c);
        badge.style.fontSize = '0.6em';
    } else {
        badge.classList.add('d-none');
        badge.textContent = '';
    }
}

async function loadAndRenderNotifications() {
    if (isLoading) return;
    isLoading = true;
    setDropdownLoading();
    const data = await fetchJSON(`${ENDPOINTS.notificationsGet}?page=1&limit=10`);
    if (!data) {
        renderNotificationsList([]);
        isLoading = false;
        return;
    }
    if (data.success) {
        renderNotificationsList(data.notifications || []);
        // Mark unread as read
        const unreadIds = (data.notifications || []).filter(n => n && Number(n.is_read) === 0).map(n => n.id);
        if (unreadIds.length > 0) {
            await fetchJSON(ENDPOINTS.notificationsMarkRead, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: unreadIds })
            });
            // Refresh count after marking read
            await refreshUnreadCount();
        }
    } else {
        renderNotificationsList([]);
        showToast(data.message || '获取通知失败', 'warning');
    }
    isLoading = false;
}

async function refreshUnreadCount() {
    // 未登录时静默：不弹出登录框，不刷 toast
    const data = await fetchJSON(ENDPOINTS.notificationsUnreadCount, { __silent401: true });
    if (data && data.success) {
        updateUnreadBadge(data.unread_count || 0);
    } else if (data === null) {
        updateUnreadBadge(0);
    }
}

export function initializeNotifications() {
    try {
        const bell = document.getElementById('notification-bell-container');
        const menu = document.getElementById('notification-dropdown-menu');
        if (!bell || !menu) {
            return;
        }

        // When dropdown is about to show, load notifications
        bell.addEventListener('show.bs.dropdown', () => {
            loadAndRenderNotifications();
        });

        // Initial unread count and poll periodically
        refreshUnreadCount();
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(refreshUnreadCount, 30000);
    } catch (e) {
        // No-op
    }
}

// Optional: expose for debugging
window.__notifications = {
    refreshUnreadCount,
    loadAndRenderNotifications
};


