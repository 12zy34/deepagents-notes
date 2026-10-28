"""Task6（ch09 HITL）：证明 resume 时"从节点开头重放"，而不是从中断处继续。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/

做法极简：在一个中间件的 after_model 里，interrupt() 之前放一行计数器，然后：
  - 第一次 invoke：计数 1，暂停；
  - resume：计数 2 —— 说明 interrupt() 之前的代码被重新执行了。

这条现象直接推出 HITL 的三条铁律：
  1. interrupt() 之前不要有副作用（会执行两次）；
  2. 不要用裸 except 包 interrupt()（会吞掉暂停异常）；
  3. decisions 数量必须和 action_requests 对齐。

运行（在 research_deepagent 目录下，复用 .venv，无需 .env）：
    uv run --frozen python ../notes/task6/code/hitl_replay.py
"""

import platform
from importlib.metadata import version

from deepagents import create_deep_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt

ENTERED: list[str] = []


class ReplayDemo(AgentMiddleware):
    def after_model(self, state, runtime):  # noqa: ARG002
        ENTERED.append(f"第 {len(ENTERED) + 1} 次进入 after_model")
        interrupt({"问题": "继续吗？", "当前是第几次进入": len(ENTERED)})
        return None


class Fake(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


print("$ uv run --frozen python ../notes/task6/code/hitl_replay.py\n")

agent = create_deep_agent(
    model=Fake(responses=[AIMessage(content="好的。")]),
    middleware=[ReplayDemo()],
    checkpointer=MemorySaver(),
)

cfg = {"configurable": {"thread_id": "replay"}}
r1 = agent.invoke({"messages": [{"role": "user", "content": "开始"}]}, config=cfg)
ints = r1.get("__interrupt__") or []
print("=== 第一次 invoke 后 ===")
print("ENTERED:", ENTERED)
if ints:
    print("中断信息:", ints[0].value)

agent.invoke(Command(resume="继续"), config=cfg)
print("\n=== resume 之后 ===")
print("ENTERED:", ENTERED)

print("\n=== 断言 ===")
assert len(ENTERED) == 2, f"interrupt() 之前的代码应执行 2 次，实际 {len(ENTERED)} 次"
print("[1/1] resume 时节点从头重放：interrupt() 之前的代码执行了 2 次")

print("\n>>> 验证通过：恢复 = 读档 + 从节点开头重放（副作用必须放 interrupt 之后或做成幂等）")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "模型：未调用真实模型（脚本化假模型，零 token 消耗）\n"
    "运行日期：2026-10-28"
)
