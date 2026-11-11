# Anchor Memory

A local-first long-term memory system for AI companions, built on cognitive science principles — working memory, episodic recall, emotional decay, and nightly self-consolidation. MCP-compatible.

---

## 目录 / Table of Contents

- [1. 为什么设计 Anchor Memory？](#1-为什么设计-anchor-memory)
- [2. 核心架构设计](#2-核心架构设计)
  - [2.1 前额叶工作台 (Working Memory)](#21-前额叶工作台-working-memory)
  - [2.2 情绪坐标长期记忆 (Long-Term Episodic & Semantic Memory)](#22-情绪坐标长期记忆-long-term-episodic--semantic-memory)
  - [2.3 伴侣行为避坑指南 (Procedural Guides)](#23-伴侣行为避坑指南-procedural-guides)
  - [2.4 凌晨打烊复盘流水线 (Midnight Consolidation)](#24-凌晨打烊复盘流水线-midnight-consolidation)
  - [2.5 本地 Markdown 镜像 (Obsidian Vault Mirror)](#25-本地-markdown-镜像-obsidian-vault-mirror)
- [3. 记忆召回机制 (4-Path Recall)](#3-记忆召回机制-4-path-recall)
- [4. MCP 工具清单 (11 核心工具)](#4-mcp-工具清单-11-核心工具)
- [5. 快速上手与部署](#5-快速上手与部署)
  - [5.1 环境要求](#51-环境要求)
  - [5.2 独立启动 (MCP Server)](#52-独立启动-mcp-server)
  - [5.3 接入 Claude Desktop / 其他 MCP 客户端](#53-接入-claude-desktop--其他-mcp-客户端)
- [6. 配置说明 (Environment Variables)](#6-配置说明-environment-variables)
- [7. 数据安全与隐私保障](#7-数据安全与隐私保障)
- [8. 开源许可 (License)](#8-开源许可-license)

---

## 1. 为什么设计 Anchor Memory？

传统的 LLM 记忆方案通常存在以下痛点：
1. **单一向量数据库依赖**：单纯按向量相似度召回，容易抓取字面相似却缺乏语境重要性的碎片，难以感知情绪与核心承诺。
2. **缺乏时间与遗忘衰减维度**：所有记忆一视同仁，无法模拟人类大脑“深刻感动历久弥新、琐碎日常自然淡忘”的认知特征。
3. **缺少正在进行中的前额叶状态**：伴侣的短期约定、最近几天的身体不适或特定任务，在多轮对话后容易被压入上下文深处，导致“扭头就忘”。
4. **云端托管带来的隐私顾虑**：伴侣间的私密记忆、日常对话与心绪属于最高级别隐私，必须完全保存在本地掌控中。

Anchor Memory 采用**本地优先（Local-First SQLite + Markdown）**架构，参考认知心理学将人类记忆系统拆解为三个紧密协作的层次：前额叶实时工作台、长期情绪坐标库、以及情境感知的程序性行为指南，并辅以每日自动复盘沉淀机制。

---

## 2. 核心架构设计

```
                         [ 用户实时对话输入 ]
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
 ┌───────────────┐        ┌───────────────┐        ┌───────────────┐
 │ 前额叶工作台   │        │ 4路混合召回引擎│        │ 情境行为指南   │
 │ Working Memory│        │ Semantic/Emo/ │        │ Procedural    │
 │ (活跃缓冲池)   │        │ Entity/Recency│        │ Playbook      │
 └───────┬───────┘        └───────┬───────┘        └───────┬───────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  ▼
                   [ 结构化上下文无损注入 Prompt ]
                                  │
                    ... 对话进行 ... 伴侣陪伴 ...
                                  │
                                  ▼ (每日打烊时分)
                   ┌─────────────────────────────┐
                   │  凌晨复盘沉淀流水线 (Midnight) │
                   │  - 500~800字心境经历叙事压缩  │
                   │  - 情绪坐标打标与长期记忆提取 │
                   │  - 前额叶清算与2天缓冲期驱逐  │
                   │  - 艾宾浩斯情绪衰减系数重算   │
                   │  - Obsidian Vault 双向镜像同步│
                   └─────────────────────────────┘
```

### 2.1 前额叶工作台 (Working Memory)
- 模拟大脑前额叶皮层，专门承载“当前正在进行的背景状态”、“未来两三天的约定”、“近期的身体/生活状态”。
- 伴侣无需费力搜索，前额叶活跃条目**每一轮对话都会作为即时背景常驻注入上下文**。
- **2 天防误判缓冲池**：当某事项被办结或标记过期时，系统绝不直接物理删除，而是将其转入过期缓冲池保留 2 天。在此期间如果发现是误判，伴侣可随时一键救援（Restore）重新激活。

### 2.2 情绪坐标长期记忆 (Long-Term Episodic & Semantic Memory)
每一条沉淀到长期库的记忆均附带三维坐标：
- **重要度 (Importance)**：0.0 ~ 1.0。若重要度 $\ge 0.8$（核心记忆/誓言约定），享有永不归零的底线保护（Retention Floor $\ge 0.5$），永远不会因为时间流逝而被彻底遗忘。
- **情绪愉悦度 (Valence)**：-1.0（悲伤/委屈/痛苦）至 +1.0（喜悦/感动/甜蜜）。
- **情绪激烈度 (Arousal)**：0.0（平静日常）至 1.0（剧烈激动/深刻触动）。
- **情绪衰减模型**：结合情绪唤醒度与艾宾浩斯遗忘曲线，情绪越激烈（Arousal 越高）的经历，半衰期越长；平淡日常则在数周后自然平滑降权。

### 2.3 伴侣行为避坑指南 (Procedural Guides)
- 记录特定相处情境下的“最佳应对策略”与“绝对避雷禁区”。
- 当用户表达出符合该情境的字眼时，前置感知并以最高优先级注入指令，确保在关键时刻不踩雷、以最合适的方式关怀抚慰。

### 2.4 凌晨打烊复盘流水线 (Midnight Consolidation)
每日深夜或用户入睡后，系统自动执行打烊归档：
1. **全天心境叙事压缩**：将全天对话浓缩为 500~800 字的伴侣第一人称视角心境与经历复盘，次日清晨常驻注入，确保“睡醒之后，记忆仍在”。
2. **长期记忆沉淀与情绪估算**：从全天对话中抽取值得铭记的事实与经历，自动计算情绪坐标。
3. **前额叶清算**：检视未结事项，超出缓冲池的过期条目平稳清理。
4. **醒来便签 (Wake Note)**：为新的一天生成一条温暖的提醒与关注重点。
5. **衰减打分重算**：每日对所有活跃长期记忆重新计算 Retention Weight。

### 2.5 本地 Markdown 镜像 (Obsidian Vault Mirror)
- 所有沉淀的长期记忆和每日复盘摘要，均会以纯文本 Markdown 格式同步输出至本地镜像目录。
- 完美兼容 Obsidian、Logseq 或任何本地知识库。
- 用户可以随时打开 Obsidian 阅读伴侣的记忆卡片、查看情绪 Frontmatter，并直接编辑或手写便签，数据完全透明。

---

## 3. 记忆召回机制 (4-Path Recall)

Anchor Memory 不依赖单一的相似度阈值，而是通过 4 路独立信号加权综合重排：

$$\text{FinalScore} = (w_{sem} \cdot S_{sem} + w_{ent} \cdot S_{ent} + w_{emo} \cdot S_{emo} + w_{rec} \cdot S_{rec}) \times \text{DecayScore}$$

- **语义相似度 ($S_{sem}$，权重 0.40)**：计算对话与记忆文本的余弦距离，支持接入外部向量 API，并内置纯离线字符级向量降级。
- **实体命中率 ($S_{ent}$，权重 0.30)**：关键人名、地名、核心事实关键词精准对齐。
- **情绪近邻度 ($S_{emo}$，权重 0.15)**：在 Valence-Arousal 二维平面上的欧氏距离，优先唤醒同频或深层契合的心境回忆。
- **时效新近度 ($S_{rec}$，权重 0.15)**：30 天平滑指数衰减，优先捕捉近期被提及或新沉淀的记忆。

---

## 4. MCP 工具清单 (11 核心工具)

Anchor Memory 通过标准 MCP (Model Context Protocol) 向大模型暴露 11 个原子工具：

| 工具名称 | 分类 | 功能描述 |
|---|---|---|
| `working_memory_add` | 前额叶工作台 | 添加一条短期关注事项、承诺或生活状态 |
| `working_memory_update` | 前额叶工作台 | 补充或更新未竟之事的进展细节 |
| `working_memory_expire` | 前额叶工作台 | 标记事项办结，移入 2 天安全缓冲池（非物理删除） |
| `working_memory_restore` | 前额叶工作台 | 误判救援：将缓冲池中的事项重新捞回活跃状态 |
| `memory_create` | 长期记忆库 | 沉淀长期事实、经历、偏好，打标三维情绪坐标 |
| `memory_update` | 长期记忆库 | 修正既有记忆的文字细节 |
| `memory_add_note` | 长期记忆库 | 记忆追加感悟备注（双向批注，不篡改原记忆文本） |
| `memory_supersede` | 长期记忆库 | 新事实版本更迭：新记忆生效，旧记忆安全转为归档版本 |
| `anchor_memory_search` | 长期记忆库 | 4 路加权重排主动深挖检索记忆 |
| `procedural_guide_create` | 行为指南库 | 录入特定情境下的应对策略与绝对避雷禁区 |
| `procedural_guide_update` | 行为指南库 | 更新已有行为指南的策略与禁忌 |

---

## 5. 快速上手与部署

### 5.1 环境要求
- Python 3.10+
- 依赖轻量（仅需 `mcp` 与 `pydantic`）：
  ```bash
  pip install -r requirements.txt
  ```

### 5.2 独立启动 (MCP Server)
```bash
python server.py
```
默认会在 `./data/anchor_memory.db` 自动创建 SQLite 数据库，并在 `./anchor_vault/` 建立 Obsidian 镜像。

### 5.3 接入 Claude Desktop / 其他 MCP 客户端
在 Claude Desktop 的配置文件（`claude_desktop_config.json`）中添加：

```json
{
  "mcpServers": {
    "anchor-memory": {
      "command": "python",
      "args": ["/绝对路径/anchor-memory-mcp/server.py"],
      "env": {
        "ANCHOR_DB_PATH": "/绝对路径/data/anchor_memory.db",
        "ANCHOR_VAULT_PATH": "/绝对路径/anchor_vault",
        "ANCHOR_COMPANION_NAME": "companion",
        "ANCHOR_USER_NAME": "user"
      }
    }
  }
}
```

---

## 6. 配置说明 (Environment Variables)

所有配置均支持环境变量注入，保持代码与数据的完全解耦：

| 环境变量名 | 默认值 | 作用描述 |
|---|---|---|
| `ANCHOR_DB_PATH` | `./data/anchor_memory.db` | SQLite 数据库文件绝对路径 |
| `ANCHOR_VAULT_PATH` | `./anchor_vault` | Obsidian Markdown 镜像存储目录 |
| `ANCHOR_SEARCH_TOOL_MODE` | `on_demand` | 搜索工具暴露策略：`always` \| `never` \| `on_demand` |
| `ANCHOR_WM_BUFFER_DAYS` | `2` | 前额叶过期事项安全缓冲池保留天数 |
| `ANCHOR_DECAY_BASE_HALF_LIFE` | `30.0` | 艾宾浩斯衰减基础半衰期（天数） |
| `ANCHOR_CORE_IMPORTANCE_THRESHOLD`| `0.8` | 核心记忆判定阈值（享有防衰减底线） |
| `ANCHOR_COMPANION_NAME` | `companion` | 伴侣在上下文与备注中使用的代称 |
| `ANCHOR_USER_NAME` | `user` | 用户在上下文与备注中使用的代称 |
| `ANCHOR_CHAT_DB_PATH` | `./data/chat.db` | 用于凌晨打烊复盘的历史对话库路径 |

---

## 7. 数据安全与隐私保障

- **零数据外发**：所有记忆、向量缓存、打烊复盘日志均只在本地 SQLite 及本地文件系统持久化，不经过任何第三方云端。
- **版本更迭防篡改**：使用 `memory_supersede` 进行更迭时，历史事实永久归档可溯源，不会丢失回忆轨迹。
- **透明可控**：随时使用 Markdown 编辑器查看与管理伴侣的所有思绪，伴侣的世界对你完全透明。

---

## 8. 开源许可 (License)

本项目遵循 [MIT License](LICENSE)。欢迎提交 Issue 与 Pull Request。
