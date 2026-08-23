import hashlib
import json
import logging
import re
import sys
import threading
import traceback as traceback_module
from datetime import datetime

from flask import current_app, has_app_context, has_request_context, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .. import db
from ..models import ErrorRecord


_SENSITIVE_PARTS = (
    'authorization', 'cookie', 'password', 'passwd', 'secret', 'token',
    'api_key', 'apikey', 'private_key', 'pay_key', 'signature', 'csrf',
)
_ALLOWED_HEADERS = (
    'Accept', 'Content-Type', 'User-Agent', 'X-Requested-With',
    'X-Forwarded-For', 'X-Request-ID',
)
_MAX_MESSAGE_LENGTH = 4000
_MAX_CONTEXT_LENGTH = 20000
_local = threading.local()


def _truncate(value, limit):
    text = '' if value is None else str(value)
    return text if len(text) <= limit else f'{text[:limit]}\n...[已截断]'


def _is_sensitive(key):
    normalized = str(key).lower().replace('-', '_')
    return any(part in normalized for part in _SENSITIVE_PARTS)


def _redact_sensitive_text(value):
    text = '' if value is None else str(value)
    text = re.sub(
        r'(?i)([?&](?:access_token|token|api[_-]?key|secret|password)=)[^&#\s]+',
        r'\1[REDACTED]',
        text,
    )
    text = re.sub(
        r'(?i)((?:authorization|password|passwd|token|api[_-]?key|private[_-]?key|pay[_-]?key|secret)'
        r'\s*["\']?\s*[:=]\s*["\']?)[^"\'\s,&}]+',
        r'\1[REDACTED]',
        text,
    )
    return text


def _redact(value, key=''):
    if _is_sensitive(key):
        return '[REDACTED]'
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item, key) for item in value[:100]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _truncate(value, 2000)


def _json_text(value):
    if value in (None, {}, []):
        return None
    return _truncate(json.dumps(value, ensure_ascii=False, indent=2, default=str), _MAX_CONTEXT_LENGTH)


def _safe_request_path():
    if request.url_rule is not None:
        return _truncate(request.url_rule.rule, 4000)
    path = re.sub(r'(?<=/)[A-Za-z0-9._~-]{24,}(?=/|$)', '<redacted-segment>', request.path)
    return _truncate(path, 4000)


def _request_snapshot():
    snapshot = {
        'request_method': None,
        'request_path': None,
        'endpoint': None,
        'query_params': None,
        'request_payload': None,
        'request_headers': None,
        'user_id': None,
        'user_email': None,
        'client_ip': None,
        'user_agent': None,
    }
    if not has_request_context():
        return snapshot

    snapshot.update({
        'request_method': request.method,
        'request_path': _safe_request_path(),
        'endpoint': request.endpoint,
        'client_ip': _truncate(request.remote_addr, 64),
        'user_agent': _truncate(request.user_agent.string, 2000),
    })

    try:
        snapshot['query_params'] = _json_text(_redact(request.args.to_dict(flat=False)))
    except Exception:
        pass

    try:
        payload = request.get_json(silent=True)
        if payload is None and request.form:
            payload = request.form.to_dict(flat=False)
        snapshot['request_payload'] = _json_text(_redact(payload))
    except Exception:
        pass

    try:
        headers = {name: request.headers.get(name) for name in _ALLOWED_HEADERS if request.headers.get(name)}
        snapshot['request_headers'] = _json_text(_redact(headers))
    except Exception:
        pass

    try:
        if current_user.is_authenticated:
            snapshot['user_id'] = current_user.id
            snapshot['user_email'] = _truncate(getattr(current_user, 'email', None), 255)
    except Exception:
        pass

    return snapshot


def _normalize_message(message):
    text = str(message).lower()
    text = re.sub(r'\b[0-9a-f]{8}-[0-9a-f-]{27,}\b', '<uuid>', text)
    text = re.sub(r'\b0x[0-9a-f]+\b', '<hex>', text)
    text = re.sub(r'\b\d{3,}\b', '<number>', text)
    return _truncate(text, 1000)


def _fingerprint(exception_type, message, source, endpoint):
    identity = '|'.join((
        exception_type or 'Error',
        _normalize_message(message),
        source or '',
        endpoint or '',
    ))
    return hashlib.sha256(identity.encode('utf-8', errors='replace')).hexdigest()


def _persist_error(values):
    """Persist using an isolated session so error logging never commits request work."""
    session_factory = sessionmaker(bind=db.engine, expire_on_commit=False)
    session = session_factory()
    try:
        existing = session.query(ErrorRecord).filter_by(fingerprint=values['fingerprint']).one_or_none()
        if existing:
            existing.occurrence_count += 1
            existing.last_seen_at = values['last_seen_at']
            existing.severity = values['severity']
            existing.message = values['message']
            existing.traceback = values['traceback'] or existing.traceback
            for field in (
                'source', 'request_method', 'request_path', 'endpoint', 'query_params',
                'request_payload', 'request_headers', 'user_id', 'user_email',
                'client_ip', 'user_agent', 'environment', 'release',
            ):
                if values.get(field) is not None:
                    setattr(existing, field, values[field])
            if existing.status == 'resolved':
                existing.status = 'open'
                existing.resolved_at = None
                existing.resolved_by_id = None
            session.commit()
            return existing.id

        item = ErrorRecord(**values)
        session.add(item)
        session.commit()
        return item.id
    except IntegrityError:
        # Another worker may have inserted the same fingerprint concurrently.
        session.rollback()
        existing = session.query(ErrorRecord).filter_by(fingerprint=values['fingerprint']).one_or_none()
        if existing:
            existing.occurrence_count += 1
            existing.last_seen_at = values['last_seen_at']
            session.commit()
            return existing.id
    except Exception:
        session.rollback()
    finally:
        session.close()
    return None


def capture_error(message, *, exception_type='LogError', severity='error', source='application',
                  traceback_text=None):
    """Store an error without allowing the error center itself to break the app."""
    if not has_app_context() or not current_app.config.get('ERROR_CENTER_ENABLED', True):
        return None
    if getattr(_local, 'capturing', False):
        return None

    _local.capturing = True
    try:
        message = _redact_sensitive_text(message)
        traceback_text = _redact_sensitive_text(traceback_text) if traceback_text else None
        request_values = _request_snapshot()
        now = datetime.utcnow()
        values = {
            'fingerprint': _fingerprint(exception_type, message, source, request_values['endpoint']),
            'status': 'open',
            'severity': _truncate(severity.lower(), 20),
            'source': _truncate(source, 255),
            'exception_type': _truncate(exception_type, 255) or 'Error',
            'message': _truncate(message, _MAX_MESSAGE_LENGTH) or '未知错误',
            'traceback': _truncate(traceback_text, _MAX_CONTEXT_LENGTH) or None,
            'environment': _truncate(current_app.config.get('ENV') or current_app.config.get('FLASK_ENV'), 64) or None,
            'release': _truncate(current_app.config.get('APP_RELEASE') or current_app.config.get('RENDER_GIT_COMMIT'), 128) or None,
            'occurrence_count': 1,
            'first_seen_at': now,
            'last_seen_at': now,
            **request_values,
        }
        return _persist_error(values)
    except Exception:
        return None
    finally:
        _local.capturing = False


def capture_exception(exception, *, source='unhandled_exception', severity='error'):
    trace = ''.join(traceback_module.format_exception(
        type(exception), exception, exception.__traceback__
    ))
    return capture_error(
        str(exception) or exception.__class__.__name__,
        exception_type=exception.__class__.__name__,
        severity=severity,
        source=source,
        traceback_text=trace,
    )


class ErrorCenterHandler(logging.Handler):
    def __init__(self, app):
        super().__init__(level=logging.ERROR)
        self.app = app

    def emit(self, record):
        if getattr(record, 'error_center_skip', False):
            return
        try:
            message = record.getMessage()
            exception_type = 'LogError'
            trace = None
            if record.exc_info:
                exception_type = record.exc_info[0].__name__
                trace = ''.join(traceback_module.format_exception(*record.exc_info))
            with self.app.app_context():
                capture_error(
                    message,
                    exception_type=exception_type,
                    severity=record.levelname.lower(),
                    source=f'log:{record.name}',
                    traceback_text=trace,
                )
        except Exception:
            # Logging must never create a second application failure.
            return


def init_error_center(app):
    for existing in list(app.logger.handlers):
        if isinstance(existing, ErrorCenterHandler):
            app.logger.removeHandler(existing)
    handler = ErrorCenterHandler(app)
    handler.setLevel(logging.ERROR)
    app.logger.addHandler(handler)
    app.extensions['error_center_handler'] = handler
