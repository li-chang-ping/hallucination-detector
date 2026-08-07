# 项目协作规则

本文件适用于整个仓库。进入本项目工作的自动化 Agent 必须先阅读并遵守本文件；子目录若存在更具体的 `AGENTS.md`，则同时遵守其补充规则。

## 项目简介

本项目是本地运行的智能客服回复幻觉检测系统，包含三个业务模块：检测任务、知识库管理和幻觉定义管理。知识库文本由 Ollama 生成向量并存入 Chroma，检测任务检索证据后调用 DeepSeek 进行幻觉判断，业务数据、任务进度、证据快照和人工评测结果保存在 SQLite。

系统为本地单用户模式，不包含登录、权限、多租户和产品级 mock 检测能力。

## 项目结构

```text
.
├─ backend/
│  ├─ .venv/                 # 本地 Python venv，不提交
│  ├─ alembic/               # SQLite 数据库迁移
│  ├─ app/
│  │  ├─ routers/            # FastAPI /api/v1 路由
│  │  ├─ schemas/            # Pydantic 请求、响应和模型输出校验
│  │  ├─ services/           # 检测、检索、评测和业务事务
│  │  ├─ config.py           # 环境变量配置
│  │  ├─ db.py               # SQLAlchemy 引擎与会话
│  │  ├─ main.py             # FastAPI 应用入口
│  │  └─ models.py           # SQLite ORM 模型
│  ├─ tests/                 # 后端单元及接口测试
│  └─ pyproject.toml         # Python 依赖与质量工具配置
├─ frontend/
│  ├─ src/
│  │  ├─ views/              # 检测任务、知识库、幻觉定义页面
│  │  ├─ api.ts              # Axios 客户端与统一错误转换
│  │  ├─ router.ts           # Vue Router 路由
│  │  └─ types.ts            # 前端领域类型
│  ├─ tests/                 # Vitest 组件与工具测试
│  ├─ package.json           # 前端依赖和脚本
│  └─ vite.config.ts         # Vite 配置及 API 代理
├─ scripts/                  # 环境准备、服务启动、质量检查脚本
├─ data/
│  ├─ app.db                 # 本地 SQLite 数据，不提交
│  └─ chroma/                # Chroma 持久化数据，不提交
├─ docs/CODE_STANDARDS.md    # 前后端代码规范
├─ .env.example              # 配置示例
└─ AGENTS.md                 # 本项目协作与运行说明
```

## Python 环境

- 必须使用 `C:\ProgramData\anaconda3\python.exe` 创建 Python venv，不创建 Conda 命名环境。
- 虚拟环境固定放在 `backend/.venv`，不得放在仓库根目录或提交到 Git。
- 后端命令优先使用 `backend/.venv/Scripts/python.exe` 执行。
- Python 依赖变更必须同步维护可复现的依赖配置和安装脚本。

首次准备后端环境：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

该脚本使用 `C:\ProgramData\anaconda3\python.exe -m venv backend/.venv` 创建环境，并以 editable 模式安装 `backend[dev]`。不得改成 Conda 命名环境。

## 技术与运行约束

- 前端使用 Vue 3、Element Plus、TypeScript 和 Vite。
- 后端使用 Python、FastAPI、SQLite 和独立运行的 Chroma 服务。
- Chroma 数据保存在项目 `data/chroma/`，服务端口为 `8001`；FastAPI 使用 `8000`；Vite 使用 `5173`。
- 嵌入模型通过本地 Ollama 服务调用，正式知识库使用 `qwen3-embedding:0.6b`；索引和查询必须使用同一模型。
- 幻觉判断使用 DeepSeek API，不提供产品级 mock 检测模式。密钥只能从环境变量或被 Git 忽略的 `.env` 读取。
- 修改或新增第三方组件用法前，先查阅对应官方文档；无法确认时再使用可靠的一手资料。

## 本地配置

首次运行时复制配置模板：

```powershell
Copy-Item .env.example .env
```

必须由用户在本地 `.env` 中填写 `DEEPSEEK_API_KEY`。常用可覆盖项包括 DeepSeek 模型、Ollama 地址及嵌入模型、Chroma 地址、SQLite 地址和前端允许来源；以 `.env.example` 和 `backend/app/config.py` 为准。

不得读取、打印、提交或要求用户在聊天中发送真实 API Key。

## 服务启动与停止

启动前检查 Ollama 并准备嵌入模型：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-ollama.ps1
```

分别在三个终端启动项目服务：

```powershell
# Chroma，端口 8001，数据保存到 data/chroma/
powershell -ExecutionPolicy Bypass -File scripts/start-chroma.ps1

# 执行 Alembic 迁移并启动 FastAPI，端口 8000
powershell -ExecutionPolicy Bypass -File scripts/start-backend.ps1

# 启动 Vite，端口 5173
powershell -ExecutionPolicy Bypass -File scripts/start-frontend.ps1
```

Ollama 由本机独立运行，默认地址为 `http://127.0.0.1:11434`。前端地址为 `http://127.0.0.1:5173`，FastAPI 文档为 `http://127.0.0.1:8000/docs`，健康检查为 `http://127.0.0.1:8000/api/v1/health`。

停止服务时终止对应前台进程。不得通过递归删除 `data/` 的方式重置服务；如确需清理业务或向量数据，必须先确认具体目标和影响。

## 构建与测试

提交前从仓库根目录执行完整质量检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/quality.ps1
```

该脚本按失败即退出的方式执行：

- 后端：Ruff check、Ruff format check、mypy、pytest。
- 前端：ESLint、Prettier check、Vitest、vue-tsc 和 Vite 生产构建。

需要单独执行时：

```powershell
# 后端
Push-Location backend
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m ruff format --check app tests
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest tests
Pop-Location

# 前端
Push-Location frontend
pnpm lint
pnpm format:check
pnpm test
pnpm build
Pop-Location
```

后端没有独立编译产物，Ruff、mypy 和 pytest 是主要验收项。前端正式构建产物位于 `frontend/dist/`，该目录不提交。

## 数据格式与导入规则

知识库导入 JSON：

```json
{"name":"售后知识库","description":"正式政策","entries":[{"id":"return-01","title":"退货政策","content":"普通商品支持7天无理由退货","metadata":{"source":"policy"}}]}
```

检测任务 JSON：

```json
[{"id":"h01","user_question":"支持30天无理由退货吗？","system_reply":"全品类支持30天无理由退货。"}]
```

人工标注 JSON：

```json
[{"id":"h01","is_hallucination":true,"hallucination_type":"政策编造","detail":"回复与退货政策矛盾"}]
```

- 知识条目 ID 在同一知识库内必须唯一。
- 回复 ID 在同一任务内必须唯一。
- 人工标注 ID 必须与任务条目完整且逐一对应，不允许只上传子集或包含未知 ID。
- 检测输入中即使存在 `knowledge_base` 字段也必须忽略，正式证据只能来自 Chroma 检索。

本地附件可通过以下命令生成演示导入文件，但附件和生成的本地数据不得提交：

```powershell
backend\.venv\Scripts\python.exe scripts\prepare_demo.py "0110附件\task4_replies.json"
```

## API 模块

- `/api/v1/tasks`：任务创建、列表、详情、暂停、继续和取消。
- `/api/v1/knowledge-bases`：知识库与条目导入、查询、编辑和删除。
- `/api/v1/categories`：幻觉分类新增、编辑、启停、归档、历史和回退。
- `/api/v1/evaluations`：人工标注评测、误判分析和分类优化建议。

修改 API 时必须同步检查相应 Pydantic schema、前端类型、调用页面和测试。SQLite 与 Chroma 组合写操作必须保证失败可见，并尽可能在外部向量操作失败时回滚数据库事务。

## 代码质量

- 实现功能时必须包含必要的测试；修复缺陷时先补充能够复现问题的测试。
- Python 提交前运行 Ruff、mypy 和 pytest。
- 前端提交前运行 ESLint、Prettier check、vue-tsc、Vitest，并按风险执行生产构建。
- 注释用于说明业务规则、状态转换和非直观实现，不重复代码表面含义。
- 不得为了通过检查而削弱类型、跳过测试或隐藏真实错误。

## Git 提交

- 使用 Conventional Commits：`feat`、`fix`、`test`、`docs`、`refactor`、`chore`。
- 提交 message 优先使用中文；作用域、命令、库名和必要的专有名词可以保留英文。
- 一次提交只包含一个功能模块及其对应测试，不能混入无关修改。
- 功能实现与 bug 修复必须使用不同提交，不得混合。
- 提交前检查暂存区，只提交当前任务明确涉及的文件，并保留用户已有的未提交修改。
- 未经用户明确要求，不重写已经推送的公共历史，不执行破坏性 Git 命令。

## 禁止提交的内容

- `提示词.md`。
- `0110附件/` 及其全部内容。
- `.env`、API Key、令牌及其他真实密钥。
- `backend/.venv/`、本地 SQLite 数据、Chroma 数据、日志、缓存、依赖目录和构建产物。
- 运行截图若只用于本地验收，应保存在已忽略目录；需要作为正式交付物提交时，必须先取得用户确认。

## 工作方式

- 修改前检查工作区状态，避免覆盖或提交用户的现有改动。
- 优先完成可验证的端到端结果；启动服务后检查真实健康接口，而不只检查进程是否存在。
- 检测指标必须来自真实运行结果和人工标注比对，不得预设或伪造。
- 需要 `DEEPSEEK_API_KEY` 时通知用户，由用户在本地 `.env` 中填写；不得要求用户把密钥发送到聊天中。
