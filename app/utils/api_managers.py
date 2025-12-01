import time
from collections import deque
import os
import asyncio
import random
from flask import current_app
from datetime import datetime, timedelta

from .. import db
from ..models import User, UserApiKey

# Constants for failure reasons
REASON_INVALID = 'invalid'
REASON_QUOTA_EXCEEDED = 'quota_exceeded'
REASON_RATE_LIMITED = 'rate_limited'
REASON_OTHER = 'other'

class APIKeyManager:
    def __init__(self, service_name, default_key=None):
        self.service_name = service_name
        self.system_keys = []
        if default_key:
            # 支持多个Key，使用逗号分隔
            if ',' in default_key:
                self.system_keys = [k.strip() for k in default_key.split(',') if k.strip()]
            else:
                self.system_keys = [default_key]

    def get_next_key(self, user_id=None):
        """
        Gets the next available API key using SQLAlchemy.
        Prioritizes the user's own key if available and active.
        """
        self._unfreeze_keys()

        # 1. Prioritize user's own active key
        if user_id:
            user_key = UserApiKey.query.filter_by(
                user_id=user_id, 
                service_name=self.service_name, 
                status='active'
            ).first()

            if user_key:
                self._update_last_used(user_key)
                return user_key.key_value, 'user'

        # 2. Fallback to system's default key (Randomly select one to distribute load)
        if self.system_keys:
            return random.choice(self.system_keys), 'system'
            
        return None, 'system'

    def report_failure(self, api_key, reason=REASON_OTHER):
        """Reports an API call failure and updates the key status."""
        key_entry = UserApiKey.query.filter_by(key_value=api_key).first()
        if not key_entry:
            return

        if reason == REASON_INVALID:
            key_entry.status = 'invalid'
        elif reason == REASON_QUOTA_EXCEEDED:
            key_entry.status = 'quota_exceeded'
            key_entry.cooldown_until = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            key_entry.failure_count = 0
        elif reason == REASON_RATE_LIMITED:
            key_entry.status = 'rate_limited'
            key_entry.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
            key_entry.failure_count = 0
        else: # REASON_OTHER
            key_entry.failure_count = (key_entry.failure_count or 0) + 1
            if key_entry.failure_count >= 3:
                key_entry.status = 'rate_limited'
                key_entry.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
                key_entry.failure_count = 0
        
        db.session.commit()
        
    def report_success(self, api_key):
        """Reports a successful API call, resetting failure count."""
        key_entry = UserApiKey.query.filter_by(key_value=api_key).first()
        if key_entry:
            key_entry.failure_count = 0
            key_entry.last_used_time = datetime.utcnow()
            db.session.commit()

    def _unfreeze_keys(self):
        """Checks and unfreezes any keys that have passed their cooldown time."""
        now = datetime.utcnow()
        UserApiKey.query.filter(
            UserApiKey.status.in_(['quota_exceeded', 'rate_limited']),
            UserApiKey.cooldown_until <= now
        ).update({
            'status': 'active',
            'cooldown_until': None
        }, synchronize_session=False)
        db.session.commit()

    def _update_last_used(self, key_entry):
        """Updates the last used timestamp for a key."""
        key_entry.last_used_time = datetime.utcnow()
        db.session.commit()

# API Rate Limiter (no changes needed, it's independent of the database)
class APIRateLimiter:
    def __init__(self, qps=3):
        self.qps = qps
        self.requests = deque()
        
    async def acquire(self):
        now = time.time()
        
        while self.requests and self.requests[0] < now - 1:
            self.requests.popleft()
            
        if len(self.requests) >= self.qps:
            wait_time = 1 - (now - self.requests[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                
        self.requests.append(time.time())

# Global limiter instances
baidu_limiter = APIRateLimiter(30) 