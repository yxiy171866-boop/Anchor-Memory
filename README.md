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
- [3. MCP 工具体系全览 (14 核心工具)](#3-mcp-工具体系全览-14-核心工具)
  - [3.1 工作记忆类工具 (5 个)](#31-工作记忆类工具-5-个)
  - [3.2 长期记忆类工具 (5 个)](#32-长期记忆类工具-5-个)
  - [3.3 历史聊天记录检索工具 (1 个)](#33-历史聊天记录检索工具-1-个)
  - [3.4 行为指南类工具 (3 个)](#34-行为指南类工具-3-个)
- [4. 前端设置面板 (Frontend Web UI & API)](#4-前端设置面板-frontend-web-ui--api)
  - [4.1 前端功能模块说明](#41-前端功能模块说明)
  - [4.2 前端服务启动与 API 对接](#42-前端服务启动与-api-对接)
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
 │ Working Memory  │       │ (语义/中文实体/ │       │ Procedural      │
 │ (活跃未竟状态)  │       │  情绪/新近度)   │       │ Playbook        │
 └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    ▼
                     [ 结构化上下文安全注入 Prompt ]
                                    │
                               [ 智能体交互 ]
                                    │
                                    ▼ (每日复盘周期)
                     ┌───────────────────────────────┐
                     │     每日复盘流水线 (Midnight)   │
                     │  - 全天心境经历长文叙事压缩    │
                     │  - 情绪坐标计算与溯源记忆抽取  │
                     │  - 前额叶审计与安全归档        │
                     │  - 艾宾浩斯情绪半衰期衰减重算  │
                     │  - 本地 Markdown 保留用户笔记同步│
                     └───────────────────────────────┘
```

### 1.2 前额叶工作台 (Working Memory / 未竟之事)
- **定位**：模拟大脑前额叶皮层，专门承载“当前阶段持续需要关注的短期背景状态”（如近期身体状况、正在推进中的事项、承诺与待办）。
- **常驻注入**：前额叶中所有处于 `active` 状态的事项，**无需搜索，每轮对话都会作为背景常驻注入 Prompt**，保证模型永远对近期的关键状态保持清晰认知。
- **2 天防误判缓冲池与零物理删除**：
  - 当某事项办结时，调用 `working_memory_expire` 必须提供**精确 ID**（若 ID 错误会返回活跃条目候选列表供确认，禁止模糊匹配误伤）；
  - 事项转入 `expired` 缓冲池保留 2 天。若属误判，可随时调用 `working_memory_restore` 恢复；
  - 缓冲期结束后，系统将其转入 `archived`（历史归档）状态，**严禁物理硬删除 (Hard DELETE)**，数据永久安全留存。

### 1.3 长期记忆库与情绪半衰期衰减 (Long-Term Memory)
每一条沉淀到长期库的记忆均附带三维物理情绪坐标与溯源信息：
- **重要度 (Importance)**：0.0 ~ 1.0（支持合法的 0.0）。若重要度 $\ge 0.8$ 或标记了 `is_protected = 1`，享有底线保护（Retention Floor $\ge 0.5$），永远不会因为时间推移而彻底归零。
- **核心记忆保护机制 (`is_protected`)**：对于重要身份、核心约定打上硬保护标，底层拒绝任何自动 supersede 或降级操作。
- **情绪愉悦度 (Valence)**：-1.0（负向情绪/委屈/痛苦）至 +1.0（正向情绪/喜悦/感动）。
- **情绪激烈度 (Arousal)**：0.0（平静日常）至 1.0（剧烈激动/深刻触动）。
- **真实半衰期衰减公式**：结合情绪唤醒度与放射性/遗忘半衰期定律：
  $$T_{1/2} = \text{base\_half\_life} \times (1 + \text{arousal} \times k)$$
  $$\text{EffectiveWeight} = \text{importance} \times 2^{-\frac{\text{days}}{T_{1/2}}} = \text{importance} \times e^{-\frac{\text{days} \cdot \ln 2}{T_{1/2}}}$$
  日常琐碎在数周后自然平滑降权，重要记忆长期保持活跃。衰减仅调整检索召回时的排序打分，原始记忆数据在本地永久保留。

### 1.4 程序性行为指南 (Procedural Guides)
- **定位**：记录特定相处情境下的“建议执行策略”与“绝对避雷禁区”。
- **前置匹配**：基于情境关键词与置信度算法，在用户输入契合特定情境时，以最高优先级注入到上下文顶层，引导模型输出符合预期的反应。

### 1.5 每日复盘与对话压缩机制 (Consolidation Pipeline)
每日深夜或对话空闲阶段，系统可自动或手动执行复盘流水线：
1. **全天心境叙事压缩**：将全天分散的聊天记录归纳为一段 500~800 字的第一人称心境与经历长文叙事，第二天唤醒时作为昨日背景注入，保持对话的连续感。
2. **长期记忆抽取与来源追溯 (Provenance)**：从对话中抽取的每条记忆均记录 `source_message_id`、`source_date` 与 `confidence`，支持追溯原始聊天出处。
3. **前额叶清算**：自动检查超时活跃事项，超出缓冲池的过期条目安全移入 `archived` 归档。
4. **醒来便签 (Wake Note)**：生成一份精炼的晨间关注点备忘录，次日清晨优先注入。
5. **衰减打分单事务重算**：每日对所有长期记忆在一个 SQLite 事务内原子重算，效率高且安全。

### 1.6 本地 Markdown 镜像 (Obsidian Vault Mirror)
- 所有沉淀的长期记忆和每日复盘摘要，均会以纯文本 Markdown 格式输出至本地镜像目录。
- **用户手写笔记保护**：增量同步时自动检测文件中的 `## Notes` 区域，**绝不覆盖用户在 Obsidian 里手动追加的批注和手写内容**。
- 采用规范的 YAML Frontmatter，兼容 Obsidian、Logseq 等本地双链笔记工具。

---

## 2. 记忆召回引擎 (4-Path Recall)

Anchor Memory 采用 4 路独立信号加权综合重排算法，全面平衡语义契合与情感关联：

$$\text{CompositeScore} = w_{sem} \cdot S_{sem} + w_{ent} \cdot S_{ent} + w_{emo} \cdot S_{emo} + w_{rec} \cdot S_{rec}$$
$$\text{FinalScore} = \text{CompositeScore} \times \text{DecayScore}$$

- **语义相似度 ($S_{sem}$，权重 0.40)**：计算输入与记忆文本的向量余弦距离。支持配置外部 Embedding API，并在无外网时自动降级到本地字符级向量算法（缓存表自带模型与维度校验，防止混维）。
- **中文与英文实体命中率 ($S_{ent}$，权重 0.30)**：集成成熟的中文 2/3/4-gram 分词器与停用词过滤，中英文混排对话均能实现精准的实体片段交集匹配。
- **情绪近邻度 ($S_{emo}$，权重 0.15)**：在 Valence-Arousal 二维平面上的欧氏空间距离，优先唤醒同频心境的经历。
- **时效新近度 ($S_{rec}$，权重 0.15)**：基于 `last_accessed_at` 的访问热度给予短期唤醒加权，不与长期的自然遗忘曲线发生双重惩罚。
- **门槛解耦**：0.35 门槛仅卡 CompositeScore（过滤无关噪音），排序由 FinalScore 负责，避免较早但重要的记忆被强行过滤。

---

## 3. MCP 工具体系全览 (14 核心工具)

系统通过标准 MCP 协议向大语言模型暴露 14 个原子工具：

### 3.1 工作记忆类工具 (5 个)
- **`working_memory_list`**：列出当前前额叶所有活跃事项及其具体 ID 与类别（让模型直观感知当前进行中状态）。
- **`working_memory_add`**：添加一条当前这几天需要持续关注的短期状态、承诺或未竟事项。
- **`working_memory_update`**：更新既有未竟事项的进展细节或补充最新动态。
- **`working_memory_expire`**：将办结事项标记为过期并移入 2 天缓冲池（要求精确 ID，输入错误返回候选项）。
- **`working_memory_restore`**：误判救援：将处于过期缓冲池中的事项重新捞回为活跃关注状态。

### 3.2 长期记忆类工具 (5 个)
- **`memory_create`**：沉淀具备长期留存价值的生活经历、身份事实、伴侣偏好或核心承诺（支持 `is_protected` 硬保护）。
- **`memory_update`**：修正或更正既有长期记忆的文字细节。
- **`memory_add_note`**：记忆双向追加备注：为已有记忆挂载后续心境、进展或感受补充，不破坏原记忆文本。
- **`memory_supersede`**：新事实更迭：用新记忆取代旧记忆，旧记忆自动打标为 superseded 历史版本存留（受保护记忆禁止误更迭）。
- **`anchor_memory_search`**：按需主动深度检索长期记忆库（4 路加权重排）。

### 3.3 历史聊天记录检索工具 (1 个)
- **`search_conversation`**：根据关键词、语义以及具体日期范围检索历史聊天记录。
  - 参数：`query`, `scope` ('recent' | '7d' | '30d' | '90d' | 'all'), `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD), `limit` (默认 6，最多 20)。

### 3.4 行为指南类工具 (3 个)
- **`procedural_guide_list`**：列出当前已注册的所有行为指南清单与触发情境。
- **`procedural_guide_create`**：录入特定情境下的最佳应对策略与绝对避雷禁区。
- **`procedural_guide_update`**：微调或完善已有行为指南的策略与禁忌。

---

## 4. 前端设置面板 (Frontend Web UI & API)

本项目在 `frontend/` 目录提供了完整的设置 UI 与轻量级后端 HTTP API 服务。

### 4.1 前端功能模块说明
1. **睡前对话余温衔接 (Bedtime Tail Bridge)**：控制次日唤醒是否拼接睡前对话片段，支持按轮数或 Token 预算截取。
2. **单日滚动对话压缩 (Daily Rolling Summary)**：随时触发长对话滚动压缩，释放窗口空间。
3. **老记忆情绪增量补齐 (Backfill)**：针对历史导入数据自动安全平滑补全情绪坐标。
4. **记忆主动搜索工具模式 (Search Tool Mode)**：`on_demand` (推荐) \| `always` \| `never`。
5. **低权重沉底记忆管理 (Decay Archive)**：查看沉底记忆并支持手动确认归档。

### 4.2 前端服务启动与 API 对接
启动自带的设置面板服务：
```bash
python frontend/server.py --port 8765
```
然后在浏览器访问 `http://localhost:8765` 即可实时查看并保存各项系统参数，所有修改即时持久化到 SQLite 的 `anchor_settings` 表中。

---

## 5. 快速部署与接入指南

### 5.1 环境要求与依赖安装
- Python 3.10+
- 运行依赖库安装：
  ```bash
  git clone https://github.com/yxiy171866-boop/Anchor-Memory.git
  cd Anchor-Memory
  pip install -r requirements.txt
  ```

### 5.2 运行自动化测试套件
在提交或部署前，可运行测试套件验证中文分词、衰减公式与防删除特性：
```bash
python -m unittest discover -s tests -v
```

### 5.3 独立启动 MCP 服务
```bash
python server.py
```
默认会在 `./data/anchor_memory.db` 自动初始化开启了 WAL 模式与外键约束的 SQLite 数据库。

### 5.4 接入 Claude Desktop 或其他 MCP 客户端
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

### 5.5 作为 Python 库直接嵌入现有项目
如果系统本身已有成熟的调度后端，可以直接导入作为底座引擎使用：

```python
from anchor.bridge.context_injector import AnchorContextInjector

# 初始化注入器
injector = AnchorContextInjector(db_path="./data/anchor_memory.db")

# 每轮对话开始前，获取要注入给模型的系统上下文（包含防投毒隔离标记）
context_block = injector.build_context_block(
    user_input="今天感觉有点着凉发烧了",
    top_k=4
)
# 直接拼入 System Prompt
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
- **全面取消物理删除**：前额叶过期缓冲满后自动转为 `archived` 状态；长期记忆仅做状态更迭标记，回忆资产永久可溯。
- **防提示注入与投毒**：注入上下文首尾打上了安全数据标记，明确区分背景数据与可执行系统指令。

---

## 8. 开源许可 (License)

本项目遵循 [MIT License](LICENSE)。欢迎提交 Issue 与 Pull Request。
