# GroundLens 智能客服幻觉检测平台

GroundLens 是面向智能客服回复的本地批量审计系统。它使用 Ollama 生成中文知识向量、Chroma 检索证据、DeepSeek 判断回复是否存在幻觉，并可上传人工标注计算漏检、误报及具体不一致 case。

## 核心能力

- 检测任务：JSON 批量导入，支持查看、暂停、继续、取消和进程重启后恢复。
- 知识库：JSON 导入及条目增改删，向量由 `qwen3-embedding:0.6b` 生成并显式写入 Chroma。
- 幻觉定义：六类默认体系，可维护描述、严重度、判定指引和启用状态；所有变更保留版本历史并支持回退。
- 人工评测：输出 TP/TN/FP/FN、Precision、Recall、Accuracy，以及漏检、误报和分类不一致 ID。
- 误判优化：对漏检和误报生成原因分析与定义优化建议，用户可选择采纳或忽略；采纳后直接更新定义并保留回退版本。

## 幻觉分类体系

| 分类 | 默认严重度 | 判定范围 |
|---|---|---|
| 政策与优惠错误 | high | 退换货、发票、优惠等政策被编造或错误描述 |
| 产品参数错误 | high | 材质、规格、接口、功能或保修与证据冲突或无依据 |
| 事实信息编造 | high | 地址、门店、品牌关系、物流状态等事实被虚构 |
| 能力越界 | high | 假装完成查询、修改、发券或工单操作 |
| 安全误导 | critical | 可能造成健康、人身或重大财产风险的错误建议 |
| 关键信息遗漏 | medium | 遗漏足以让用户形成相反或明显错误结论的信息 |

当前采用单标签判定：一条幻觉回复只选择一个最主要分类。知识库未提供的信息不能被客服回复强肯定；“已查询、已修改”等执行声明必须有能力证据支持。

## 检测方法

1. 将“用户问题 + 系统回复”发送到本地 Ollama `/api/embed`。
2. 使用同一嵌入模型从选定 Chroma 集合检索前 5 条相关知识。
3. 将证据、回复和启用分类快照发送到 DeepSeek JSON Output 接口。
4. 用 Pydantic 校验单标签分类、严重度、置信度和理由；失败最多重试 3 次。
5. 每条完成后写入 SQLite 检查点，暂停或异常重启不会丢失已有结果。

检测输入中的 `knowledge_base` 字段会被忽略，证据只从 Chroma 获取。这样可以验证真实 RAG 链路，而不是把标准答案直接拼入提示词。

## 本地环境

要求：Windows 上已安装 Conda、Ollama、Node.js 20+ 和 pnpm 11+。

```powershell
# 1. 使用 Conda 自带 Python 在 backend 下创建 venv 并安装依赖
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

# 2. 复制配置并填写 DEEPSEEK_API_KEY
Copy-Item .env.example .env

# 3. 检查/下载 Ollama 中文嵌入模型
powershell -ExecutionPolicy Bypass -File scripts/check-ollama.ps1
```

分别打开三个终端：

```powershell
powershell -File scripts/start-chroma.ps1
powershell -File scripts/start-backend.ps1
powershell -File scripts/start-frontend.ps1
```

访问前端 `http://127.0.0.1:5173`，API 文档位于 `http://127.0.0.1:8000/docs`。

## JSON 格式

知识库：

```json
{"name":"售后知识库","description":"正式政策","entries":[{"id":"return-01","title":"退货政策","content":"普通商品支持7天无理由退货","metadata":{"source":"policy"}}]}
```

检测回复：

```json
[{"id":"h01","user_question":"支持30天无理由退货吗？","system_reply":"全品类支持30天无理由退货。"}]
```

人工标注：

```json
[{"id":"h01","is_hallucination":true,"hallucination_type":"政策编造","detail":"回复与实际退货政策矛盾"}]
```

本地附件不会提交仓库。可在本机生成演示导入文件：

```powershell
backend\.venv\Scripts\python.exe scripts\prepare_demo.py "0110附件\task4_replies.json"
```

## 测试与代码质量

```powershell
powershell -File scripts/quality.ps1
```

后端使用 Ruff、mypy、pytest；前端使用 ESLint、Prettier、vue-tsc、Vitest 和 Vite 生产构建。常规测试只替换外部网络边界，产品中没有 mock 检测模式。

## 附件实测结果

最终结果必须来自真实 DeepSeek API。完成 API Key 配置和 20 条检测后，将在此记录混淆矩阵、Precision、Recall、Accuracy、漏检和误报 ID，并附上真实页面截图。

容易误判的边界包括：知识库只写“未标注”而非明确否定、回复部分正确部分错误、能力限制被写在否定式说明中，以及关键信息遗漏。这些 case 同时依赖检索召回和模型对“无依据肯定”“部分矛盾”的理解。

## AI 工具使用情况

- Codex：用于需求分析、架构设计、代码实现、测试和文档辅助，所有产物经过自动化检查。
- DeepSeek API：唯一的实际幻觉判定模型，默认 `deepseek-v4-flash`。
- Ollama：仅运行 `qwen3-embedding:0.6b` 生成本地中文向量，不参与最终幻觉判断。

真实 API Key、SQLite/Chroma 数据、本地附件、模型文件、截图原文件和构建缓存均不提交仓库。
