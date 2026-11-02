# Task8：可复现教学 Agent——把 teach skill 升级为 DeepAgents 图（ch01–09 + ch13 综合）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程（ch01–ch09 基础能力 + ch13 评分量规），
> 结合本仓库 `teach-agent/` 的工程落地。完整引用清单见[notes/README.md](../README.md#引用与致谢)。

## 目录

本文件夹自包含本次任务的实现流程、代码与思维导图（可运行副本在 `code/`）：

- [README.md](README.md) — 本文件：实现流程、五项打卡、机制解释与错题记录
- [code/teach_agent.py](code/teach_agent.py) — 组装图：`build_teach_agent()` 一次性接入 4 项能力 + `record_mistake` + `run_rubric_demo()`
- [code/verify_teach_agent.py](code/verify_teach_agent.py) — 零 token 验证 5 项能力；检测到 key 时跑真实评分闭环
- [code/SKILL.md](code/SKILL.md) — teach 技能本体（能力①的单一信息源）
- [code/learner.md](code/learner.md) — 长期记忆种子文件（能力②，`record_mistake` 追加于此）
- [mindmap.py](mindmap.py) / [教学Agent升级.png](教学Agent升级.png) — 任务视角思维导图（四能力同图 · 升级点 · 时序）
- [outputs/verify_output.log](outputs/verify_output.log) — 真实运行日志（5 项能力断言 + 真实评分闭环）

> 权威源码在本地目录 `teach-agent/`（不在本 GitHub 仓库内）：
> `teach_agent.py` · `verify_teach_agent.py` · `SKILL.md` · `learner.md` · `教学Agent.png`（架构视角思维导图）。
> `code/` 内为本次任务的快照副本，以本地 `teach-agent/` 为准。

## 本章核心一句话

**teach 本身就是一个 Skill；长期记忆记错题/偏好（可由 `record_mistake` 自动追加）；生成教学页后 HITL 暂停等你审批；Rubric 用真实评分模型验收产出——四件事在同一张 `create_deep_agent` 图里正交共存。**

## 打卡：统一要求五项

### 1. 验证什么

| 能力 | 命题 | 断言 |
|---|---|---|
| ① Skills | teach 索引进 system prompt、正文埋点不预加载 | 2 |
| ② Memory | learner.md 全文埋点注入；HTML 注释被剥除 | 2 |
| ③ HITL | publish_page 触发中断；approve 执行、reject 不执行 | 3 |
| ④ Rubric | 4 能力同图组装 + 证据工具单测；★ 真实评分模型跑通端到端闭环 | 3+真实 |
| ⑤ record_mistake | 工具把错题追加进 learner.md；Agent 对话中自动调用 | 2 |

### 2. 改了什么

1. **用"能力图"替代"4 个 Agent 串起来"**：`build_teach_agent()` 把 skills / memory / tools / interrupt_on / middleware 作为 `create_deep_agent` 的独立配置项一次性接入，四项能力天然共存，没有手写编排。
2. **learner.md 从静态文件升级为 `record_mistake` 工具（能力②升级）**：新增 `@tool record_mistake(original, choice, misunderstanding, correct, source_ref)`，把一条错题结构化追加进 learner.md 的「## 错题」段；写路径由 `LEARNER_MD_PATH` 控制，测试可覆盖为临时副本避免污染种子记忆。工作模型在对话中发现学习者做错就主动调用它，下一次 thread 起号时该错题已注入 system prompt。
3. **接真实评分模型跑端到端 Rubric 闭环（能力④升级）**：`RubricMiddleware(model=grader, tools=[check_lesson_structure], max_iterations=, on_evaluation=)`，`TEACH_RUBRIC` 作为评分标准通过 `invoke` 的 `"rubric"` 字段注入；`run_rubric_demo()` 用 `.env` 的 `OPENAI_API_KEY/OPENAI_API_BASE/AGENTSEEK_MODEL` 构造 `ChatOpenAI`（与 `rubric_loop.py` 同款）。
4. **端到端闭环必须 `hitl=False`**：评分在工作模型**自然停止后**才启动，HITL 中断会挡住它，所以演示关掉 `publish_page` 中断。
5. **两处 `tools` 不通用**：`RubricMiddleware(tools=...)` 只给评分模型取证；`create_deep_agent(tools=[...])` 是工作模型的工具箱（含 `record_mistake` / `publish_page`）。

### 3. 实际结果

**零 token 探针**（`verify_teach_agent.py` 前 4 能力 + 能力⑤）

```
=== 能力5：record_mistake 写入长期记忆 ===
工具返回: 已记录错题 LM-20261102-210045 到长期记忆 learner.md。
是否追加了 LM- 开头的错题: True
[1/2] record_mistake 把错题结构化追加进 learner.md（埋点仍在，证明插入在错题段）
[2/2] Agent 在对话中调用 record_mistake 自动追加错题到 learner.md
```

**真实评分模型闭环**（检测到 `.env` key 时自动跑，`deepagents 0.7.8`，模型 `agnes-3.0-flash`）

```
=== 能力4：真实评分模型端到端 Rubric 闭环 ===
[真实] 评审轮数: 2
  iter 0: needs_revision  gaps=['通过 check_lesson_structure 取证且 ok=true', '收尾包含『面试官追问』与可背的 90 秒答案', '若发现学习者有错误理解，必须调用 record_mistake 写入长期记忆']
  iter 1: satisfied  gaps=[]
[真实] 最终结论: satisfied
[1/1] 能力4：真实评分模型已跑通端到端 Rubric 闭环（check_lesson_structure 取证 + 验收）
```

完整存档日志见 [outputs/verify_output.log](outputs/verify_output.log)。评分器先 `check_lesson_structure` 取证 → `needs_revision`（3 条 gap 写回）→ 工作模型按 gap 修订 → `satisfied` 放行。此前另一次运行曾因两轮未补齐 gap 以 `max_iterations_reached` 收场——同样不放行。两种结局印证同一条机制：**fail-closed，非 `satisfied` 一律拒绝**；课程要点：**satisfied ≠ 正确，Rubric 漏写就不会查**。

### 4. 证据与解释

- **四能力正交**：skills（方法论）、memory（错题/偏好）、HITL（人审）、Rubric（验收）都是 `create_deep_agent` 的独立配置，互不打架。
- **RubricMiddleware 激活条件**：必须在 `invoke` 的 state 里带 `"rubric"` 字段，否则它整体 no-op。
- **评分时序**：`after_agent` 在工作模型**自然停止后**才启动评分；这是端到端闭环要 `hitl=False` 的根本原因。
- **`on_evaluation` 回调**：收 `RubricEvaluation`：`{iteration, result, criteria, explanation}`；异常会被吞掉只记日志，不能当控制钩子。
- **`record_mistake` 写文件的坑**：`@tool` 函数返回字符串时 `.invoke()` 直接给字符串（不是 dict）；返回 dict 的工具（如 `check_lesson_structure`）才给 `{ok, failures}`。
- **长期记忆的快照与跨 thread**：learner.md 全文每轮注入；同 thread 走快照不重扫；写入后新 thread 起号会重加载到 system prompt。
- **fail-closed 验收**：最终结果只有 `satisfied` 放行，其余四种 (`needs_revision` / `failed` / `grader_error` / `max_iterations_reached`) 一律拒绝。

### 5. 下一步修正

1. **弱/强 Rubric 对照**：仿 `rubric_loop.py` 做"弱 Rubric（只查结构）/ 强 Rubric（再查面试追问质量）"，复现 `satisfied ≠ 正确`。
2. **record_mistake 落盘位置**：当前追加到 `learner.md`，可改为独立 `learner_mistakes.md` 并在 `memory` 并列加载，保持种子记忆干净。
3. **HITL 接真实前端**：`edit` 决策目前只验证不执行；接前端做"改完再发"。
4. **沙箱化证据工具**：`check_lesson_structure` 当前是纯字符串检查，可升级为调用真实运行/单测的取证。

## 错题记录

| # | 原题 | 当时的选择 | 错误理解 | 正确机制 |
|---|---|---|---|---|
| 1 | 4 项能力能否同图 | 以为要拆成 4 个 Agent 串起来 | 以为要手写编排 | 都是 `create_deep_agent` 的独立配置项，正交可共存 |
| 2 | RubricMiddleware 何时评分 | 以为 publish_page 一调用评分就介入 | 没注意它是 after_agent | 评分在工作模型自然停止后才启动；端到端闭环要 `hitl=False` |
| 3 | RubricMiddleware 激活 | 以为建了中间件就会评分 | 漏了 `rubric` 注入 | 必须 `invoke` 带 `"rubric"` 字段，否则 no-op |
| 4 | `on_evaluation` 回调 | 以为能拿到每轮评审 | 没意识到格式 | 收 `RubricEvaluation`：`{iteration, result, criteria, explanation}` |

## 运行方式

```bash
cd d:\study\deepagents-in-action\research_deepagent

# 1) 先确保 .venv 可用（当前 .venv 已损坏：只剩坏 lib64 符号链接）
Remove-Item .venv\lib64 -Force
uv sync --frozen

# 2) 零 token 验证 5 项能力（不需要 .env / 网络；但若 .env 有 key 会自动跑真实评分闭环）
uv run --frozen python ../teach-agent/verify_teach_agent.py

# 3) 组装冒烟测试
uv run --frozen python ../teach-agent/teach_agent.py

# 4) 单独跑端到端真实评分模型 Rubric 闭环（需要 .env 的 OPENAI_API_KEY 等）
uv run --frozen python ../teach-agent/teach_agent.py --rubric
```

> 说明：`research_deepagent/` 是本仓库的本地研究目录（含 `.venv`、`.env` 与前端源码），不随学习仓库上传；上面命令假设你已在该目录准备好 uv 环境。
