# World Cup Agent

这是一个用于学习 LangChain Agent 的最小版本项目。

## 已实现的最小闭环

1. CLI 接收问题，例如“生成今天世界杯战报”。
2. LangChain `create_openai_tools_agent` + `AgentExecutor` 创建工具调用 Agent。
3. Agent 可调用这些工具：
   - `get_daily_report`：读取 2026 美加墨世界杯结构化每日赛程、比分和进球数据。
   - `get_match_analysis`：读取单场比赛、双方本届赛事表现和上下文。
   - `get_prediction_context`：读取预测所需的赛程、历史表现和规则上下文。
   - `get_fixtures` / `get_match_result`：兼容旧命令的别名工具。
   - `query_vector_knowledge`：使用本地 FAISS RAG 检索战报、规则和球队分析文档。
   - `search_web`：用 DuckDuckGo 搜索新闻背景。
4. Agent 基于结构化数据和搜索来源输出 Markdown 战报、比赛分析或预测。

日报按北京时间生成：默认不是简单查询数据源当天日期，而是输出“上一比赛日回顾 + 下一比赛日前瞻”。例如北京时间 6 月 17 日中午，会回顾美加墨当地 6 月 16 日比赛，并前瞻当地 6 月 17 日比赛。

## 配置

复制示例配置：

```bash
cp .env.example .env
```

默认使用：

```env
MODEL_NAME=kimi-k2.5
DEEPGATE_API_KEY=EMPTY
```

当 `MODEL_NAME` 是 `kimi-k2.5` 或 `kimi-k2.6` 时，代码会自动使用：

```text
http://deepgate.ximalaya.local/{model}/api/v1
```

如果 DeepGate 需要真实鉴权，请把 `DEEPGATE_API_KEY` 改成真实值。

## 运行

```bash
.venv/bin/python -m app.main "生成今天世界杯战报"
```

学习时建议先看 `app/tools/football_api.py`，理解普通 Python 函数如何通过 `@tool` 变成 Agent 可调用的数据工具。

当前赛事基础数据来自公开数据集 `openfootball/worldcup.json`，适合学习每日战报、基础赛果和进球事件。它不是商业实时数据 API；如果要稳定获取实时技术统计、阵容、伤停、xG 和赔率，后续建议接入 API-Football、Sportmonks 或 TheStatsAPI。

## 本地 RAG

知识库文档放在：

```bash
data/knowledge/
```

当前用 `faiss-cpu` 做向量检索，并用本地轻量 hashing embedding 演示 RAG 流程，不依赖额外 embedding API。适合学习“文档切块 -> 向量化 -> FAISS 相似度搜索 -> Agent 使用检索结果”。后续可以替换成真正的 embedding 模型。

向量会持久化到：

```bash
data/faiss/index.faiss   # FAISS 索引
data/faiss/chunks.json   # chunk 文本和 metadata
data/faiss/meta.json     # 构建时间和知识库 hash
```

首次使用或修改 `data/knowledge/` 后，先构建索引：

```bash
.venv/bin/python -m app.rag.ingest
```

查询时如果检测到知识库变更，也会自动重建索引。

可以测试：

```bash
.venv/bin/python -m app.main "西班牙为什么表现差"
.venv/bin/python -m app.main "世界杯小组赛怎么出线"
```

当前为了兼容系统自带 Python 3.9，项目使用 LangChain 0.2 系列。等你升级到 Python 3.11+ 后，可以再切换到新版 `create_agent` 写法。
