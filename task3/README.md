# Task3：任务规划与分解——让 Agent 先规划再执行（ch04）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程
> [ch04 任务规划与分解](https://datawhalechina.github.io/deepagents-in-action/chapters/ch04-task-planning/)。
> 完整引用清单见[仓库根 README](../README.md#引用与致谢)。
>
> - 课程教程：<https://datawhalechina.github.io/deepagents-in-action/>
> - B站视频：《Deep Agents 实战》 <https://space.bilibili.com/28357052/lists/7757577?type=season>
> - 课程仓库：<https://github.com/datawhalechina/deepagents-in-action>

## 目录

- [任务规划与分解.png](./任务规划与分解.png) — 本章思维导图（手绘笔记）
- [code/planning_agent.py](./code/planning_agent.py) — 显式启用 `TodoListMiddleware`，完成"规划 → 执行 → 更新状态 → 产出报告"
- [code/planning_persistence.py](./code/planning_persistence.py) — `todos` 的持久化对照实验（同一 thread 接续 / 新 thread 隔离 / 无 Checkpointer 不接续）
- [NOTES.md](./NOTES.md) — 本章深度笔记（中间件机制、状态结构、职责边界）

> 思维导图注记：图中 `TodoListMiddleware` 分支把 `create_deep_agent()` 标为
> "预设好的最佳组合"，容易读成"它已包含任务规划"。**v0.7 的预设组合不含
> `TodoListMiddleware`**——预装的是文件系统、摘要、PatchToolCalls 等；任务规划
> 必须通过 `middleware=[TodoListMiddleware()]` 显式加入。`create_agent() + middleware=[...]`
> 是手动组合路径，`create_deep_agent()` 是预设组合路径，两者都**不会自动**带规划。

## 本章核心一句话

`write_todos` 不是"待办清单 UI"，而是**把计划从模型的上下文里搬进 State**：
即使后续对话被总结压缩，`todos` 字段也不会被删除，Agent 靠它保持主线。

## 打卡：统一要求五项

### 1. 验证什么

1. v0.7 默认不装 `TodoListMiddleware`，显式加入后 Agent 才拥有 `write_todos` 工具与 `todos` 状态；
2. 一个多步任务里，Agent 是否真的"先规划、再逐步执行、每步更新状态"；
3. `todos` 的持久化边界：同 thread 接续、跨 thread 隔离、无 Checkpointer 不接续。

### 2. 改了什么

1. 任务刻意设计成**确定性三步**（查三城天气 → 算平均 → 写报告），工具返回固定值，
   便于核对 Agent 是否真的用了工具结果而不是自己编；
2. 系统提示词强制"先 `write_todos`、每步 in_progress/completed、结论不与 write_todos 同轮"，
   把课程里"可用工作方式"显式化为可验证的约束；
3. 脚本打印三类证据：`write_todos` 的每次全量更新、最终 `todos`、`state['files']` 里的产物；
4. 第二个脚本用 `InMemorySaver` 做 A/B/C 三组持久化对照。

### 3. 实际结果

**规划执行**（`planning_agent.py`）：

- Agent 首轮 `write_todos` 拆出 5 项，全部 `pending`；
- 连续 3 次 `get_weather` 后，一次性把三项查询置为 `completed`、计算步骤置 `in_progress`；
- 调用 `average_temperature([12, 18, 25])` 得 `18.3`，再更新状态、`write_file` 写报告、最后全部 `completed`；
- 最终 `todos` 5 项全部 completed；产物 `/weather_report.md` 在 `state['files']` 中，
  内容含三城表格与"平均气温 18.3℃"。

**持久化对照**（`planning_persistence.py`）：

| 场景 | 结果 |
|---|---|
| A. 同一 `thread_id` 二次 invoke | 4 项计划仍在（未从零重规划） |
| B. 新 `thread_id` | `todos == []`（线程隔离） |
| C. 无 Checkpointer | 无可恢复状态，第二次 invoke 只能重新规划（首次运行时遇 429 免费额度限流，脚本已加容错跳过，不影响 A/B 结论） |

### 4. 证据与解释

- 证据：脚本打印的 `write_todos` 全量参数（可看到每次都是**整份列表**覆盖，而不是"改一项"）、
  最终 `todos`、`state['files']` 中的报告全文；
- 解释：
  - `write_todos` 的入参是 `todos: list[Todo]`，每次调用**替换整份清单**，所以模型必须
    把已完成项一并带上，这也是它每次输出都很长的原因；
  - `todos` 与 `messages` 分开存放，后续对话被总结时不会丢失，因此能起到"锚定主线"的作用；
  - 跨 invoke 接续的三个条件：`TodoListMiddleware` + **Checkpointer** + **同一 `thread_id`**，
    缺一不可；`InMemorySaver` 只在进程内有效，进程重启需持久化 saver。

### 5. 下一步修正

1. 本次 `write_todos` 第一次就把"制定计划"本身也当成了一个 todo，属于模型的过度规划；
   真实项目可在 `system_prompt` 里明确"不要把更新计划本身列为任务"（research 项目的
   COURSE.md 就是这么约束的）；
2. `completed` 只代表模型自述，本练习靠人工核对报告内容；下一步应加**产物校验**
   （报告是否存在、平均温度是否等于 18.3、三城是否齐全），而不是只看清单；
3. 目前是单 Agent；下一步验证 ch04 第 5 条结论——子 Agent **不继承**主 Agent 的
   `TodoListMiddleware`，需要在 subagent spec 里单独开启；
4. 换弱模型复跑，观察是否出现"漏步骤 / 重复搜索 / 半途而废"，对照本章列出的四种失败症状。

## 运行方式

```bash
cd /mnt/d/study/deepagents-in-action/research_deepagent
uv run --frozen python ../notes/task3/code/planning_agent.py
uv run --frozen python ../notes/task3/code/planning_persistence.py
```
