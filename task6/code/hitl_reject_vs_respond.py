"""Task6（ch09 HITL）：reject 与 respond 的对照实验——同一句"不要删"，AI 收到的却相反。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/

两个案例除了决策类型完全一样：都调用 delete_file、都传同一句 message。
唯一区别是决策用 reject 还是 respond。结果：
  - reject ：工具不执行，AI 收到 status="error" 的消息（"被拒了，别重试"）
  - respond：工具不执行，AI 收到 status="success" 的消息（人的话 = 工具结果）

结论：两者都不会真的删文件，但"告诉 AI 的事情"完全相反。副作用工具必须用 reject。

机制依据（deepagents 0.7.8 环境内）：
  - langchain/agents/middleware/human_in_the_loop.py:359-376  reject → status="error"
  - :377-385  respond → status="success" + 人的 message
  - :345-392  四种决策的完整分支

运行（在 research_deepagent 目录下，复用 .venv，无需 .env）：
    uv run --frozen python ../notes/task6/code/hitl_reject_vs_respond.py
"""

import platform
from importlib.metadata import version

from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

DELETED: list[str] = []


@tool
def delete_file(path: str) -> str:
    """删除指定路径的文件。"""
    DELETED.append(path)
    return f"已删除 {path}"


def tool_call(idx: int, name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"call_{idx}", "type": "tool_call"}


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


def make_agent() -> object:
    return create_deep_agent(
        model=ScriptedModel(
            responses=[
                AIMessage(content="", tool_calls=[tool_call(1, "delete_file", {"path": "/var/log/app/old.log"})]),
                AIMessage(content="好的。"),
            ]
        ),
        tools=[delete_file],
        interrupt_on={"delete_file": {"allowed_decisions": ["approve", "edit", "reject", "respond"]}},
        checkpointer=MemorySaver(),
    )


def run_case(decision: dict, thread: str) -> tuple[str | None, str | None, int]:
    """跑一次中断→恢复，返回（ToolMessage.status, content, 删除函数执行次数）。"""
    DELETED.clear()
    agent = make_agent()
    cfg = {"configurable": {"thread_id": thread}}
    agent.invoke({"messages": [{"role": "user", "content": "清理 /var/log/app/ 的过期日志"}]}, config=cfg)
    result = agent.invoke(Command(resume={"decisions": [decision]}), config=cfg)
    tool_msg = next((m for m in result["messages"] if m.type == "tool"), None)
    return (
        getattr(tool_msg, "status", None),
        (tool_msg.content if tool_msg else None),
        len(DELETED),
    )


print("$ uv run --frozen python ../notes/task6/code/hitl_reject_vs_respond.py\n")

SAME_MESSAGE = "不要删除，改为归档。"

reject_status, reject_content, reject_deleted = run_case(
    {"type": "reject", "message": SAME_MESSAGE}, "case-reject"
)
respond_status, respond_content, respond_deleted = run_case(
    {"type": "respond", "message": SAME_MESSAGE}, "case-respond"
)

print("=== 同一句：", SAME_MESSAGE, "===")
print("\n[reject]")
print("  工具执行次数:", reject_deleted)
print("  AI 收到的 status:", reject_status)
print("  AI 收到的内容:", reject_content)

print("\n[respond]")
print("  工具执行次数:", respond_deleted)
print("  AI 收到的 status:", respond_status)
print("  AI 收到的内容:", respond_content)

print("\n=== 断言 ===")
assert reject_deleted == 0 and respond_deleted == 0, "两种决策都不该执行工具"
print("[1/3] reject 与 respond 都没有执行删除函数（文件都还在）")

assert reject_status == "error", f"reject 应返回 error，实际 {reject_status}"
assert reject_content and "rejected" in reject_content, "reject 的消息里没有明确说明被拒绝"
print("[2/3] reject：status='error'，明确告诉 AI「被拒绝了、没执行」")

assert respond_status == "success", f"respond 应返回 success，实际 {respond_status}"
assert respond_content == SAME_MESSAGE, "respond 没有把人的话当作工具结果"
print("[3/3] respond：status='success'，人的话被当作工具结果")

print("\n>>> 验证通过：都不执行工具，但 reject 告诉 AI「失败」、respond 告诉 AI「成功」")
print(">>> 所以：拒绝删除/发送/部署必须用 reject；respond 只用于「本来就是问人」的工具")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "模型：未调用真实模型（脚本化假模型，零 token 消耗）\n"
    "运行日期：2026-10-28"
)
