# Task2：虚拟文件系统——「写入 — 读回 — 修改」（ch03）

> 资料来源声明：本目录练习改编自 Datawhale《DeepAgents 实战》课程
> [ch03 虚拟文件系统](https://datawhalechina.github.io/deepagents-in-action/chapters/ch03-virtual-filesystem/)。
> 完整引用清单见[仓库根 README](../README.md#引用与致谢)。

## 目录

- [虚拟文件系统Context Engineering的核心.png](./虚拟文件系统Context Engineering的核心.png) — 本章思维导图（手绘笔记）
- [code/write_read_edit.py](./code/write_read_edit.py) — 「写入 — 读回 — 修改」练习脚本
- [outputs/agent_note.md](./outputs/agent_note.md) — Agent 产出的真实磁盘文件（证据产物）

> 思维导图勘误：图中"六大文件系统工具"分支实际列了 **7** 个工具——
> `ls` / `read_file` / `write_file` / `edit_file` / `delete` / `glob` / `grep`，
> 其中 `delete` 为 v0.7 新增，故总数为 7。

## 核心知识点：可插拔 Backend

| Backend | 存储位置 | 产物在哪能找到 |
|---|---|---|
| `StateBackend`（默认） | LangGraph 线程状态 | 只在 `result["files"]` / checkpoint 里，**磁盘上没有** |
| `FilesystemBackend` | 本地磁盘 | `root_dir` 指向的目录下，亲手可摸 |

task1 没传 `backend` 参数，所以 Agent "写"的文件其实只是状态里的字典；本练习换成：

```python
from deepagents.backends import FilesystemBackend
backend = FilesystemBackend(root_dir=<notes/task2>, virtual_mode=True)
agent = create_deep_agent(model=model, backend=backend, system_prompt=...)
```

`virtual_mode=True` 开启路径沙箱：Agent 看到的是虚拟路径 `/outputs/agent_note.md`，
实际映射到 `{root_dir}/outputs/agent_note.md`，`..`、`~` 与越界路径一律被拦截。

## 打卡：统一要求五项

### 1. 验证什么

Agent 能否用虚拟文件系统完成一次完整的「`write_file` 写入 → `read_file` 读回核对 →
`edit_file` 精确替换」，并且产物以**真实文件**形式出现在项目目录里（而非只存在线程状态中）。

### 2. 改了什么

在课程示例（`create_deep_agent(model, backend=FilesystemBackend(root_dir=".", virtual_mode=True))`）基础上：

1. `root_dir` 由 `.` 改为本 task 目录（由脚本位置 `Path(__file__)` 推导，与运行目录无关），
   产物固定落在 `notes/task2/outputs/`；
2. 系统提示词固化三步操作与产物路径，并埋入占位行 `TODO: 待补充` 作为 `edit_file` 的替换锚点；
3. 脚本末尾追加**程序化验证**：文件存在性、大小、全文打印、断言 `DONE` 标记存在且 `TODO` 已消失；
4. `.env` 加载做了双路兜底（脚本目录向上查找 + 显式指向 `research_deepagent/.env`）。

### 3. 实际结果

- 工具调用序列（Agent 自主按序执行，未乱序）：
  1. `write_file /outputs/agent_note.md`（写入含 `TODO: 待补充` 的 10 行笔记）
  2. `read_file /outputs/agent_note.md`（读回核对）
  3. `edit_file`（`old_string: TODO: 待补充` → `new_string: DONE: 已由 Agent 二次确认`）
- 磁盘验证：`文件存在: True`，`/mnt/d/.../notes/task2/outputs/agent_note.md`，
  529 bytes / 10 行，全文中占位行已被替换为 `DONE: 已由 Agent 二次确认`
- 断言全部通过：`验证通过：写入 → 读回 → 修改 全链路完成，产物已真实落盘`

### 4. 证据与解释

- 证据产物：[outputs/agent_note.md](./outputs/agent_note.md)（Agent 写、Agent 改，
  由脚本断言确认），本 README 即"亲手在项目目录里找到"的记录；
- 解释：`FilesystemBackend` 把每次 `write_file/read_file/edit_file` 直接落到
  `root_dir` 对应的真实路径，因此 Agent 会话结束后文件仍在磁盘上；对比 task1 的
  默认 `StateBackend`（产物只在 `result["files"]` 状态字典里，进程结束即消失），
  这就是 ch03 强调的"可插拔 Backend 决定产物的持久性与位置"。

### 5. 下一步修正

1. `write_file` 会**完整覆盖**同名文件，局部修改必须用 `edit_file`——本练习刻意
   让两者各司其职，后续练习要注意别用 `write_file` 做"修改"；
2. `read_file` 默认只读前 100 行，长文件需 `offset`/`limit` 分片，本练习文件很短未触发，
   下一步用超长文件验证分片读取；
3. 未配置 `FilesystemPermission`，Agent 理论上可写 `root_dir` 下任何路径（含覆盖本 README），
   下一步加 `permissions=[FilesystemPermission(mode="deny", paths=["/README.md"])]` 做保护；
4. 换一个小参数模型复跑，观察三步调用是否还稳定（模型能力对多步工具链路影响显著）。

## 运行方式

```bash
cd /mnt/d/study/deepagents-in-action/research_deepagent
uv run --frozen python ../notes/task2/code/write_read_edit.py
```

复用项目 `.venv`（deepagents 0.7.8）与 `.env`（模型凭据），产物固定落在 `notes/task2/outputs/`。
