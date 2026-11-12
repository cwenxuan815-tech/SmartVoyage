# SmartVoyage：基于 A2A + MCP 的旅行智能助手

[![Python](https://img.shields.io/badge/Python-3.12.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116.1-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3.26-1C3C3C)](https://python.langchain.com/)
[![MCP](https://img.shields.io/badge/MCP-1.18.0-6E4AFF)](https://modelcontextprotocol.io/)
[![A2A](https://img.shields.io/badge/A2A-python--a2a%200.5.4-2F6FED)](https://github.com/themanojdesai/python-a2a)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)

这是一个面向旅行咨询场景的多智能体系统：把「查天气、查火车票/机票/演出票、租车、买保险、挑旅游团、找景点」这类混合诉求，拆给 3 个 A2A 子代理，再由 3 个 MCP 工具服务落到 MySQL 业务表。整套系统由 7 个独立进程组成，覆盖意图识别、任务规划、并行执行、ReAct 串行回退、多轮记忆、追问状态机、CLI 与 Web 双入口。

> 项目采用代码、数据与密钥分离的交付方式。数据库凭据、大模型 Key、和风天气 Key 全部通过环境变量或 `.env` 注入（`.env` 已在 `.gitignore` 中），仓库内只保留代码、建表脚本、模拟数据与前端页面。

课程背景与实现说明见 [`项目参考资料/笔记/day04/D4_项目实现.md`](项目参考资料/笔记/day04/D4_项目实现.md)，协议与架构部分见 [`项目参考资料/笔记/day03/D3_A2A协议_架构_实现.md`](项目参考资料/笔记/day03/D3_A2A协议_架构_实现.md)。

## 导航

- [项目解决的问题](#解决的问题)
- [快速了解](#快速了解)
- [系统架构](#系统架构)
- [核心能力](#核心能力)
- [数据链路](#数据链路)
- [智能体体系与技术选型](#智能体体系与技术选型)
- [编排链路与追问状态机](#编排链路与追问状态机)
- [服务接口](#服务接口)
- [项目结构与关键文件](#项目结构与关键文件)
- [环境准备与运行方式](#环境准备与运行方式)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [评估与验收口径](#评估与验收口径)
- [测试与工程质量](#测试与工程质量)
- [部署与资产管理](#部署与资产管理)
- [项目交付成果](#项目交付成果)
- [许可证](#许可证)

## 解决的问题

- 旅行咨询天然是「多意图混合」问题：一句话里同时包含天气、机票、租车、保险，串行执行会让响应时间随意图数量线性增长；
- 工具能力与对话逻辑容易耦合：SQL、Prompt、HTTP 入口写在同一脚本里，工具无法被 CLI、Web、其他 Agent 复用；
- Agent 之间缺少可发现的能力描述：没有 AgentCard 就无法表达「谁会做什么、参数是什么」，也无法做路由；
- 参考资料 D4 明确点名的追问判定缺陷：仅凭「请提供 / 请确认」两个词就判定 `INPUT_REQUIRED`，会把「为您找到 G942，商务座 808.51 元，请确认后预订」这类**已含数据**的结果误判为追问，导致结论被降级成一句追问；
- 多轮对话缺少可持久化记忆：追问后补充的城市/日期、用户偏好（二等座、经济型）在进程重启后丢失；
- 演示环境经常没有 MySQL、没有大模型 Key，系统直接起不来；
- 密钥、连接串、第三方 API Key 容易被硬编码，随代码进入提交历史。

## 快速了解

| 业务需求或工程问题 | 解决方案 | 形成的交付能力 |
|---|---|---|
| 一句话里问多件事 | 意图识别输出多意图 + 子查询切分 | 单轮多意图，城市/日期不串味 |
| 子任务之间有依赖 | Planning 判定依赖 → 串行 ReAct | 有依赖走 ReAct，无依赖走并行 |
| 首字延迟高 | 启发式路由 + `asyncio.gather` | 独立意图并行执行 |
| 工具要被多方复用 | 3 个 MCP Server，13 个工具 | CLI / Web / 子代理共用同一套工具 |
| Agent 需要互相发现 | A2A AgentCard + Task 状态机 | 3 个子代理，1/6/6 个技能 |
| 追问与结果混淆 | `[NEED_INPUT]` 标记 + 三条件兜底判定 | 状态机可区分 completed / input-required / failed |
| 多轮上下文丢失 | 短期对话 + 偏好 + 任务上下文 + 实体历史，落 MySQL | 追问 → 补槽位 → 换座位类型全链路可用 |
| 无 MySQL / 无 Key 演示 | SQLite 自动降级 + 规则式离线路由 | 离线也能跑通 A2A→MCP→DB |
| 7 个进程手工起太慢 | `scripts/start_all.py` 按依赖顺序拉起 | 一条命令启动，端口占用自动跳过 |
| 部署到容器 | 单镜像 + 不同启动命令 | 8 个容器的 compose 编排 |

项目的核心价值不是「接一个大模型回答旅行问题」，而是把旅行咨询整理成可分层演进的工程系统：**编排层只懂 A2A，子代理只懂 MCP，工具层只懂 SQL**，任一层替换不影响其他层。

## 系统架构

```text
客户端
  ├── CLI      python -m SmartVoyage.main                （进程内调用 ChatService）
  └── Web      FastAPI :8080 + static/index.html          （REST + SSE）

        ▼
编排层 ChatService（运行在 CLI / API 进程内）
  记忆(短期/偏好/任务/实体) → 意图识别 → 启发式路由 → Planning / 并行 / ReAct → 汇总 → 持久化

        │  A2A（python-a2a，AgentCard 暴露在 /agent.json，任务走 Task 状态机）
        ├──────────────────┬──────────────────┐
        ▼                  ▼                  ▼
WeatherQueryAssistant  TicketAssistant    TripAssistant
      :5005                :5006                :5007
        │  MCP（mcp.FastMCP，streamable-http，/mcp）
        ├──────────────────┬──────────────────┐
        ▼                  ▼                  ▼
WeatherTools :8002   TicketTools :8001    TripTools :8003
 query_weather       3 查询 + 3 预定       3 查询 + 3 预定 + 旅游团 RAG

        └──────────────────┴──────────────────┘
                           ▼
   MySQL 8.0 / travel_rag（10 张表）  ──连接失败──▶  SQLite / data/smartvoyage.db
   和风天气 API（可选，WEATHER_SOURCE=api）      Milvus + Qwen Embedding（可选）
```

分层边界：

- 编排层**不直接访问业务表**，只通过 A2A 下发自然语言任务；
- 子代理**不含 SQL**，通过 MCP 加载工具后由 LangChain Agent 决策调用；
- 工具层**不含对话逻辑**，只做参数化查询与格式化返回；
- 三个子代理各自独立进程，MCP 故障只影响对应领域，不会拖垮整体。

## 核心能力

| 模块 | 仓库状态 | 边界 |
|---|---|---|
| 对话编排 | 已实现并验证 | 单轮多意图、Planning + ReAct、独立意图并行 |
| 意图识别 | 已实现并验证 | LLM 输出 JSON；无 Key 时降级为 10 类规则匹配 |
| 多轮记忆 | 已实现并验证 | 短期 10 条、偏好、任务上下文、实体 20 条；MySQL 持久化并可重启恢复 |
| 天气 MCP | 已实现并验证 | 1 个工具；`database` / `api` 双数据源，缺省日期自动补 3 天 |
| 票务 MCP | 已实现并验证 | 3 查询 + 3 预定，全部参数化 SQL |
| 行程 MCP | 已实现并验证 | 3 查询 + 3 预定 + 旅游团语义检索 |
| A2A 子代理 | 已实现并验证 | 3 个，AgentCard 技能数 1 / 6 / 6 |
| 追问状态机 | 已实现并验证 | 结构化标记 + 三条件兜底；7 个判定用例通过 |
| Web 前端 | 已实现并验证 | 单页原生 JS：流式开关、代理卡片、记忆面板、路由标签 |
| CLI 客户端 | 已实现并验证 | `quit` / `cards` / `memory` / `clear` |
| 数据库初始化 | 已实现并验证 | MySQL 建库建号 + 10 表 + 模拟数据；SQLite 同源生成 |
| 天气采集 | 已实现并验证 | 24 小时增量、UPSERT、定时调度；**真实 API 未验证**（无 Key） |
| 容器编排 | 配置已就绪，**未实机跑通** | 单镜像 8 服务，本机未执行 `docker compose up` |
| Milvus 向量检索 | 代码已就绪，**当前未启用** | 无 `pymilvus` / 无 Milvus 服务，自动走本地 n-gram 检索 |
| 真实预订 | **未接入** | 预定工具返回模拟回执，不写库、不出票、不接支付 |

### 当前状态与边界

- 当前定位是**本地单机验证型工程**，不是生产系统：无账号体系、无鉴权、无 HTTPS、无多租户隔离；Web API 的 CORS 为 `*`；
- 业务数据全部为模拟数据，覆盖 2025-07-30、2025-08-11、2025-08-23 与 2026 年五一（05-01～05-05），不对应真实库存；
- 预定类工具（火车票/机票/演出票/租车/旅游团/保险）只返回格式化的模拟回执，**不写库、不扣减余票、不接支付**；
- 编排层记忆保存在进程内存并同步到 MySQL；`ChatService` 若以多 worker 方式部署，记忆与会话状态会分裂，当前按单进程设计；
- 大模型走 DashScope OpenAI 兼容模式，默认 `qwen3.6-plus`；未配置 Key 时自动切换到规则式离线路由（仍走真实 MCP 调用链）；
- 前端为无构建链的单页 HTML，不含路由、打包与组件化。

### 已知限制

- 本机同时存在其他项目的 `MYSQL_DATABASE` / `MYSQL_USER` 环境变量时，需要为本项目设置 `SV_MYSQL_*`（优先级更高），否则会连到别的库；
- MySQL 可连接但库内缺少业务表时**不会自动降级**，会直接报 `Table ... doesn't exist`，需先执行 `scripts/init_db.py` 或核对库名；
- 和风天气实时链路需要 `HEFENG_WEATHER_API_KEY` 与 `HEFENG_API_HOST`，仓库内只验证了 `database` 数据源；
- 旅游团语义检索在当前环境使用中文字符 n-gram + 余弦相似度，属于可用性兜底，不等价于向量召回质量；
- 容器编排（`docker-compose.yml`、`entrypoint.sh`）已完成静态校验，未在本机实际拉起容器验证。

## 数据链路

### 表结构与模拟数据

建表脚本 [`SmartVoyage/sql/create_all_tables.sql`](SmartVoyage/sql/create_all_tables.sql) 是**唯一 DDL 来源**，模拟数据在 [`insert_may01_data.sql`](SmartVoyage/sql/insert_may01_data.sql)：

| 表 | 用途 | 模拟行数 |
|---|---|---|
| `train_tickets` | 火车票（车次、席别、票价、余票） | 8 |
| `flight_tickets` | 机票（航班号、舱位、票价、余票） | 5 |
| `concert_tickets` | 演出票（艺人、场馆、票档） | 4 |
| `weather_data` | 天气（最高/最低温、湿度、风力、降水） | 15 |
| `car_rentals` | 租车（公司、车型、日租金、押金） | 6 |
| `insurances` | 保险（类型、保额、保障天数） | 5 |
| `tour_groups` | 旅游团（行程、价格、亮点、描述） | 6 |
| `user_profiles` | 用户偏好（键值对） | 运行时写入 |
| `query_history` | 查询实体历史 | 运行时写入 |
| `short_term_messages` | 短期对话（角色、内容、顺序） | 运行时写入 |

数据覆盖的城市包括北京、上海、广州、深圳、成都、杭州、南京、西安、三亚；旅游团覆盖川西雪山、成都亲子、三亚海滨、江南古镇、内蒙古草原、西安古都六类主题。

### 天气数据采集

[`SmartVoyage/utils/spider_weather.py`](SmartVoyage/utils/spider_weather.py) 对应和风天气 30 天预报接口（`/v7/weather/30d`），覆盖 7 个常用城市：

```bash
python -m SmartVoyage.utils.spider_weather --once       # 立即更新一次
python -m SmartVoyage.utils.spider_weather --force      # 忽略 24 小时增量判断
python -m SmartVoyage.utils.spider_weather --scheduler  # 每天 01:00 定时执行
```

- 以 `(city, fx_date)` 唯一键做 UPSERT，重复采集不会产生脏数据；
- 先读 `MAX(update_time)`，24 小时内跳过，避免频繁调用付费接口；
- 响应为 gzip 压缩，按 `Content-Encoding` 解压后解析；
- 未配置 Key 或 API Host 时记录告警并跳过在线采集，不影响其他链路。

### 单一定义与自动降级

- MySQL DDL 由 `mysql_to_sqlite_script()` 做最小方言转换后生成 SQLite 库，**一张表只维护一份定义**；
- MySQL 连接失败（未启动、账号错误、网络不可达）时自动切到 `data/smartvoyage.db`，业务代码零改动；
- 降级链路对 `ON DUPLICATE KEY UPDATE` → `INSERT OR REPLACE`、`NOW()`、`%s` 占位符做自动翻译。

## 智能体体系与技术选型

| 组件 | 选型目的 | 工程实现 |
|---|---|---|
| 编排模型 | 意图识别、规划、结果润色 | `ChatOpenAI` + DashScope 兼容接口，默认 `qwen3.6-plus`，`temperature=0.1` |
| Agent 框架 | 子代理内的工具决策 | LangChain `create_tool_calling_agent` + `AgentExecutor(max_iterations=6)` |
| 工具协议 | Agent 与工具解耦 | MCP `FastMCP`，`streamable-http` 传输，共用 `load_mcp_tools` 加载 |
| Agent 协议 | Agent 间互操作与能力发现 | `python-a2a` 的 `A2AServer` / `A2AClient` / `AgentCard` |
| 任务状态 | 区分完成 / 追问 / 失败 | `TaskState.COMPLETED` / `INPUT_REQUIRED` / `FAILED` |
| 记忆存储 | 跨重启保留上下文 | MySQL 三表；未注入连接时静默降级为纯内存（便于单测） |
| 语义检索 | 旅游团自然语言匹配 | Milvus + `text-embedding-v3`（1024 维，COSINE）；不可用时本地 n-gram 检索 |
| Web 服务 | REST 与流式输出 | FastAPI + `StreamingResponse`（SSE），静态页 `FileResponse` |
| 日志 | 多进程统一排查 | `colorlog` 控制台 + 文件，各服务独立日志在 `logs/` |

`python-a2a` 与 `mcp` 的版本经过固定，`0.5.4` 与 `1.18.0` 的 `Task` / `TaskStatus` / `FastMCP` 签名与当前实现一致，升级前需回归 A2A 任务结构。

## 编排链路与追问状态机

### 一次请求的处理路径

1. **写入记忆**：用户消息进入短期对话，并立即同步到 `short_term_messages`；
2. **意图识别**：把短期对话、用户偏好、当前任务上下文、当前日期一起交给意图提示词，输出 `intents` 与 `user_queries`；无 Key 时走规则匹配；
3. **路由判定**：单意图或全部为独立意图时跳过规划，直接并行；存在依赖时才调用规划器；
4. **执行**：独立意图 `asyncio.gather` 并行下发；有依赖时按 `steps` 串行执行 ReAct（Thought → Action → Observation）；
5. **子代理调用**：按 `intent` 找到 A2A 地址，组装 `Task` 调用 `send_task_async`；仅当上一轮子代理追问过，才把历史对话带下去，避免历史城市污染新问题；
6. **状态处理**：`completed` 取 artifacts 文本；`input-required` 原样透传追问；`failed` 返回错误提示；
7. **汇总与落库**：多结果交给汇总提示词整合，单结果直接返回，随后写入助手消息。

### 意图识别与启发式路由

- 意图共 10 类：`weather`、`flight`、`train`、`concert`、`order`、`car_rental`、`tour_group`、`insurance`、`trip_order`、`attraction`；前 9 类映射到 3 个子代理，`attraction` 由编排层直接调用景点提示词；
- 离线模式下按关键词表顺序匹配，并支持两类继承：上一轮在追问 → 继承意图并补历史；上一轮已成功 → 本轮只补槽位时沿用上一轮查询条件（新槽位放前面，覆盖旧值）；
- `_should_skip_planning()` 是路由开关：意图数 ≤ 1，或全部属于独立意图集合，就不产生额外 LLM 规划调用。

### 并行与 ReAct

- 独立意图：`asyncio.gather` 并发，总耗时约等于最慢的那一路；
- 有依赖：规划器输出 `steps`（含 `depends_on`），逐个执行并把 Observation 累积给汇总提示词；
- 规划结果解析失败时直接降级为顺序执行，不阻塞主流程。

### 追问判定

原实现只用正则匹配「请提供 / 请确认」，会把带数据的结果误判成追问。现在的判定顺序：

| 优先级 | 判定依据 | 结果 |
|---|---|---|
| 1 | `status == error` | `failed` |
| 2 | `status == input_required` | `input_required` |
| 3 | Agent 输出以 `[NEED_INPUT]` 开头 | `input_required`，标记被剥离后展示 |
| 4 | `need_input` 显式为 `False` | `completed` |
| 5 | 兜底：追问句式 **且** 无数据证据 **且** 短文本 | 三者同时成立才 `input_required` |

「数据证据」包含车次/航班号、`¥` 或「元」、温度、`YYYY-MM-DD`、余票/票价/湿度，以及「以下是 / 查询到 / 共找到 / 推荐」等结果句式。回归用例：

| 用例 | 输入特征 | 期望 |
|---|---|---|
| 缺日期追问 | 「请提供出发日期？」 | `input_required` |
| 显式标记 | `[NEED_INPUT]` + 追问 | `input_required` |
| 结构化完成 | 车次 + 票价 + `need_input=False` | `completed` |
| 结果含「请确认」 | G942、808.51 元、余票 19 张 | `completed` |
| 旧版含数据 | G101、662.00 元、末尾「请提供是否预订」 | `completed` |
| 旧版纯追问 | 「请提供出发城市和到达城市？」 | `input_required` |
| 工具异常 | MCP 连接失败 | `failed` |

## 服务接口

### MCP 工具（13 个）

| 服务 | 端口 | 工具 | 说明 |
|---|---|---|---|
| `WeatherTools` | 8002 | `query_weather(city, start_date, end_date)` | `city` 留空或填「全国」返回四大热门城市；缺省日期取今天起 3 天 |
| `TicketTools` | 8001 | `query_train(departure_city, arrival_city, date, seat_type?)` | 席别可选，按出发时间与价格排序 |
| | | `query_flight(departure_city, arrival_city, date, cabin_type?)` | 舱位可选 |
| | | `query_concert(city, artist, date, ticket_type?)` | 票档可选 |
| | | `order_train / order_flight / order_concert` | 模拟预定，返回回执文本 |
| `TripTools` | 8003 | `query_car_rental(pickup_city, return_city, date, car_type?)` | 按日租金排序 |
| | | `query_tour_group(query_text, city?)` | 语义检索，返回相似度 |
| | | `query_insurance(insurance_type?)` | 类型可选 |
| | | `order_car_rental / order_tour_group / order_insurance` | 模拟预定 |

统一返回结构：`{"status": "success" | "no_data" | "error", "data": [...], "message": "..."}`。所有查询条件以参数化 SQL 下推到数据库，不在应用层过滤全表。

### A2A 子代理（3 个）

| 端口 | Agent | 技能数 | 上游 MCP | 说明 |
|---|---|---|---|---|
| 5005 | `WeatherQueryAssistant` | 1 | `:8002/mcp` | 城市 + 日期天气，支持多城市对比 |
| 5006 | `TicketAssistant` | 6 | `:8001/mcp` | 火车票 / 机票 / 演出票查询与预定 |
| 5007 | `TripAssistant` | 6 | `:8003/mcp` | 租车、保险、旅游团查询与预定 |

AgentCard 通过 `GET /agent.json` 暴露，编排层的能力面板直接读取该端点；服务未启动时回退到本地静态卡片。

### HTTP API 与 SSE

| 方法 | 路径 | 功能 |
|---|---|---|
| `GET` | `/` | 对话页面 |
| `GET` | `/health` | 存活探测 |
| `POST` | `/api/chat` | 同步对话，返回 `message` 与命中代理 |
| `POST` | `/api/chat/stream` | SSE 流式对话，事件为 `start` / `delta` / `done` / `error` |
| `GET` | `/api/memory` | 短期对话、偏好、任务上下文、实体历史 |
| `POST` | `/api/memory/profile` | 写入用户偏好 |
| `POST` | `/api/memory/clear` | 清空记忆（内存 + 库） |
| `GET` | `/api/agents` | 三个子代理的 AgentCard 汇总 |

请求示例：

```json
{ "message": "帮我查下成都 2026-05-01 的天气和北京到成都 2026-05-01 的火车票" }
```

响应示例：

```json
{
  "status": "success",
  "message": "……",
  "agents": ["WeatherQueryAssistant", "TicketAssistant"]
}
```

### CLI

```text
python -m SmartVoyage.main

quit | exit | q   退出
cards             查看三个子代理的 AgentCard
memory            查看短期对话、偏好、任务上下文、实体历史
clear             清空记忆
```

启动时会探测 5005/5006/5007/8001/8002/8003 六个端口，未就绪时给出启动提示。

## 项目结构与关键文件

```text
.
├── SmartVoyage/
│   ├── config.py                环境变量驱动的统一配置（密钥不落代码）
│   ├── create_logger.py         全局日志：控制台 + logs/app.log
│   ├── db.py                    MySQL/SQLite 双实现、方言转换、连接降级
│   ├── memory.py                四类记忆 + MySQL 持久化与重启恢复
│   ├── main_prompts.py          6 类提示词：意图/规划/汇总/景点/天气/票务
│   ├── chat_service.py          编排核心：意图 → 路由 → 执行 → 汇总
│   ├── vector_store.py          旅游团语义检索（Milvus 优先，本地兜底）
│   ├── main.py                  CLI 客户端
│   ├── api_server.py            FastAPI：REST + SSE + 静态页
│   ├── a2a_server/
│   │   ├── base_agent.py        LLM+MCP 执行、状态判定、服务启动
│   │   ├── offline.py           规则式离线路由（仍走真实 MCP）
│   │   ├── weather_server.py    5005 天气代理
│   │   ├── ticket_server.py     5006 票务代理
│   │   └── trip_server.py       5007 行程代理
│   ├── mcp_server/
│   │   ├── mcp_weather_server.py  8002 天气工具
│   │   ├── mcp_ticket_server.py   8001 票务工具
│   │   └── mcp_trip_server.py     8003 行程工具 + RAG
│   ├── sql/
│   │   ├── create_all_tables.sql  10 张表 DDL
│   │   └── insert_may01_data.sql  跨日期模拟数据
│   ├── static/index.html        单页前端
│   ├── tests/                   53 个用例
│   └── utils/
│       ├── format.py            date/Decimal/timedelta 的 JSON 编码器
│       └── spider_weather.py    和风天气采集与定时调度
├── scripts/
│   ├── init_db.py               建库建号 + 建表 + 灌数据（MySQL/SQLite）
│   ├── start_all.py             一键启动 6/7 个服务
│   └── smoke_test.py            A2A→MCP→DB 端到端 8 用例
├── Dockerfile                   统一镜像
├── entrypoint.sh                按 SERVICE_NAME 分派进程
├── docker-compose.yml           8 个服务的编排
├── requirements.txt
├── .env.example
└── README.md
```

关键入口：

| 文件 | 作用 |
|---|---|
| `SmartVoyage/chat_service.py` | 编排主流程；`chat()` 是唯一对外入口 |
| `SmartVoyage/a2a_server/base_agent.py` | `query_via_mcp()` 与 `classify_result()`，追问判定在此实现 |
| `SmartVoyage/db.py` | `get_connection()` 决定走 MySQL 还是 SQLite |
| `SmartVoyage/mcp_server/_common.py` | MCP 服务统一 host/port 选项 |
| `scripts/start_all.py` | 服务启动顺序、端口探测、日志分流 |
| `SmartVoyage/api_server.py` | 前后端契约与 SSE 事件格式 |

## 环境准备与运行方式

### 前置条件

| 项 | 要求 |
|---|---|
| OS | Windows 10/11（本项目在 Windows + Git Bash 下验证；核心服务可移植到 Linux/macOS） |
| Python | 3.12（本项目实测 3.12.11，虚拟环境 `D:\Miniconda3\envs\SmartVoyage`） |
| MySQL | 8.0，默认库 `travel_rag`，账号 `smart_yoyage`（可由 `init_db.py` 自动创建） |
| 大模型 | DashScope Key（`DASHSCOPE_API_KEY`）；不配置时进入离线规则模式 |
| 可选 | 和风天气 Key（`WEATHER_SOURCE=api`）、Milvus + `pymilvus`（向量检索） |

### 依赖安装

```bash
python -m pip install -r requirements.txt
```

| 约束 | 原因 |
|---|---|
| `mcp==1.18.0` | `FastMCP` 的 `streamable_http_app` 与 `run(transport=...)` 签名在此版本确定 |
| `python-a2a==0.5.4` | `TaskStatus` / `TaskState` 结构影响子代理状态机 |
| `langchain==0.3.26` + `langchain-mcp-adapters==0.1.11` | `create_tool_calling_agent` 与 MCP 工具加载器配套 |
| `mysql-connector-python==9.4.0` | 连接参数与 `ping(reconnect, attempts, delay)` 用法 |

> `streamlit` 沿课程依赖保留，当前 Web 入口为 FastAPI + 原生前端，未使用 Streamlit。

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

至少填写 `DASHSCOPE_API_KEY`。数据库配置建议使用 `SV_MYSQL_*`：

```ini
SV_MYSQL_HOST=127.0.0.1
SV_MYSQL_PORT=3306
SV_MYSQL_USER=smart_yoyage
SV_MYSQL_PASSWORD=changeme      # 示例值，改成你本机 MySQL 的实际口令
SV_MYSQL_DATABASE=travel_rag
```

> `SV_` 前缀优先于通用 `MYSQL_*`。若本机其他项目已设置 `MYSQL_DATABASE`，直接用通用变量名会连到别的库。

### 2. 初始化数据库

```bash
python scripts/init_db.py              # 建库、建项目账号、建表、灌模拟数据
python scripts/init_db.py --sqlite     # 只初始化 SQLite 降级库
python scripts/init_db.py --mysql-only # 只走 MySQL，失败即报错
```

初始化完成后会打印各表行数；需要的管理员权限通过 `MYSQL_ADMIN_USER` / `MYSQL_ADMIN_PASSWORD` 指定。

### 3. 启动服务

```bash
# 在线模式：6 个服务（3 MCP + 3 A2A）
python scripts/start_all.py

# 追加 Web API，共 7 个进程，访问 http://127.0.0.1:8080
python scripts/start_all.py --with-api

# 离线模式：不调用大模型，规则路由 + 真实 MCP 链路
python scripts/start_all.py --offline --with-api

# 只启动某一层
python scripts/start_all.py --group mcp
```

按依赖顺序启动并逐个探测端口，日志分流到 `logs/<service>.log`；端口已被占用时打印 `[SKIP]` 并跳过。端口可用环境变量覆盖：

```bash
API_PORT=8090 python scripts/start_all.py --with-api   # 8080 被占用时
```

### 4. 命令行对话

```bash
python -m SmartVoyage.main
```

```text
请输入您的问题: 北京 2025-07-30 的天气怎么样
请输入您的问题: 查一下火车票
请输入您的问题: 北京到上海 2025-07-30
请输入您的问题: 二等座
```

第 2 轮「查一下火车票」缺参数，子代理返回追问；第 3 轮补齐城市与日期后拿到车次；之后只输入「二等座」「商务座」，席别被覆盖，城市与日期沿用上一轮条件。

### 5. Web 对话

浏览器打开 `http://127.0.0.1:8080/`，页面提供流式开关、示例问题、代理卡片面板、记忆面板（刷新/清空/偏好保存）与命中代理标签。

### 6. 验收

```bash
# 单元测试（已启动服务时为 53/53）
python -m unittest discover -s SmartVoyage/tests -t .

# 端到端冒烟（需 6 个服务就绪）
python scripts/smoke_test.py
python scripts/smoke_test.py --case ticket
```

## 配置说明

### 配置文件

| 文件 | 作用 |
|---|---|
| `.env` | 本机配置，已被 `.gitignore` 忽略 |
| `.env.example` | 配置模板，含主要变量与注释 |
| `SmartVoyage/config.py` | 读取环境变量、提供意图映射与服务地址 |
| `docker-compose.yml` | 容器环境下的同义变量（服务名替代 127.0.0.1） |

### 关键环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 大模型 Key；为空则进入离线规则模式 | 未设置 |
| `LLM_BASE_URL` | OpenAI 兼容接口地址 | DashScope 兼容模式 |
| `LLM_MODEL_NAME` | 模型名 | `qwen3.6-plus` |
| `LLM_TEMPERATURE` | 采样温度 | `0.1` |
| `SV_MYSQL_HOST` / `SV_MYSQL_PORT` | 数据库地址/端口 | `127.0.0.1` / `3306` |
| `SV_MYSQL_USER` / `SV_MYSQL_PASSWORD` | 业务账号 | `smart_yoyage` / `changeme`（占位） |
| `SV_MYSQL_DATABASE` | 业务库名 | `travel_rag` |
| `MYSQL_ADMIN_USER` / `MYSQL_ADMIN_PASSWORD` | 初始化脚本建库建号所用管理员 | `root` / 同业务密码 |
| `WEATHER_SOURCE` | `database` 教学数据 / `api` 和风实时 | `database` |
| `HEFENG_WEATHER_API_KEY` | 和风天气 Key | 空 |
| `HEFENG_API_HOST` | 和风 API 主机 | 空 |
| `MILVUS_HOST` / `MILVUS_PORT` | 向量库地址 | `127.0.0.1` / `19530` |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | 向量模型与维度 | `text-embedding-v3` / `1024` |
| `WEATHER_A2A_URL` / `TICKET_A2A_URL` / `TRIP_A2A_URL` | 子代理地址 | `127.0.0.1:5005/5006/5007` |
| `WEATHER_MCP_URL` / `TICKET_MCP_URL` / `TRIP_MCP_URL` | 工具服务地址 | `127.0.0.1:8002/8001/8003/mcp` |
| `SV_OFFLINE` | `1` 强制规则式离线 | `0` |
| `SV_DB_FALLBACK` | MySQL 失败时降级 SQLite | `1` |
| `SV_SQLITE_PATH` | 降级库路径 | `data/smartvoyage.db` |
| `LOG_FILE` | 日志文件 | `logs/app.log` |
| `WEATHER_MCP_PORT` / `TICKET_MCP_PORT` / `TRIP_MCP_PORT` | MCP 端口 | `8002` / `8001` / `8003` |
| `WEATHER_A2A_PORT` / `TICKET_A2A_PORT` / `TRIP_A2A_PORT` | A2A 端口 | `5005` / `5006` / `5007` |
| `API_PORT` | Web API 端口 | `8080` |
| `HOST` | 服务监听地址 | `127.0.0.1`（容器内 `0.0.0.0`） |

## 评估与验收口径

- **功能验收**：`scripts/smoke_test.py` 的 8 个用例覆盖三条子代理链路，期望状态为 `completed` 或 `input-required`，状态不符即失败；
- **状态机验收**：追问判定以「是否含数据证据」为准，带车次/票价/温度的回复不得判为追问；
- **编排验收**：单意图、多意图并行、追问后补槽位、只换席别四类对话均需返回有效结果；
- **数据一致性**：所有查询必须通过参数化 SQL 完成，禁止把全表捞到应用层过滤；
- **离线可跑**：`SV_OFFLINE=1` 时不依赖大模型，仍应返回结构化结果；
- **检索质量**：旅游团检索只校验「口语化描述能否命中正确团」，不声称向量召回指标。

> 本项目的「准确」指业务链路与状态机行为，不含模型回答质量评测；LLM 输出未做人工评分或基准集比对。

## 测试与工程质量

### 验证快照（2026-11-12 复跑）

| 检查项 | 结果 | 证据边界 |
|---|---|---|
| 单元测试（服务已启动） | `Ran 53 tests ... OK`，7.7s | 离线模式，A2A→MCP→MySQL 真实链路 |
| 单元测试（服务未启动） | `OK (skipped=7)` | 7 个集成用例按设计跳过 |
| 端到端冒烟 | `8/8 通过` | 天气 2、票务 3、行程 3 |
| 追问判定用例 | 7/7 通过 | 含「结果含请确认但带车次」不误判 |
| 旅游团语义检索 | 「想看雪山的地方」命中川西雪山团，相似度 `0.4797` | 本地 n-gram 路径 |
| Web 接口 | `/health`、`/`、`/api/chat`、`/api/chat/stream`、`/api/memory`、`/api/memory/profile`、`/api/memory/clear`、`/api/agents` 全部通过 | 离线模式，SSE 事件 `start/delta/done` |
| AgentCard 发现 | 1 / 6 / 6 个技能 | 从 `/agent.json` 实拉 |
| 数据库初始化 | MySQL `travel_rag` 10 表；SQLite 同源生成 | 本机 MySQL 8.0 |
| 静态检查 | `compileall` 通过；无硬编码密钥 | 仓库内代码与脚本 |

### 当前工程约束

- 仓库**未配置 CI**，上述结果均为本机隔离验证；
- 集成用例依赖 6 个已启动服务，未启动时自动跳过，不能把跳过等同于通过；
- 真实和风天气、Milvus 向量检索、容器编排**未验收**；
- 未做并发压测；在线模式单次请求涉及多次 LLM 调用，端到端通常 60～110 秒，离线模式为毫秒级。

### 联调中修复的真实缺陷

| 缺陷 | 现象 | 修复 |
|---|---|---|
| 历史对话污染新查询 | 新问题复用上一轮城市/日期 | 仅在上一轮 `input-required` 时才把历史带给子代理 |
| 多意图子查询串味 | 「成都天气 + 北京到成都机票」两路都拿到成都 | 按连接词切分子查询，再补齐各自缺失的城市/日期 |
| 槽位补充不覆盖旧值 | 先查二等座再问商务座，仍返回二等座 | 本轮补充放查询串最前，新槽位优先 |
| 追问误判 | 带票价的结果被判为 `input-required` | `[NEED_INPUT]` 标记 + 三条件兜底 |
| 配置串库 | 本机其他项目的 `MYSQL_DATABASE` 覆盖本项目 | 新增 `SV_MYSQL_*`，优先级高于 `MYSQL_*` |
| 端口占用无提示 | 8080 被占用时 API 被跳过，浏览器打开的是别的服务 | 启动脚本打印 `[SKIP]`，并支持 `API_PORT` 覆盖 |

## 部署与资产管理

- **镜像**：`Dockerfile` 构建单一镜像，`entrypoint.sh` 按 `SERVICE_NAME` 分派到 7 个进程之一；
- **编排**：`docker-compose.yml` 拉起 MySQL、3 个 MCP、3 个 A2A、1 个 API，`depends_on` 保证 MySQL 健康后再启工具层；
- **初始化**：MySQL 容器挂载 `SmartVoyage/sql` 到 `/docker-entrypoint-initdb.d`，首次启动自动建表；

```bash
docker build -t smart-voyage:latest .
docker compose up -d
docker compose logs -f api-server
```

- **数据**：`data/`（SQLite 降级库）与 `logs/` 已在 `.gitignore` 中，不入库；
- **密钥**：只通过 `.env` 或进程环境注入，容器内通过 compose 变量透传；
- **服务暴露**：默认无鉴权、无 HTTPS，CORS 为 `*`，仅适合本机或受信网络；
- **未验证项**：本机未实际执行 `docker compose up`，编排文件只做了结构校验（服务数、环境变量、端口映射）。

## 项目交付成果

- 完成 3 层 7 进程架构：编排层（ChatService）、代理层（3 个 A2A）、工具层（3 个 MCP）；
- 完成 10 类意图识别、启发式路由、Planning 依赖判定、并行执行与 ReAct 串行回退；
- 完成 13 个 MCP 工具，全部参数化 SQL，统一 `status/data/message` 返回结构；
- 完成 3 个 A2A 子代理与 1/6/6 技能的能力卡片，支持从 `/agent.json` 动态发现；
- 修复参考资料点名的追问判定缺陷，并给出 7 个可复跑用例；
- 完成四类记忆与 MySQL 持久化，支持重启恢复、偏好复用、追问补槽位；
- 完成 10 张表 DDL、跨日期模拟数据、和风天气采集脚本与增量更新；
- 完成 MySQL/SQLite 双数据层，单一定义、自动降级，离线环境可直接演示；
- 完成 CLI、FastAPI（REST + SSE）、单页前端三套入口；
- 完成 53 个单元测试、8 个端到端用例、一键启动脚本与容器编排；
- 配置、密钥、数据、日志边界清晰，`.env` 与运行产物不入库。

## 许可证

仓库暂未添加开源许可证。项目基于课程参考资料实现，第三方地图/天气/票务数据的权属与授权范围需在对外发布前自行确认。
