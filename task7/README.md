# Task7：评分量规——让 Agent 按验收标准自我迭代（ch13）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程
> [ch13 Grading Rubrics](https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/)。
> 完整引用清单见[仓库根 README](../README.md#引用与致谢)。

## 目录

- [评分量规.png](./评分量规.png) — 本章思维导图（代码渲染）
- [code/rubric_evidence.py](./code/rubric_evidence.py) — 证据工具：测试能抓"崩溃 / 顺序错 / 改输入"（4 断言，零 token）
- [code/rubric_gate.py](./code/rubric_gate.py) — fail-closed 验收门：五种结果 + `unverified` 判定（3 断言，零 token）
- [code/rubric_task_vs_rubric.py](./code/rubric_task_vs_rubric.py) — TASK 与 RUBRIC 是两份文件（3 断言，零 token）
- [code/rubric_loop.py](./code/rubric_loop.py) — 真实模型的弱/强 Rubric 对照（含限流处理说明）
- [outputs/](./outputs/) — 三份零 token 实验日志
- [mindmap.py](./mindmap.py) — 导图生成脚本

## 本章核心一句话

**"生成结束"是运行事件，"通过验收"才是业务结论；而验收的可信度，取决于 Rubric 写了什么、证据工具能证明什么。**
`RubricMiddleware` 在工作模型自然停止后启动评分，只有 `satisfied` 才放行——其余四种结果一律拒绝（fail-closed）。

## 打卡：统一要求五项

### 1. 验证什么

| 脚本 | 命题 | 断言 |
|---|---|---|
| `rubric_evidence.py` | 测试能抓三类问题：崩溃、语义顺序错、修改输入 | 4 |
| `rubric_gate.py` | 除 `satisfied` 外全部拒绝；`bool(messages)` 是错误门 | 3 |
| `rubric_task_vs_rubric.py` | 格式要求写在 TASK 里，评分模型看不到；必须写进 RUBRIC | 3 |
| `rubric_loop.py` | 真实模型下，弱 Rubric 会放过格式问题（`satisfied` ≠ 正确） | 实测记录 |

### 2. 改了什么

1. **把"评分"拆成可独立验证的三层**：证据工具（纯函数）、验收门（纯函数）、闭环（真实模型）。
   前两层零 token、可在 CI 里跑；只有第三层需要模型。
2. **用真实翻车当主线**：先用真实模型跑弱 Rubric，拿到"`satisfied` 但回答带说明文字和围栏"的证据，
   再回头解释"为什么叫 Rubric 漏写"。
3. **把"两份文件"做成可运行检查**：`rubric_task_vs_rubric.py` 逐条统计 TASK / WEAK / STRONG 的条目数与格式关键词，
   避免停留在口头区分。
4. **给验收门写反例**：不只验证"正确写法通过"，还验证 `bool(messages)` 会在 `needs_revision` 时误放行。
5. **测试沙箱补齐常用 builtins**：第一版漏了 `Exception`，导致合法候选代码被误判为异常；
   这个坑本身说明"证据工具也可能骗你"。

### 3. 实际结果

**证据工具**（`outputs/rubric_evidence.log`）

```
set 实现      → {'ok': False, 'failures': ["test_unhashable: TypeError: unhashable type: 'list'"]}
排序去重      → {'ok': False, 'failures': ['test_basic: expected [2, 1], got [1, 2]']}
列表+相等比较 → {'ok': True, 'failures': []}
修改输入      → failures 含 "input was mutated"
```

**验收门**（`outputs/rubric_gate.log`）

```
无评审 / needs_revision / max_iterations_reached / failed / grader_error / unverified → accepted=False
satisfied（未被降级）→ accepted=True
反例：bool(messages)=True 但评审是 needs_revision → 误放行
```

**两份文件**（`outputs/rubric_task_vs_rubric.log`）

```
TASK            条目数=0   命中格式要求=['only executable python source code']
WEAK_RUBRIC     条目数=7   命中格式要求=无
STRONG_RUBRIC   条目数=9   命中格式要求=['no prose', 'markdown fence', 'parse as valid python']
```

**真实模型闭环**（弱 Rubric）

```
[weak] iteration 0: needs_revision   ← 指出 unhashable 等 gap
[weak] iteration 1: satisfied
最终回答开头：'The implementation has been revised. The key changes:\n\n1. **...'
accepted: True
```

→ 评分通过，但回答违反"只返回可执行代码"。**直接原因是 Rubric 没有格式标准。**
强 Rubric 一阶段遇到网关限流 `429 max connections reached: 450`，尚未复现，已列入下一步。

### 4. 证据与解释

- **四角色分工**：Working Model 生成/修订 → Rubric 声明标准 → Grader Model 取证并判定 → Evidence Tool 返回结构化事实。
  证据工具不负责放行，评分模型不替代确定性测试。
- **两处 `tools` 不通用**：`RubricMiddleware(tools=...)` 只给评分模型取证；
  `create_deep_agent(tools=...)` 才是工作模型的工具箱。混淆会让工作模型"看不见"工具。
- **五种结果**：`satisfied` 唯一放行；`needs_revision`、`failed`、`grader_error`、`max_iterations_reached` 全部拒绝。
- **`unverified=True`**：评分模型声称通过但没逐项覆盖标准，中间件降级为 `needs_revision` 并打标——
  它表示"没有完整验证"，不是"已确认有缺陷"。
- **fail-closed**：`accepted = 评审存在 and 最后一条 result == "satisfied"`。未知状态默认拒绝。
- **为什么"顺序错"能被抓**：`actual != expected` 比较的是整个列表，元素相同、顺序不同就不相等。
  实测 `expected [2, 1], got [1, 2]`。
- **`on_evaluation` 不是控制钩子**：它抛出的异常会被记录并抑制，不能用来阻止 Agent 或做权限判断。
- **`exec` 不是沙箱**：本仓库的测试工具用 `exec` 仅作教学；生产必须隔离进程/容器并限制文件、网络、CPU、内存与时间。

### 5. 下一步修正

1. **强 Rubric 闭环待复现**：免费网关 429，未能验证"补上格式标准后评分模型会拒绝并触发修订"。
2. **并发与幂等未测**：`on_evaluation` 的记录需要按 `grading_run_id` 归属，并对 `(grading_run_id, iteration)` 建幂等约束。
3. **离线评测未做**：首轮通过率、平均评分轮数、人工推翻率都还没有数据。
4. **沙箱未接**：证据工具仍在当前进程执行候选代码；应换成受限进程或容器。
5. **更多失败状态**：只构造了 `needs_revision`，`failed` / `grader_error` / `unverified` 只做了门判定，没做端到端复现。

## 错题记录

| # | 原题 | 当时的选择 | 错误理解 | 正确机制 |
|---|---|---|---|---|
| 1 | 测试能否抓"结果对、顺序错" | 未勾（认为抓不到） | 以为只有崩溃才算失败 | `actual != expected` 比较整个列表，顺序不同即不等；实测 `expected [2, 1], got [1, 2]` |
| 2 | 哪条结果才允许放行 | `grader_error 但已有答案` | 有答案就能放行 | 只有 `satisfied`（且未 `unverified`）放行；其余四种一律拒绝 |
| 3 | 两处 `tools` 的区别 | 前者给工作模型、后者给评分模型 | 两个工具箱归属反了 | `RubricMiddleware(tools=...)` 只给评分取证；`create_deep_agent(tools=...)` 给工作模型 |
| 4 | satisfied 却不合格的直接原因 | 工作模型没收到任务描述 | 把"Rubric 漏标准"误判成"任务没传达" | TASK 给工作模型读，RUBRIC 给评分模型读；格式要求没写进 RUBRIC，评分就不查 |

**共同盲区**：这是第 3 次出现"归属/位置"类错误（前两次：reject/respond、技能与记忆的存放位置）。
本质不是知识点没记住，而是"**哪个东西归哪个组件**"没有建模。后续章节会先给归属表，再讲流程。

## 运行方式

```bash
cd /mnt/d/study/deepagents-in-action/research_deepagent

# 三个零 token 实验（不需要 .env、不需要网络）
uv run --frozen python ../notes/task7/code/rubric_evidence.py
uv run --frozen python ../notes/task7/code/rubric_gate.py
uv run --frozen python ../notes/task7/code/rubric_task_vs_rubric.py

# 真实模型闭环（约 4–10 次调用，免费额度可能 429）
uv run --frozen python ../notes/task7/code/rubric_loop.py
```

重出导图（Windows 侧）：

```bash
uv run --with matplotlib python notes/task7/mindmap.py
```
