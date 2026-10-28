"""Task6（ch09 Human-in-the-Loop）：验证"中断 → 审批 → 恢复执行"的真实链路。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch09-human-in-the-loop/

本脚本用"脚本化假模型"确定性触发一次 delete_file 工具调用（零 token），
走完 interrupt_on → interrupt() 暂停 → Command(resume=...) 恢复 全链路，再用断言对账。

验证四条命题：
  1. 第一次 invoke 在 delete_file 处暂停，result 里能拿到 action_requests（工具名+参数+允许的决策）；
  2. 暂停时工具【没有】被执行；
  3. resume({"type":"approve"}) 后，工具【真的执行了】，且参数是模型原始参数；
  4. 换个线程用 reject 恢复：工具【不执行】，模型收到 status="error" 的"被拒"消息。

机制依据：
  - langchain/agents/middleware/human_in_the_loop.py:447-457  after_model 取最后一条 AIMessage 的 tool_calls
  - :474-481  组装 HITLRequest 并调用 interrupt()
  - :345-392  四种决策分支（approve/reject 的落点不同）
  - LangGraph interrupt()：抛异常暂停 + checkpoint 存档 + resume 从头重放节点

运行（在 research_deepagent 目录下，复用 .venv，无需 .env）：
    uv run --frozen python ../notes/task6/code/hitl_approval.py
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


def get_interrupts(result):
    """兼容 v1（dict['__interrupt__']）与 v2（.interrupts）两种返回。"""
    if isinstance(result, dict) and result.get("__interrupt__"):
        return result["__interrupt__"]
    if hasattr(result, "interrupts") and result.interrupts:
        return result.interrupts
    return []


def make_agent(responses):
    return create_deep_agent(
        model=ScriptedModel(responses=responses),
        tools=[delete_file],
        interrupt_on={"delete_file": {"allowed_decisions": ["approve", "edit", "reject"]}},
        checkpointer=MemorySaver(),
    )


print("$ uv run --frozen python ../notes/task6/code/hitl_approval.py\n")

# ---- 案例 A：approve ----
agent_a = make_agent(
    [
        AIMessage(content="", tool_calls=[tool_call(1, "delete_file", {"path": "/tmp/temp.txt"})]),
        AIMessage(content="已按你的要求处理。"),
    ]
)
cfg_a = {"configurable": {"thread_id": "approve-case"}}
r1 = agent_a.invoke(
    {"messages": [{"role": "user", "content": "删掉 temp.txt"}]},
    config=cfg_a,
)

ints = get_interrupts(r1)
print("=== 案例 A：第一次 invoke（应在此暂停）===")
print("中断数量:", len(ints))
if ints:
    value = ints[0].value if hasattr(ints[0], "value") else ints[0]
    print("action_requests:", value.get("action_requests"))
    print("review_configs:", value.get("review_configs"))
print("暂停时 delete_file 被调用次数:", len(DELETED))

# resume：approve
r2 = agent_a.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=cfg_a)
print("\n=== 案例 A：approve 恢复之后 ===")
print("delete_file 被调用次数:", len(DELETED), "参数:", DELETED)
print("最终 AI 消息:", r2["messages"][-1].content)
approved_paths = list(DELETED)   # 案例 B 会清空 DELETED，先存档

# ---- 案例 B：reject ----
DELETED.clear()
agent_b = make_agent(
    [
        AIMessage(content="", tool_calls=[tool_call(1, "delete_file", {"path": "/tmp/temp.txt"})]),
        AIMessage(content="好的，我不删了。"),
    ]
)
cfg_b = {"configurable": {"thread_id": "reject-case"}}
agent_b.invoke({"messages": [{"role": "user", "content": "删掉 temp.txt"}]}, config=cfg_b)
r3 = agent_b.invoke(Command(resume={"decisions": [{"type": "reject", "message": "不要删除，改为归档。"}]}), config=cfg_b)

reject_msg = next((m for m in r3["messages"] if m.type == "tool" and getattr(m, "status", None) == "error"), None)
print("\n=== 案例 B：reject 恢复之后 ===")
print("delete_file 被调用次数:", len(DELETED))
print("reject 的 ToolMessage.status:", getattr(reject_msg, "status", None))
print("reject 的 ToolMessage.content:", (reject_msg.content[:60] if reject_msg else None))

# ----------------------------------------------------------------------------
# 断言
# ----------------------------------------------------------------------------

print("\n=== 断言 ===")

# 1. 中断发生，且能读到 action_requests
assert ints, "第一次 invoke 没有产生中断"
value = ints[0].value if hasattr(ints[0], "value") else ints[0]
assert value["action_requests"][0]["name"] == "delete_file", "action_requests 里没有 delete_file"
assert value["action_requests"][0]["args"] == {"path": "/tmp/temp.txt"}, "action_requests 参数不对"
assert value["review_configs"][0]["allowed_decisions"] == ["approve", "edit", "reject"], "review_configs 不对"
print("[1/4] 中断发生，action_requests 含工具名/参数，review_configs 含允许决策")

# 2. 暂停时工具没执行
assert len(DELETED) == 0, "暂停阶段就执行了工具：中断没拦住"
print("[2/4] 暂停时 delete_file 未执行")

# 3. approve 后真的执行了
assert approved_paths == ["/tmp/temp.txt"], f"approve 后 delete_file 未按原参数执行：{approved_paths}"
print("[3/4] approve 恢复后，delete_file 按原参数执行了一次")

# 4. reject 不执行 + 模型收到 error
assert len(DELETED) == 0, "reject 却执行了工具"
assert reject_msg is not None and "rejected" in (reject_msg.content or ""), "reject 没产生 status=error 的拒绝消息"
print("[4/4] reject 恢复后，delete_file 未执行，模型收到 status=error 的拒绝消息")

print("\n>>> 验证通过：interrupt_on 中断 / approve 执行 / reject 不执行且反馈给模型")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "模型：未调用真实模型（脚本化假模型，零 token 消耗）\n"
    "运行日期：2026-10-28"
)
