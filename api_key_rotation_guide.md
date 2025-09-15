# API密钥轮换系统说明文档

## 1. 系统概述

本系统实现了一个灵活的API密钥管理和轮换机制，主要用于管理高德地图等第三方服务的API密钥。系统支持多密钥轮换使用，并实现了请求频率限制（Rate Limiting）。

## 2. 核心组件

### 2.1 APIKeyManager 类
负责管理和轮换API密钥：
- 从数据库加载可用的API密钥
- 在没有数据库记录时使用环境变量中的默认密钥
- 提供密钥轮换功能

### 2.2 APIRateLimiter 类
控制API请求频率：
- 默认限制为每秒3次请求（高德地图限制）
- 使用时间窗口算法实现精确的请求频率控制
- 支持异步等待机制

## 3. 数据库设计

### 3.1 数据库表结构
```sql
CREATE TABLE IF NOT EXISTS api_keys (
    service TEXT,         -- 服务名称（如 'amap'）
    key TEXT,            -- API密钥
    qps INTEGER,         -- 每秒请求限制
    daily_limit INTEGER, -- 每日请求限制
    is_active INTEGER    -- 是否激活（1=激活，0=停用）
);
```

### 3.2 添加新密钥示例
```sql
-- 添加新的API密钥
INSERT INTO api_keys (service, key, qps, daily_limit, is_active) 
VALUES ('amap', 'your_new_key', 3, 300000, 1);

-- 停用特定密钥
UPDATE api_keys SET is_active = 0 WHERE key = 'old_key';
```

## 4. 使用说明

### 4.1 添加新的API密钥
1. 确保 `api_keys.db` 数据库文件存在
2. 使用 SQLite 工具或执行 SQL 语句添加新密钥
3. 系统会自动加载新添加的密钥

### 4.2 密钥轮换机制
- 系统自动在所有激活的密钥间轮换
- 当遇到配额限制时，自动切换到下一个可用密钥
- 如果所有密钥都达到限制，会等待适当时间后重试

### 4.3 错误处理
- 数据库连接失败时使用环境变量中的默认密钥
- API请求失败时自动重试并切换密钥
- 详细的日志记录帮助追踪问题

## 5. 监控和维护

### 5.1 建议的维护任务
- 定期检查密钥的使用情况
- 监控API请求的成功率
- 在密钥接近配额限制时添加新密钥

### 5.2 常见问题处理
1. 配额超限：
   - 检查 API 调用日志
   - 确认是否需要添加新密钥
   - 考虑调整请求频率限制

2. 数据库问题：
   - 检查数据库连接
   - 验证表结构完整性
   - 确保密钥记录正确

## 6. 代码示例

### 6.1 使用 APIKeyManager
```python
# 创建密钥管理器实例
amap_key_manager = APIKeyManager('amap', AMAP_KEY)

# 获取下一个可用密钥
next_key = amap_key_manager.get_next_key()
```

### 6.2 使用 APIRateLimiter
```python
# 创建限流器实例
amap_limiter = APIRateLimiter(3)  # 3 QPS

# 在API调用前等待许可
await amap_limiter.acquire()
```

## 7. 注意事项

1. 密钥安全：
   - 不要在代码中硬编码API密钥
   - 定期轮换密钥
   - 及时停用不再使用的密钥

2. 性能考虑：
   - 合理设置QPS限制
   - 监控API响应时间
   - 适时调整重试策略

3. 维护建议：
   - 定期备份数据库
   - 记录密钥使用情况
   - 建立密钥更新流程

## 8. 未来优化方向

1. 添加密钥使用统计
2. 实现自动负载均衡
3. 添加密钥健康检查
4. 实现自动告警机制
5. 优化密钥轮换算法

## 9. 联系方式

如有问题，请联系系统管理员或查看相关文档。 