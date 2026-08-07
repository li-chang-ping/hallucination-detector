# 代码与提交规范

## 通用原则

- 业务规则、状态转换和外部系统边界必须有简洁注释；不为显而易见的赋值或流程添加注释。
- 函数保持单一职责，外部 I/O 与领域逻辑分离；禁止在路由或 Vue 模板中堆叠复杂业务逻辑。
- API、数据库模型和前端类型使用一致命名；时间统一存储为 UTC ISO 8601。
- 密钥只从环境变量读取，日志、数据库、测试夹具和提交内容不得包含真实密钥。

## Python / FastAPI

- Python 3.12，四空格缩进，完整类型标注；使用 Ruff 格式化与检查、mypy 静态检查、pytest 测试。
- 路由只负责协议转换，业务逻辑放在 service，外部服务调用放在 client。
- Pydantic 模型用于所有 API 输入输出；捕获异常时转换为可定位、不可泄密的错误信息。
- SQLAlchemy 事务必须明确，SQLite 与 Chroma 的跨存储变更失败时执行补偿或返回失败。

## Vue / TypeScript

- Vue 3 Composition API 与 `<script setup lang="ts">`；开启 TypeScript strict。
- Pinia 管理跨页面状态，页面组件组织流程，可复用表单和展示逻辑下沉到组件。
- 使用 ESLint、Prettier、vue-tsc 与 Vitest；API 响应必须声明 TypeScript 类型。
- 所有异步操作提供加载、成功、失败反馈；危险删除操作必须二次确认。

## 测试

- 每个功能提交同时包含该模块必要测试。
- 单元测试可替换 Ollama、Chroma、DeepSeek 网络边界，但产品不得提供 mock 检测模式。
- 缺陷修复必须先补充可复现测试，再提交修复。

## Git 提交

- 使用 Conventional Commits：`feat`、`fix`、`test`、`docs`、`refactor`、`chore`。
- 一次提交只包含一个功能模块；功能与缺陷修复不得混合。
- 提交说明优先使用中文，作用域和必要的专有名词可保留英文。
- 推荐格式：`feat(knowledge): 实现 JSON 知识库导入`。
- 提交前必须运行对应模块的 lint、类型检查和测试。
