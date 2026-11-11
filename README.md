# Anchor Memory

Anchor Memory 是一个面向大语言模型（LLM）对话与伴侣系统的本地长期记忆与认知状态管理系统，完全支持标准 MCP（Model Context Protocol）协议。

系统采用**本地优先（Local-First SQLite + Markdown 镜像）**架构，参考认知心理学将人类记忆系统拆解为三个紧密协作的层次：前额叶实时工作台、长期情绪坐标库、以及情境感知的程序性行为指南，并辅以每日自动复盘沉淀机制与多范围聊天记录检索工具。

---

## 目录 / Table of Contents

- [1. 系统架构与核心设计](#1-系统架构与核心设计)
  - [1.1 总体分层架构](#11-总体分层架构)
  - [1.2 前额叶工作台 (Working Memory / 未竟之事)](#12-前额叶工作台-working-memory--未竟之事)
  - [1.3 长期记忆库与情绪半衰期衰减 (Long-Term Memory)](#13-长期记忆库与情绪半衰期衰减-long-term-memory)
  - [1.4 程序性行为指南 (Procedural Guides)](#14-程序性行为指南-procedural-guides)
  - [1.5 每日复盘与对话压缩机制 (Consolidation Pipeline)](#15-每日复盘与对话压缩机制-consolidation-pipeline)
  - [1.6 本地 Markdown 镜像 (Obsidian Vault Mirror)](#16-本地-markdown-镜像-obsidian-vault-mirror)
- [2. 记忆召回引擎 (4-Path Recall)](#2-记忆召回引擎-4-path-recall)
- [3. MCP 工具体系全览 (12 核心工具)](#3-mcp-工具体系全览-12-核心工具)
  - [3.1 工作记忆类工具 (4 个)](#31-工作记忆类工具-4-个)
  - [3.2 长期记忆类工具 (5 个)](#32-长期记忆类工具-5-个)
  - [3.3 历史聊天记录检索工具 (1 个)](#33-历史聊天记录检索工具-1-个)
  - [3.4 行为指南类工具 (2 个)](#34-行为指南类工具-2-个)
- [4. 前端设置面板 (Frontend Web UI)](#4-前端设置面板-frontend-web-ui)
  - [4.1 前端功能模块说明](#41-前端功能模块说明)
  - [4.2 前端代码使用与集成方法](#42-前端代码使用与集成方法)
- [5. 快速部署与接入指南](#5-快速部署与接入指南)
  - [5.1 环境要求与依赖安装](#51-环境要求与依赖安装)
  - [5.2 独立启动 MCP 服务](#52-独立启动-mcp-服务)
  - [5.3 接入 Claude Desktop 或其他 MCP 客户端](#53-接入-claude-desktop-或其他-mcp-客户端)
  - [5.4 作为 Python 库直接嵌入现有项目](#54-作为-python-库直接嵌入现有项目)
- [6. 配置项说明 (Environment Variables)](#6-配置项说明-environment-variables)
- [7. 本地数据存储与安全说明](#7-本地数据存储与安全说明)
- [8. 开源许可 (License)](#8-开源许可-license)

---

## 1. 系统架构与核心设计

### 1.1 总体分层架构

Anchor Memory 的核心设计目标是解决传统记忆方案“单向搜索慢、缺乏遗忘规律、短期背景丢失、云端隐私不可控”的问题。系统由以下几个部分组成：

```
                          [ 用户实时对话输入 ]
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │  前额叶工作台   │       │  4路混合召回引擎 │       │  情境行为指南   │
 │ Working Memory  │       │ (语义/实体/     │       │ Procedural      │
 │ (活跃未竟状态)  │       │  情绪/新近度)   │       │ Playbook        │
 └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    ▼
                     [ 结构化上下文无损注入 Prompt ]
                                    │
                               [ 智能体交互 ]
                                    │
                                    ▼ (每日复盘周期)
                     ┌───────────────────────────────┐
                     │     每日复盘流水线 (Midnight)   │
                     │  - 全天心境经历长文叙事压缩    │
                     │  - 情绪坐标计算与新记忆抽取    │
                     │  - 前额叶审计与 2 天缓冲期驱逐  │
                     │  - 艾宾浩斯情绪半衰期衰减重算  │
                     │  - 本地 Markdown Vault 双向同步│
                     └───────────────────────────────┘
```

### 1.2 前额叶工作台 (Working Memory / 未竟之事)
- **定位**：模拟大脑前额叶皮层，专门承载“当前阶段持续需要关注的短期背景状态”（如近期身体状况、正在推进中的事项、承诺与待办）。
- **常驻注入**：前额叶中所有处于 `active` 状态的事项，**无需搜索，每轮对话都会作为背景常驻注入 Prompt**，保证模型永远对近期的关键状态保持清晰认知。
- **2 天防误判缓冲池**：当某事项被办结或标记过期时，系统绝不直接从数据库中物理删除，而是将其状态标记为 `expired` 并保留 2 天。在此期间如果发现是模型误判，可随时调用 `working_memory_restore` 工具重新恢复为活跃状态。

### 1.3 长期记忆库与情绪半衰期衰减 (Long-Term Memory)
每一条沉淀到长期库的记忆均附带三维物理情绪坐标：
- **重要度 (Importance)**：0.0 ~ 1.0。若重要度 $\ge 0.8$（核心记忆/重要约定），享有底线保护（Retention Floor $\ge 0.5$），永远不会因为时间推移而彻底归零。
- **情绪愉悦度 (Valence)**：-1.0（负向情绪/委屈/痛苦）至 +1.0（正向情绪/喜悦/感动）。
- **情绪激烈度 (Arousal)**：0.0（平静日常）至 1.0（剧烈激动/深刻触动）。
- **遗忘曲线模型**：结合情绪唤醒度与艾宾浩斯遗忘定律，情绪越激烈（Arousal 越高）的经历，半衰期越长：
  $$\lambda = \text{base\_}\lambda \times (1 + \text{arousal} \times k)$$
  $$\text{EffectiveWeight} = \text{importance} \times e^{-\frac{\text{days}}{\lambda}}$$
  日常琐碎在数周后自然平滑降权，重要记忆长期保持活跃。衰减仅调整检索召回时的排序打分，原始记忆数据在本地永久保留。

### 1.4 程序性行为指南 (Procedural Guides)
- **定位**：记录特定相处情境下的“建议执行策略”与“绝对避雷禁区”。
- **前置匹配**：基于情境关键词与置信度算法，在用户输入契合特定情境时，以最高优先级注入到上下文顶层，引导模型输出符合预期的反应。

### 1.5 每日复盘与对话压缩机制 (Consolidation Pipeline)
每日深夜或对话空闲阶段，系统可自动或手动执行复盘流水线：
1. **全天心境叙事压缩**：将全天分散的聊天记录归纳为一段 500~800 字的第一人称心境与经历长文叙事，第二天唤醒时作为昨日背景注入，保持对话的连续感。
2. **长期记忆沉淀与情绪估算**：从全天对话中抽取值得铭记的事实与经历，自动补齐情绪坐标并入库。
3. **前额叶清算**：标记办结事项，超出 2 天缓冲期的过期条目平稳清理。
4. **醒来便签 (Wake Note)**：为第二天生成一份精炼的晨间关注点备忘录。
5. **衰减打分重算**：每日对所有长期记忆重新计算 Retention Weight。

### 1.6 本地 Markdown 镜像 (Obsidian Vault Mirror)
- 所有沉淀的长期记忆和每日复盘摘要，均会以纯文本 Markdown 格式输出至本地镜像目录。
- 采用规范的 YAML Frontmatter（记录 ID、重要度、情绪值、标签等）。
- 完美兼容 Obsidian、Logseq 等本地双链笔记工具，用户可以直接查看、编辑卡片或手写批注。

---

## 2. 记忆召回引擎 (4-Path Recall)

Anchor Memory 采用 4 路独立信号加权综合重排算法，全面平衡语义契合与情感关联：

$$\text{FinalScore} = (w_{sem} \cdot S_{sem} + w_{ent} \cdot S_{ent} + w_{emo} \cdot S_{emo} + w_{rec} \cdot S_{rec}) \times \text{DecayScore}$$

- **语义相似度 ($S_{sem}$，权重 0.40)**：计算输入与记忆文本的向量余弦距离。支持配置外部 Embedding API，并在无外网时自动降级到本地字符级向量算法。
- **实体命中率 ($S_{ent}$，权重 0.30)**：精准比对关键人名、地名、核心事实词汇。
- **情绪近邻度 ($S_{emo}$，权重 0.15)**：在 Valence-Arousal 二维平面上的欧氏空间距离，优先唤醒同频心境的经历。
- **时效新近度 ($S_{rec}$，权重 0.15)**：30 天平滑指数衰减，优先捕捉近期被提及或新沉淀的内容。

---

## 3. MCP 工具体系全览 (12 核心工具)

系统通过标准 MCP 协议向大语言模型暴露 12 个原子工具：

### 3.1 工作记忆类工具 (4 个)
- **`working_memory_add`**：添加一条当前这几天需要持续关注的短期状态、承诺或未竟事项。
  - 参数：`content` (描述), `category` ('todo' | 'state' | 'promise' | 'general')
- **`working_memory_update`**：更新既有未竟事项的进展细节或补充最新动态。
  - 参数：`item_id` (条目ID), `content` (更新后的描述)
- **`working_memory_expire`**：将办结或无需再关注的事项标记为过期并移入 2 天缓冲池（非物理删除）。
  - 参数：`item_id` (条目ID), `reason` (办结原因)
- **`working_memory_restore`**：误判救援：将处于过期缓冲池中的事项重新捞回为活跃关注状态。
  - 参数：`item_id` (条目ID), `restore_reason` (恢复原因说明)

### 3.2 长期记忆类工具 (5 个)
- **`memory_create`**：沉淀具备长期留存价值的生活经历、身份事实、伴侣偏好或核心承诺。
  - 参数：`content`, `category`, `importance` (0.0~1.0), `valence` (-1.0~+1.0), `arousal` (0.0~1.0), `emotion_label`, `entities`, `links`
- **`memory_update`**：修正或更正既有长期记忆的文字细节。
  - 参数：`memory_id`, `content`
- **`memory_add_note`**：记忆双向追加备注：为已有记忆挂载后续心境、进展或感受补充，不破坏原记忆文本。
  - 参数：`memory_id`, `content`
- **`memory_supersede`**：新事实更迭：用新记忆取代旧记忆，旧记忆自动打标为 superseded 历史版本存留。
  - 参数：`old_memory_id`, `new_content`, `reason`
- **`anchor_memory_search`**：按需主动深度检索长期记忆库（4 路加权重排）。
  - 参数：`query`, `limit` (默认 4)

### 3.3 历史聊天记录检索工具 (1 个)
- **`search_conversation`**：根据关键词、语义以及具体日期范围检索历史聊天记录。
  - 参数：
    - `query`: 检索词或句子
    - `scope`: 时间跨度范围，可选 `'recent'` (3天) \| `'7d'` (7天) \| `'30d'` (30天) \| `'90d'` (90天) \| `'all'` (全量历史)
    - `start_date`: 起始日期过滤，格式 `YYYY-MM-DD`（可选，支持精细到某一天）
    - `end_date`: 截止日期过滤，格式 `YYYY-MM-DD`（可选）
    - `limit`: 返回条目数（默认 6，最多 20）

### 3.4 行为指南类工具 (2 个)
- **`procedural_guide_create`**：录入特定情境下的最佳应对策略与绝对避雷禁区。
  - 参数：`situation` (情境描述), `playbook` (策略与语气要求), `taboos` (绝对避雷行为与禁忌话术)
- **`procedural_guide_update`**：微调或完善已有行为指南的策略与禁忌。
  - 参数：`guide_id`, `playbook`, `taboos`

---

## 4. 前端设置面板 (Frontend Web UI)

本项目在 `frontend/index.html` 中提供了一个开箱即用的前端独立设置面板，用于配置记忆系统的运行参数。

### 4.1 前端功能模块说明
1. **睡前对话余温衔接 (Bedtime Tail Bridge)**：
   - 支持开关配置。开启后，第二天唤醒时在昨日摘要下方额外拼接前一天临睡前的最后几句真实对话，保持语境连贯；
   - 支持“按轮次截取（默认 4 轮）”或“按 Token 预算截取（默认 400 Tokens）”。
2. **单日滚动对话压缩 (Daily Rolling Summary)**：
   - 用于在交谈消息过多时手动触发摘要压缩，释放原始消息占用的上下文窗口。
3. **老记忆情绪增量补齐 (Backfill)**：
   - 针对从外部或旧系统导入的无情绪标签记忆，在打烊批处理时逐步补齐情绪数值；
   - 支持配置每日批处理的最大条数（默认 10 条）。
4. **记忆主动搜索工具模式 (Search Tool Mode)**：
   - 基础 4 路召回每轮自动进行。该项控制模型自主搜索的权限：
     - `on_demand` (默认推荐)：按需由模型自主决定是否调用 `anchor_memory_search`；
     - `always`：始终强制在每轮提示词中暴露搜索工具；
     - `never`：完全禁用搜索工具（仅依赖前置自动注入）。
5. **低权重沉底记忆管理 (Decay Archive)**：
   - 浏览因时间衰减而沉底的低权重记忆，并可手动确认归档到 Vault，保持数据库整洁。

### 4.2 前端代码使用与集成方法
- **独立运行预览**：直接在浏览器中打开 `frontend/index.html` 即可预览完整 UI 交互。
- **与你的系统对接**：前端页面内已封装统一的 RESTful 请求处理（`GET /api/anchor/settings` 与 `POST /api/anchor/settings`），修改 `index.html` 内的 `API_BASE` 变量即可对接到你自己的后端路由。

---

## 5. 快速部署与接入指南

### 5.1 环境要求与依赖安装
- Python 3.10+
- 安装极简依赖（仅依赖标准 MCP SDK 与 Pydantic）：
  ```bash
  git clone https://github.com/yxiy171866-boop/Anchor-Memory.git
  cd Anchor-Memory
  pip install -r requirements.txt
  ```

### 5.2 独立启动 MCP 服务
```bash
python server.py
```
首次启动时，系统会自动在 `./data/anchor_memory.db` 初始化包含 7 张表的 SQLite 数据库，并在 `./anchor_vault/` 建立 Obsidian 镜像目录。

### 5.3 接入 Claude Desktop 或其他 MCP 客户端
在 Claude Desktop 的配置文件（`claude_desktop_config.json`）中添加以下配置：

```json
{
  "mcpServers": {
    "anchor-memory": {
      "command": "python",
      "args": ["/path/to/Anchor-Memory/server.py"],
      "env": {
        "ANCHOR_DB_PATH": "/path/to/data/anchor_memory.db",
        "ANCHOR_VAULT_PATH": "/path/to/anchor_vault",
        "ANCHOR_CHAT_DB_PATH": "/path/to/data/chat.db",
        "ANCHOR_SEARCH_TOOL_MODE": "on_demand"
      }
    }
  }
}
```

### 5.4 作为 Python 库直接嵌入现有项目
如果不需要跑 MCP 独立进程，可以直接在你的 Python 对话服务中导入对应模块：

```python
from anchor.working_memory.service import WorkingMemoryService
from anchor.long_term.service import LongTermMemoryService
from anchor.bridge.context_injector import AnchorContextInjector

# 初始化
injector = AnchorContextInjector(db_path="./data/anchor_memory.db")

# 每轮对话开始前，获取要注入给模型的系统上下文
context_block = injector.build_context_block(
    user_input="今天感觉有点着凉发烧了",
    top_k=4
)
# 将 context_block 直接加入到你的 System Prompt 中
```

---

## 6. 配置项说明 (Environment Variables)

所有配置均支持环境变量注入，保持代码与数据的完全解耦：

| 环境变量名 | 默认值 | 作用描述 |
|---|---|---|
| `ANCHOR_DB_PATH` | `./data/anchor_memory.db` | SQLite 数据库文件绝对路径 |
| `ANCHOR_VAULT_PATH` | `./anchor_vault` | Obsidian Markdown 镜像存储目录 |
| `ANCHOR_CHAT_DB_PATH` | `./data/chat.db` | 用于聊天记录检索与复盘的历史消息库路径 |
| `ANCHOR_SEARCH_TOOL_MODE` | `on_demand` | 搜索工具暴露策略：`always` \| `never` \| `on_demand` |
| `ANCHOR_WM_BUFFER_DAYS` | `2` | 前额叶过期事项安全缓冲池保留天数 |
| `ANCHOR_DECAY_BASE_HALF_LIFE` | `30.0` | 艾宾浩斯衰减基础半衰期（天数） |
| `ANCHOR_CORE_IMPORTANCE_THRESHOLD`| `0.8` | 核心记忆判定阈值（享有防衰减底线） |
| `ANCHOR_COMPANION_NAME` | `companion` | 伴侣在上下文与备注中使用的代称 |
| `ANCHOR_USER_NAME` | `user` | 用户在上下文与备注中使用的代称 |

---

## 7. 本地数据存储与安全说明

- **零数据外发**：所有记忆条目、向量缓存、打烊复盘日志均只在本地 SQLite 及本地文件系统持久化，不上传任何第三方云端。
- **数据更新安全**：后续如果从 GitHub 拉取 Anchor-Memory 的代码更新（`git pull`），由于数据库文件与 Vault 目录默认保存在独立路径或 `.gitignore` 排除目录中，**本地已有的记忆与聊天数据绝不会被覆盖或丢失**。
- **可逆与防误删**：
  - 前额叶具备 2 天缓冲期；
  - 长期记忆支持版本更迭标记（`superseded`），旧事实永不物理丢失；
  - 严禁大模型单方面物理删除长期记忆，保证回忆资产的安全可追溯。

---

## 8. 开源许可 (License)

本项目遵循 [MIT License](LICENSE)。欢迎提交 Issue 与 Pull Request。
EOF