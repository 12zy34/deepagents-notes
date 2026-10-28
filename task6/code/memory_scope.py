"""Task6（ch08 长期记忆）：验证"短期 vs 长期"只由文件落在哪个 Backend 决定。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch08-long-term-memory/

本脚本延续 task5/task6 的"脚本化模型"思路：用假模型按顺序吐出工具调用，零 token 走完真实的
write_file → CompositeBackend 路由 → Store 落盘 全链路，再用断言对账。

关键点：每个场景用「新建一个 agent」而不是复用一个 agent 去改 model——因为编译好的图在构建时
就绑定了模型，运行期改 `.model` 不生效（这是脚本第一版的坑）。

验证四条命题：
  1. 写到 /memories/ 的文件进了 Store（长期），不留在 state["files"]；
  2. 写到 /notes.txt 的文件进了 StateBackend（短期），留在 state["files"]；
  3. 换 thread（换 agent）：/notes.txt 消失（短期），/memories/ 里的记忆仍经 memory= 重载进提示词（长期）；
  4. namespace 隔离：user-456 读不到 user-123 的记忆。

机制依据（deepagents 0.7.8）：
  - CompositeBackend 按路径前缀路由：/memories/ → StoreBackend，其余 → StateBackend
  - StoreBackend 把 /memories/ 前缀剥掉，剩余路径当 Store key（与 ch07 的 /skills/ 同一个机制）
  - MemoryMiddleware.before_agent 用 backend.download_files 取 memory= 指定的全文
  - StateBackend 的文件在 state["files"]，按 thread 隔离

运行（在 research_deepagent 目录下，复用项目 .venv，无需 .env）：
    uv run --frozen python ../notes/task6/code/memory_scope.py
"""

import platform
from dataclasses import dataclass
from importlib.metadata import version

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


def tool_call(idx: int, name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"call_{idx}", "type": "tool_call"}


class ScriptedModel(FakeMessagesListChatModel):
    """按给定顺序吐工具调用/AI 消息，同时把每次收到的 system prompt 抄下来。"""

    def __init__(self, responses, prompts):
        super().__init__(responses=responses)
        self._prompts = prompts

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        for m in messages:
            if m.type == "system":
                self._prompts.append(text_of(m))
                break
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@dataclass
class UserCtx:
    user_id: str = "user-123"


def mem_namespace(rt):
    return (getattr(rt.context, "user_id", "user-123"), "memories")


# 共享的 Store 与 Backend：长期记忆的"档案柜"和"路由表"在整个进程里只有一份
store = InMemoryStore()
backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend(namespace=mem_namespace)},
)
prompts: list[str] = []


def make_agent(responses):
    """每个场景新建一个 agent：图在构建时绑定模型，运行期不能换。"""
    return create_deep_agent(
        model=ScriptedModel(responses=responses, prompts=prompts),
        backend=backend,
        context_schema=UserCtx,
        memory=["/memories/preferences.md"],
        store=store,
        checkpointer=MemorySaver(),
    )


def invoke(responses, user_msg: str, user_id: str, thread: str) -> dict:
    agent = make_agent(responses)
    return agent.invoke(
        {"messages": [{"role": "user", "content": user_msg}]},
        context=UserCtx(user_id=user_id),
        config={"configurable": {"thread_id": thread}},
    )


print("$ uv run --frozen python ../notes/task6/code/memory_scope.py\n")

# ---- 场景 1：thread t1（user-123）写两个文件 ----
r1 = invoke(
    [
        AIMessage(content="", tool_calls=[
            tool_call(1, "write_file", {"file_path": "/memories/preferences.md", "content": "张三喜欢简洁代码，注释中文"}),
        ]),
        AIMessage(content="", tool_calls=[
            tool_call(2, "write_file", {"file_path": "/notes.txt", "content": "这是一条临时笔记"}),
        ]),
        AIMessage(content="已写入。"),
    ],
    "记住我的偏好，并记一条临时笔记。",
    "user-123",
    "t1",
)

files1 = r1.get("files") or {}
print("=== 场景 1（t1 写两个文件）===")
print("state['files'] 的键:", sorted(files1.keys()))
saved = store.get(("user-123", "memories"), "/preferences.md")
print("Store 里 /preferences.md 内容:", (saved.value["content"][:24] if saved else None))

# ---- 场景 2：换新 thread t2（同一个 user-123，新 agent 新 state） ----
prompts.clear()
r2 = invoke(
    [AIMessage(content="好的张三，还是简洁风格。")],
    "帮我写个排序函数。",
    "user-123",
    "t2",
)

files2 = r2.get("files") or {}
print("\n=== 场景 2（换 thread t2，同 user-123）===")
print("state['files'] 的键:", sorted(files2.keys()))
print("新线程的 system prompt 里含记忆全文:", "张三喜欢简洁代码" in (prompts[-1] if prompts else ""))

# ---- 场景 3：隔离检查 ----
print("\n=== 场景 3（namespace 隔离）===")
print("user-456 读 /preferences.md:", store.get(("user-456", "memories"), "/preferences.md"))

# ----------------------------------------------------------------------------
# 断言
# ----------------------------------------------------------------------------

print("\n=== 断言 ===")

# 1. /memories/ 进了 Store，没留在 state
assert saved is not None, "记忆内容没有写进 Store（检查 CompositeBackend 路由）"
assert "张三喜欢简洁代码" in saved.value["content"], "Store 里的内容不对"
assert "/memories/preferences.md" not in files1, "/memories/ 文件留在了 state：路由未生效"
print("[1/5] /memories/ 路由到 Store（长期），且已从 state 剥离")

# 2. /notes.txt 进了 StateBackend（state）
assert "/notes.txt" in files1, "/notes.txt 没有进入 state：StateBackend 默认路径异常"
print("[2/5] /notes.txt 进入 StateBackend（短期，state['files']）")

# 3. 换 thread：短期消失、长期仍在
assert "/notes.txt" not in files2, "新 thread 仍能看到 /notes.txt：StateBackend 没有按 thread 隔离"
assert "张三喜欢简洁代码" in (prompts[-1] if prompts else ""), "新 thread 没从 Store 重载记忆：memory= 未生效"
print("[3/5] 换 thread：/notes.txt 消失（短期），记忆经 memory= 重载进提示词（长期）")

# 4. namespace 隔离
assert store.get(("user-456", "memories"), "/preferences.md") is None, "user-456 读到了 user-123 的记忆"
print("[4/5] namespace 隔离：user-456 读不到 user-123 的记忆")

# 5. 前缀剥离：Store key 是相对路径，不含 /memories/
assert saved.key == "/preferences.md", f"Store key 错误：{saved.key}"
print("[5/5] CompositeBackend 剥掉了 /memories/ 前缀，Store key 是相对路径")

print("\n>>> 验证通过：短期(StateBackend)按 thread 隔离 / 长期(StoreBackend)跨 thread / namespace 隔离 / 前缀剥离")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "模型：未调用真实模型（脚本化假模型，零 token 消耗）\n"
    "运行日期：2026-10-27"
)
