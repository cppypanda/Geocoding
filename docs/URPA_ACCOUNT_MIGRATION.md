# GeoCo 接入 URPA 统一账户

## 当前策略

- 新用户优先使用 URPA 手机号登录、注册和找回密码。
- 原邮箱验证码、邮箱/用户名密码登录继续保留，不进行强制切换。
- 原用户登录后会看到可延后七天的绑定提示，也可在“设置 → 个人资料”中绑定。
- 绑定只为当前 GeoCo 用户增加一个 URPA 外部身份，不迁移主键，因此积分、任务、充值单、API Key 和日志归属保持不变。
- GeoCo 不保存 URPA 密码、验证码、访问令牌或刷新令牌。服务端验证成功后只保存 `urpa_user_id`、已验证手机号和绑定时间。
- 如果同一 URPA 身份已经关联另一个 GeoCo 用户，接口返回 `409`，不得静默合并账户。需要在后续账户合并工具中显式预览和确认。

## 与 QPA 的协议兼容

GeoCo 与 QPA 使用相同的 URPA 公共认证接口：

- `POST /api/auth/status`
- `POST /api/auth/send-code`
- `POST /api/auth/password-login`
- `POST /api/auth/register`
- `POST /api/auth/reset-password`

请求使用 `clientProduct: "geoco"` 和 `X-URPA-Product: geoco` 标识来源。当前 URPA 版本会把未知产品安全归入 URPA 主产品，但身份 ID 与 QPA 使用的身份 ID 完全一致；URPA 后续增加 GeoCo/Luwu 产品维度时无需修改本地用户映射。

## 配置

- `URPA_BASE_URL`：默认 `https://urpa.luwug.top`
- `URPA_AUTH_TIMEOUT_SECONDS`：默认 `12`

生产环境必须使用 HTTPS。不要在日志、数据库或错误中心记录请求中的密码、验证码及 URPA 返回的令牌。

## 数据库迁移

迁移 `9c4e1b7a2d05` 为 `users` 增加：

- `phone`：唯一、可空；
- `urpa_user_id`：唯一、可空；
- `urpa_linked_at`；
- `account_origin`：`email`、`urpa` 或 `deleted`。

历史用户自动保留为 `account_origin=email`，无需批量改写。新 URPA 用户使用不可投递的内部占位邮箱满足旧表兼容要求，任何面向用户的接口都不会展示该占位地址。
