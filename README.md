# AI 增强型电商接口自动化测试框架

**AI-Augmented E-commerce API Automation Testing Framework**

基于 `pytest + requests + Allure + YAML` 的分层接口自动化测试框架，面向本地电商 API，当前覆盖注册、登录模块，并针对服务端限流策略实现了主动请求节流。

> 本项目仅用于本地测试与学习。管理员账号、口令、Token 等敏感信息不进入版本库；日志和 Allure 附件统一脱敏。

---

## 项目简介

- 目前使用的电商后端项目是：

  - Donovan-Nudrak / E_commerce [https://github.com/Donovan-Nudrak/E_commerce](https://github.com/Donovan-Nudrak/E_commerce?utm_source=chatgpt.com)

  - 项目技术栈：

    - 后端：Python + FastAPI

    - 数据库：PostgreSQL

    - 缓存：Redis

    - 部署：Docker Compose

    - 接口文档：Swagger / OpenAPI

  - 本地接口地址：

    - Swagger：[http://localhost:8000/docs](http://localhost:8000/docs?utm_source=chatgpt.com)

    - OpenAPI：[http://localhost:8000/openapi.json](http://localhost:8000/openapi.json?utm_source=chatgpt.com)

本项目从一个最小可运行的登录用例出发，逐步演进为可扩展的接口自动化测试工程：

- 分层清晰：`api`、`data`、`testcases`、`utils` 各司其职
- 数据驱动：YAML 管理输入与预期，测试函数只负责编排和断言
- 多角色隔离：独立 `HttpClient` 实例分别承载游客、管理员、普通用户 Token
- 生命周期管理：session / module / function 三级 fixture 管理账号和清理
- 限流感知：根据服务端实测配额主动等待，避免 429 污染测试结果
- 报告友好：Allure 展示场景标题、请求/响应附件和失败上下文
- 安全默认：密码、Token、Authorization、Cookie 在日志和报告中自动脱敏

---

## 核心特性

### 1. 数据驱动与可读性

- 登录、注册用例均由 YAML 驱动
- 每条用例有 `id`、`title` 和 `expected`，按需声明输入差异和省略字段
- pytest 参数 ID 由 YAML 编号和中文标题组成
- Allure 从 `case["title"]` 取标题，写明场景和预期结果

示例：

```yaml
- id: LOGIN-003
  title: 已注册用户输入错误密码，登录返回 401
  group: standard
  input:
    password: "Wrong!Passw0rd#2026"
  expected:
    status: 401
```

### 2. 账号与数据生命周期

- `test_login_user`：`module` 级，登录模块共用一个真实账号，模块结束清理
- `random_register_data`：`function` 级，每个注册用例生成唯一邮箱/密码
- `register_cleanup`：`function` 级，登记成功创建的账号并在 teardown 清理
- 清理优先调用 `DELETE /api/v1/users/profile`，失败后尝试 `POST /api/v1/auth/logout`
- 删除失败时尝试登出并记录待清理账号。清理前登录或降级登出失败时，pytest 会报告 teardown 错误

### 3. 多角色客户端

```python
guest_client = HttpClient(base_url, rate_limiter=rate_limiter)
admin_client = HttpClient(base_url, token=admin_token, rate_limiter=rate_limiter)
user_client = HttpClient(base_url, token=user_token, rate_limiter=rate_limiter)
```

每个客户端拥有独立的 `requests.Session` 和鉴权信息。同一次 pytest 会话内，角色客户端、临时清理客户端和并发客户端共享一个 `rate_limiter`。

### 4. 主动限流保护

服务端实测配额：

| 接口 | 配额 |
|---|---|
| `POST /api/v1/auth/register` | 5 次/分钟 |
| `POST /api/v1/auth/login` | 10 次/分钟 |
| `GET /api/v1/auth/me` | 未观察到限制 |

`RateLimitGuard` 在请求发出前按滑动窗口主动等待：

```text
RATE_LIMIT_WAIT key=register limit=5/60.0s wait=...
```

避免全量用例在数秒内触发 `429 Rate limit exceeded`。

### 5. Allure 报告

- `@allure.feature` / `@allure.story` / `@allure.title`
- 动态标题：`allure.dynamic.title(case["title"])`
- HTTP 请求和响应以折叠附件展示
- 请求体、密码、Token、Cookie 自动脱敏
- 控制台日志输出到 `stdout`，同时写入滚动日志文件

---

## 技术栈

| 类别 | 选型 |
|---|---|
| 语言 | Python 3.9+ |
| 测试框架 | pytest |
| HTTP | requests |
| 报告 | Allure |
| 数据 | YAML / JSON |
| 配置 | YAML + 环境变量覆盖 |
| AI Agent | 辅助测试设计、用例生成、框架重构与评审，不是运行时依赖 |

---

## 分层架构

```text
testcases  —— 业务编排、参数化、断言、Allure 标记
    │
    ├── api  —— 接口发送：HttpClient、LoginAPI、RegisterAPI、AccountAPI
    │
    ├── data —— 配置、YAML 测试数据
    │
    └── utils —— 配置加载、路径、日志、脱敏、Token、限流、数据加载
```

调用链：

```text
YAML → load_cases → @pytest.mark.parametrize
  → 测试函数用 fixture 数据构造请求
  → LoginAPI / RegisterAPI / AccountAPI
  → HttpClient → 共享 RateLimitGuard → requests.Session
  → 原始 Response 返回测试函数断言
  → Allure 记录脱敏请求和响应，日志写入 framework.log
```

职责边界：

- `api` 只发请求，不做断言
- `testcases` 只做编排和断言
- `utils` 只提供配置、日志、路径、脱敏、限流等基础能力
- `data` 不包含代码

---

## 目录结构

```text
auto_test_ai/
├── api/
│   ├── __init__.py
│   ├── http_client.py          # 通用 HTTP 客户端、Token 注入、Allure 附件
│   ├── login_api.py            # 登录接口封装
│   ├── register_api.py         # 注册接口封装
│   └── account_api.py          # /me、删除账号、登出
├── data/
│   ├── config/
│   │   └── config.yaml         # 本地配置
│   └── testdata/
│       ├── login.yaml          # 登录参数化数据
│       └── register.yaml       # 注册参数化数据
├── docs/
│   └── 注册登录模块测试点与测试用例.md
├── logs/
│   └── .gitkeep                # framework.log 运行时生成，不提交
├── reports/
│   ├── allure-results/         # Allure 原始结果，不提交
│   └── allure-report/          # Allure HTML 报告，不提交
├── testcases/
│   ├── __init__.py
│   ├── conftest.py             # 账号 fixture、清理、API fixture
│   ├── test_login.py           # 登录参数化用例
│   └── test_register.py        # 注册参数化用例
├── utils/
│   ├── __init__.py
│   ├── config.py               # 配置加载与环境变量覆盖
│   ├── data_loader.py          # YAML 用例读取与分组
│   ├── logger.py               # stdout + 文件日志
│   ├── paths.py                # 项目路径
│   ├── rate_limit.py           # 主动限流守卫
│   ├── redaction.py            # 敏感信息脱敏
│   └── token.py                # Token 提取
├── conftest.py                 # 配置、共享限流器、游客与管理员客户端
├── pytest.ini
├── requirements.txt
├── .gitignore
└── README.md
```

> `data/config/config.yaml` 包含本地管理员凭据，已在 `.gitignore` 中排除。首次克隆后请按下方模板创建。

---

## 快速开始

### 环境要求

- Python 3.9+
- conda 环境：`cekai`
- Allure Commandline 2.x
- 本地 API：`http://localhost:8000`

### 安装依赖

```powershell
cd D:\deepseekwork\auto_test_ai
conda activate cekai
python -m pip install -r requirements.txt
```

### 创建本地配置

在 `data/config/` 下创建 `config.yaml`：

```yaml
default:
  base_url: "http://localhost:8000"
  timeout: 10
  admin:
    email: "admin@ecommerce.com"
    password: "local-admin-password"
  rate_limit:
    enabled: true
    window_seconds: 60
    register_per_minute: 5
    login_per_minute: 10
    me_per_minute: 0
    buffer_seconds: 0.5

local:
  base_url: "http://localhost:8000"
```

推荐通过环境变量传入管理员口令，不把真实口令写入任何准备提交的文件：

```powershell
$env:ADMIN_PASSWORD = "local-admin-password"
```

### 运行测试

```powershell
# 全量 66 条参数化用例（启用主动限流，执行时间会变长）
python -m pytest --clean-alluredir -q

# 仅登录模块
python -m pytest testcases/test_login.py --clean-alluredir -q

# 仅注册模块
python -m pytest testcases/test_register.py --clean-alluredir -q
```

### 生成并打开 Allure 报告

```powershell
allure generate reports/allure-results -o reports/allure-report --clean
allure open reports/allure-report
```

`pytest.ini` 已配置：

```ini
addopts = -ra --strict-markers --tb=short --alluredir=reports/allure-results --allure-no-capture
```

因此运行 pytest 时无需再次指定 `--alluredir`。

---

## 配置项

| 环境变量 | 用途 | 默认值 |
|---|---|---|
| `APP_ENV` | 选择配置环境段 | `local` |
| `API_BASE_URL` | 覆盖 `base_url` | `http://localhost:8000` |
| `API_TIMEOUT` | 请求超时秒数 | `10` |
| `ADMIN_EMAIL` | 管理员邮箱 | `admin@ecommerce.com` |
| `ADMIN_PASSWORD` | 管理员口令，推荐必填 | 本地配置 |
| `RATE_LIMIT_ENABLED` | 是否启用主动限流 | `true` |
| `RATE_LIMIT_WINDOW_SECONDS` | 限流窗口 | `60` |
| `RATE_LIMIT_REGISTER_PER_MINUTE` | 注册配额 | `5` |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | 登录配额 | `10` |
| `RATE_LIMIT_ME_PER_MINUTE` | `/me` 配额，0 表示不等待 | `0` |
| `RATE_LIMIT_BUFFER_SECONDS` | 窗口额外缓冲 | `0.5` |

示例：

```powershell
$env:APP_ENV = "local"
$env:API_BASE_URL = "http://127.0.0.1:8000"
$env:ADMIN_PASSWORD = "local-admin-password"
python -m pytest testcases/test_login.py -q
```

---

## 数据驱动设计

### YAML 结构

```yaml
module: login
cases:
  - id: LOGIN-005
    title: 登录缺少 email 字段，返回 422 并定位到 email
    group: standard
    delete_fields:
      - email
    expected:
      status: 422
      error_field: email
```

约定：

- `input` 覆盖默认请求字段。测试文件在发送请求前生成唯一邮箱和超长邮箱
- `delete_fields`：明确删除哪些字段，替代容易混淆的 `remove`
- `expected.status`：预期 HTTP 状态码
- `expected.error_field`：422 时校验 `detail[].loc`
- `expected.forbidden_fields`：成功响应中禁止出现的敏感字段
- `title`：Allure 标题和 pytest 参数 ID 的来源

### 参数化机制

测试文件直接声明 YAML 分组，测试函数收到普通字典。管理员凭据在运行时读取配置。

```python
@pytest.mark.parametrize(
    "case",
    load_cases("login.yaml", group="standard"),
    ids=lambda c: f"{c['id']}_{c['title']}",
)
```

---

## 限流策略

### 服务端配额

- 注册：5 次/分钟
- 登录：10 次/分钟
- `/me`：未观察到限制

### 客户端策略

- 使用 `utils/rate_limit.py` 的滑动窗口
- 注册有效请求自动间隔等待
- 登录有效请求自动间隔等待
- 422 参数校验请求不进入等待，依据实测行为
- 清理登录与注册后登录验证同样纳入登录配额
- 所有等待写入 `logs/framework.log`

### 注意

- 主动限流会让全量测试耗时增加，这是预期行为
- 当前未实现 429 自动重试；如果后端策略变化，可继续增加 429 退避策略
- 若需要全部请求都等待，可将测试中的 `rate_limit=False` 去掉

---

## Allure 报告

报告内容包括：

- 明确的用例标题，例如：
  - `普通用户用正确凭据登录成功，且可查询本人资料`
  - `已注册用户输入错误密码，登录返回 401`
  - `同一邮箱再次注册返回 409，原账号仍可登录`
- feature / story / severity 分层
- 请求与响应 JSON 附件
- 失败时的具体场景名和状态码
- 敏感字段脱敏后的请求上下文

---

## 测试覆盖

当前共 **66 条参数化测试**：

| 模块 | 数量 | 覆盖 |
|---|---:|---|
| 登录 | 31 | 正向、密码错误、不存在用户、字段缺失、类型错误、非法邮箱、额外 `role`、SQLi/XSS、`/me` 鉴权 |
| 注册 | 35 | 正向、可选 `phone`、合法/非法邮箱、必填、空串、类型错误、超长、弱密码、重复/并发、角色提权、XSS/SQLi |

账号生命周期：

- 登录模块：模块级账号，模块结束清理
- 注册模块：每个用例唯一数据，成功后登记，函数结束清理
- 清理失败会记录待清理账号，便于人工补偿

---

## 安全说明

- `data/config/config.yaml` 不提交到 Git
- 管理员口令建议通过 `ADMIN_PASSWORD` 环境变量注入
- 日志和 Allure 附件中的 `password`、`token`、`Authorization`、`Cookie` 会替换为 `***`
- 本项目仅用于本地测试环境
- 不要将真实生产凭据、Token 或用户数据写入测试数据

---

## Roadmap

- [ ] Dockerfile / docker-compose，隔离本地 API 与测试执行环境
- [ ] 增加 429 `Retry-After` 解析与退避重试
- [ ] 登录/注册之外的模块扩展
- [ ] AI Agent 辅助生成测试数据与失败分析
- [ ] CI 集成与 Allure 报告归档
