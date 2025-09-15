# CLAUDE.md

本文件为 Claude Code（`claude.ai/code`）在本仓库中工作的指南。

## 开发命令

### 运行应用
```bash
python run.py
```
Flask 应用将以调试模式在 `http://0.0.0.0:5000` 启动。

### 测试
```bash
pytest
```
运行全部测试。测试配置位于 `pytest.ini`，其中 `pythonpath` 已设置为当前目录。

### 数据库管理
- 初始化数据库：`python init_db.py`
- 初始化地点类型：`python init_location_types.py`  
- 设置管理员用户：`python set_admin.py`
- 查看数据库内容：`python view_db.py`
- 数据库迁移：`python migrate_db.py`

### 依赖
安装所需包：
```bash
pip install -r requirements.txt
```

## 架构概览

这是一个基于 Flask 的地理编码 Web 应用，遵循 `ARCHITECTURE.md` 中定义的严格“三层架构”。

### 1. 路由层（`app/routes/`）
- **作用**：处理 HTTP 请求并编排业务流程
- **关键文件**： 
  - `geocoding.py`：遵循瀑布式逻辑的主要地理编码端点
  - `auth.py`：认证相关路由
  - `user.py`：用户管理
  - `main.py`：通用应用路由
  - `payment_bp.py`：支付处理
- **约束**： 
  - 不得包含直接 I/O 操作或外部 API 调用
  - 不得解析第三方 API 的原始响应
  - 复杂逻辑应委托给 services/utils 层

### 2. 服务层（`app/services/`）
- **作用**：外部 API 集成与第三方服务适配
- **关键文件**：
  - `geocoding_apis.py`：高德、百度、天地图等地理编码 API 封装类
  - `llm_service.py`：AI/LLM 集成
  - `poi_search.py`：兴趣点（POI）搜索功能
- **约束**： 
  - 处理所有外部 I/O（HTTP 请求、数据库调用）
  - 将第三方 API 响应标准化为内部格式
  - 不得包含跨服务的业务逻辑

### 3. 工具层（`app/utils/`）
- **作用**：纯计算函数与可复用算法
- **关键文件**：
  - `address_processing.py`：核心置信度计算算法
  - `geo_transforms.py`：坐标系转换
  - `api_managers.py`：API 密钥轮换与限流
- **约束**： 
  - 必须是无状态的纯函数
  - 不得包含任何 I/O 操作
  - 应可独立进行测试

## 关键工作流

### 多源地理编码流程
本应用实现了复杂的瀑布式策略：
1. 路由层接收地址输入
2. 工具层执行地址补全与清洗
3. 服务层按优先级顺序调用地理编码 API（高德 → 天地图 → 百度）
4. 工具层对结果计算置信度分数
5. 路由层选择最佳结果，并可选地进行逆地理编码增强

### 数据库架构
- **用户数据**：`database/user_data.db`（用户、充值订单、API 密钥）
- **地理编码缓存**：`database/geocoding.db`（地点类型、缓存结果）
- **API 密钥**：`database/api_keys.db`（第三方服务密钥）

## 特别事项

### API 密钥管理
应用通过 `utils/api_managers.py` 管理高级的 API 密钥轮换系统。当触发限流或配额耗尽时，将自动进行密钥轮换。

### 上下文日志
通过 `utils/log_context.py` 实现带上下文的信息化日志，并在 Flask 应用初始化时完成配置。

### 静态文件
由于开发期间的文件权限问题，静态文件从根目录 `/static/`（而非 `app/static/`）提供服务。

### 配置
主要配置位于 `app/config.py`，根目录下的 `config.py` 中包含附加常量。

## 文档参考
- `ARCHITECTURE.md`：关于架构原则与各层职责的详细说明  
- `docs/SOP_*.md`：各类地理编码工作流的标准操作流程（SOP）
- `docs/poi_search_documentation.md`：POI 搜索功能文档 