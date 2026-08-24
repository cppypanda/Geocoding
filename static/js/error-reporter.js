(function () {
    'use strict';

    const recentErrors = new Map();
    const dedupeWindowMs = 60 * 1000;

    function sendError(payload) {
        const signature = [payload.kind, payload.type, payload.message, payload.location].join('|');
        const now = Date.now();
        if (recentErrors.has(signature) && now - recentErrors.get(signature) < dedupeWindowMs) {
            return;
        }
        recentErrors.set(signature, now);

        if (recentErrors.size > 100) {
            for (const [key, timestamp] of recentErrors) {
                if (now - timestamp >= dedupeWindowMs) recentErrors.delete(key);
            }
        }

        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (!csrfToken) return;

        const requestOptions = {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(payload)
        };
        fetch('/api/client-errors', requestOptions).catch(function () {
            // A worker restart can briefly reject both the original request and
            // this report. Retry once after the service has had time to recover.
            window.setTimeout(function () {
                fetch('/api/client-errors', requestOptions).catch(function () {
                    // Never report an error caused by the reporter itself.
                });
            }, 1500);
        });
    }

    // Allow application code to report errors that it intentionally catches.
    // Without this hook, fetch failures handled by the UI never reach the
    // administration error center.
    window.reportClientError = function (payload) {
        if (!payload || typeof payload !== 'object') return;
        sendError({
            kind: String(payload.kind || 'caught').slice(0, 64),
            type: String(payload.type || 'ClientError').slice(0, 255),
            message: String(payload.message || '浏览器端已捕获错误').slice(0, 4000),
            stack: String(payload.stack || '').slice(0, 20000),
            location: String(payload.location || window.location.pathname).split('?', 1)[0].slice(0, 2000),
            context: payload.context && typeof payload.context === 'object' ? payload.context : undefined
        });
    };

    window.addEventListener('error', function (event) {
        if (event.error) {
            sendError({
                kind: 'javascript',
                type: event.error.name || 'ClientError',
                message: event.message || event.error.message || '浏览器脚本错误',
                stack: event.error.stack || '',
                location: [event.filename, event.lineno, event.colno].filter(Boolean).join(':')
            });
            return;
        }

        const target = event.target;
        if (target && target !== window) {
            sendError({
                kind: 'resource',
                type: 'ResourceLoadError',
                message: '静态资源加载失败',
                stack: '',
                location: target.src || target.href || target.tagName || ''
            });
        }
    }, true);

    window.addEventListener('unhandledrejection', function (event) {
        const reason = event.reason;
        sendError({
            kind: 'promise',
            type: reason?.name || 'UnhandledPromiseRejection',
            message: reason?.message || String(reason || '未处理的 Promise 异常'),
            stack: reason?.stack || '',
            location: window.location.pathname
        });
    });
}());
