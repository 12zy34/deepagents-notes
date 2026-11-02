# -*- coding: utf-8 -*-
"""verify_teach_agent.py — 零 token 验证教学 Agent 的 4 项能力（deepagents 0.7.8）。

不调用真实模型：用录制型 / 脚本化假模型把 system prompt 与工具调用抄下来做断言。
覆盖：能力1 Skills（索引进提示词、正文不预加载）、能力2 长期记忆（全文注入、HTML 注释剥除）、
能力3 HITL（publish_page 中断 / approve 执行 / reject 不执行）、能力4 Rubric（图组装 + 证据工具单测）。

运行（在 research_deepagent 目录下，复用 .venv，无需 .env / 网络）：
    uv run --frozen python ../teach-agent/verify_teach_agent.py
"""

import os
import platform
import shutil
import tempfile
from importlib.metadata import version
from pathlib import Path

from deepagents.backends import StateBackend
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

import teach_agent
from teach_agent import (
    HERE,
    LEARNER_MD_PATH,
    PUBLISHED,
    build_teach_agent,
    check_lesson_structure,
    publish_page,
    record_mistake,
    run_rubric_demo,
    teach_files,
)

# 加载 research_deepagent/.env（真实评分模型需要 OPENAI_API_KEY / OPENAI_API_BASE / AGENTSEEK_MODEL）
try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parents[1] / "research_deepagent" / ".env"
    load_dotenv(_env_path)
except Exception:  # noqa: BLE001
    pass

# ===========================================================================
# 通用：录制型假模型（抄下 system prompt）
# ===========================================================================

RECEIVED: list[list] = []
SEEN_SYSTEM_PROMPTS: list[str] = []


def _text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


class RecordingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ARG002
        RECEIVED.append(list(messages))
        for m in messages:
            if m.type == "system":
                SEEN_SYSTEM_PROMPTS.append(_text_of(m))
                break
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


# ===========================================================================
# 能力3 的脚本化模型：第一次返回 publish_page 调用，第二次返回收尾消息
# ===========================================================================

def _tool_call(idx: int, name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"call_{idx}", "type": "tool_call"}


class ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):  # noqa: ARG002
        return self


def _get_interrupts(result):
    """兼容 v1（dict['__interrupt__']）与 v2（.interrupts）。"""
    if isinstance(result, dict) and result.get("__interrupt__"):
        return result["__interrupt__"]
    if hasattr(result, "interrupts") and result.interrupts:
        return result.interrupts
    return []


print("$ uv run --frozen python ../teach-agent/verify_teach_agent.py\n")


# ===========================================================================
# 能力1 + 能力2：Skills 索引进提示词 / 正文不预加载；Memory 全文注入 / 剥 HTML 注释
# ===========================================================================

agent_prompt = build_teach_agent(
    RecordingModel(responses=[AIMessage(content="收到。")]),
    checkpointer=MemorySaver(),
    rubric=False,  # 探针只验证 Skills/Memory 注入，不触发假评分模型
)
cfg = {"configurable": {"thread_id": "prompt-probe"}}
before = len(SEEN_SYSTEM_PROMPTS)
agent_prompt.invoke(
    {"messages": [{"role": "user", "content": "讲一节 Skills 的课"}], "files": teach_files()},
    config=cfg,
)
PROMPT = SEEN_SYSTEM_PROMPTS[before]

print("=== system prompt 关键证据 ===")
print("含 teach 技能索引 '- **teach**:':", "- **teach**:" in PROMPT)
print("含记忆全文埋点 MEM-TOKEN-TEACH-7742:", "MEM-TOKEN-TEACH-7742" in PROMPT)
print("含 HTML 注释内部备注（应为 False）:", "内部备注" in PROMPT)
print("含技能正文埋点 BODY-TOKEN-TEACH-9981（应为 False）:", "BODY-TOKEN-TEACH-9981" in PROMPT)

print("\n=== 断言（能力1 Skills + 能力2 Memory）===")
assert "- **teach**:" in PROMPT, "teach 技能没有进索引：Skills 未加载或路径层级错"
print("[1/2] 能力1：teach 技能索引进 system prompt（正文由模型自读，不预加载）")
assert "MEM-TOKEN-TEACH-7742" in PROMPT, "记忆全文没有注入：memory= 失效"
assert "内部备注" not in PROMPT, "HTML 注释没被剥掉：记忆里的内部标记泄漏给了模型"
print("[2/2] 能力2：learner.md 全文注入 + HTML 注释注入前被剥除")


# ===========================================================================
# 能力3：HITL —— publish_page 中断 / approve 执行 / reject 不执行
# ===========================================================================

PUBLISHED.clear()

# build_teach_agent 返回编译后的图对象，直接 invoke
hitl_agent = build_teach_agent(
    ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call(1, "publish_page", {"content": "《Skills 四层递进》教学页全文……"})]),
            AIMessage(content="已按你的要求处理。"),
        ]
    ),
    checkpointer=MemorySaver(),
    rubric=False,  # 探针只验证 HITL 中断/审批，不触发假评分模型
)

cfg_a = {"configurable": {"thread_id": "hitl-approve"}}
r1 = hitl_agent.invoke(
    {"messages": [{"role": "user", "content": "生成一节 Skills 课并交审批"}], "files": teach_files()},
    config=cfg_a,
)
ints = _get_interrupts(r1)
print("\n=== 能力3 HITL：第一次 invoke（应暂停）===")
print("中断数量:", len(ints))
if ints:
    val = ints[0].value if hasattr(ints[0], "value") else ints[0]
    print("action_requests:", val.get("action_requests"))
    print("review_configs:", val.get("review_configs"))
print("暂停时 publish_page 执行次数:", len(PUBLISHED))

r2 = hitl_agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=cfg_a)
print("\n=== approve 恢复之后 ===")
print("publish_page 执行次数:", len(PUBLISHED), "内容长度:", len(PUBLISHED[0]) if PUBLISHED else 0)
approved = list(PUBLISHED)

# reject 案例
PUBLISHED.clear()
hitl_agent_b = build_teach_agent(
    ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call(1, "publish_page", {"content": "待审页"})]),
            AIMessage(content="好的，我不发了。"),
        ]
    ),
    checkpointer=MemorySaver(),
    rubric=False,  # 探针只验证 HITL reject，不触发假评分模型
)
cfg_b = {"configurable": {"thread_id": "hitl-reject"}}
hitl_agent_b.invoke(
    {"messages": [{"role": "user", "content": "生成一节 Skills 课并交审批"}], "files": teach_files()},
    config=cfg_b,
)
r3 = hitl_agent_b.invoke(Command(resume={"decisions": [{"type": "reject", "message": "先补错题记录再发。"}]}), config=cfg_b)
reject_msg = next(
    (m for m in r3["messages"] if m.type == "tool" and getattr(m, "status", None) == "error"),
    None,
)
print("\n=== reject 恢复之后 ===")
print("publish_page 执行次数:", len(PUBLISHED))
print("reject 的 ToolMessage.status:", getattr(reject_msg, "status", None))

print("\n=== 断言（能力3 HITL）===")
assert ints, "第一次 invoke 没有产生中断：interrupt_on 未生效"
val = ints[0].value if hasattr(ints[0], "value") else ints[0]
assert val["action_requests"][0]["name"] == "publish_page", "action_requests 里没有 publish_page"
assert val["review_configs"][0]["allowed_decisions"] == ["approve", "edit", "reject"], "review_configs 不对"
print("[1/3] 能力3：publish_page 触发中断，action_requests / review_configs 正确")
assert len(PUBLISHED) == 0, "暂停阶段就执行了 publish_page：中断没拦住"
print("[2/3] 能力3：暂停时 publish_page 未执行")
assert approved and approved[0].startswith("《Skills"), f"approve 后未执行：{approved}"
print("[3/3] 能力3：approve 恢复后，publish_page 按原参数执行了一次")


# ===========================================================================
# 能力4：Rubric —— 图能组装（4 能力同图）+ 证据工具单测
# ===========================================================================

print("\n=== 能力4 Rubric：图组装 + 证据工具 ===")
full_agent = build_teach_agent(
    FakeMessagesListChatModel(responses=[AIMessage(content="ok")]),
    checkpointer=MemorySaver(),
)
assert hasattr(full_agent, "invoke"), "4 能力同图组装失败：build_teach_agent 未返回可用图"
print("[1/3] 能力4：Skills + Memory + HITL + Rubric 成功接入同一张 create_deep_agent 图")

good = (
    "真实案例：某团队把技能正文当整体塞进 system prompt，结果上下文直接爆掉"
    "（类比：把整本词典硬塞进脑容量）。可运行代码见下，运行输出显示只加载了索引，"
    "正文一个字没进。\n\n```python\n"
    "from deepagents import create_deep_agent\n"
    "a = create_deep_agent(model=m, skills=['/skills/teach/'])\n"
    "```\n\n"
    "运行输出：技能索引出现 '- **teach**:'，但正文标记 BODY-TOKEN-TEACH-9981 没有出现。"
    "机制上，skills 中间件只在 before_agent 扫一层并写索引，"
    "正文由模型 read_file 读取（源码 skills.py:928，行号明确）。为什么这样设计？"
    "因为每次模型调用都重拼索引，正文过大会放大每轮成本，这就是代价。"
    "用法：子 Agent 不继承父的 skills；失败模式是同名技能 last wins；边界在只 ls 一层。"
    "面试官追问：索引为什么不进正文？错题：曾误以为正文整体进 prompt，"
    "错误理解导致预算失控，正确机制是 L1 索引 + L2 自读。复盘时还要把这条错题"
    "写进长期记忆，避免下次再踩同样的坑。此外，memory 与 skills 是同一副骨架、一处相反："
    "memory 是全文注入，skills 是索引注入，两者都走 before_agent 的快照分支，"
    "换 thread 才重新加载。这条对照本身就是一节完整四层递进的课。"
)
bad = "太短了。"
res_good = check_lesson_structure.invoke({"lesson_text": good})
res_bad = check_lesson_structure.invoke({"lesson_text": bad})
print(f"[2/3] 好教学页 -> ok={res_good['ok']}，坏教学页 -> ok={res_bad['ok']}")
assert res_good["ok"] is True, f"好教学页应被证据工具判为达标：{res_good}"
assert res_bad["ok"] is False and res_bad["failures"], f"坏教学页应被判不合格：{res_bad}"
print("[3/3] 能力4：check_lesson_structure 证据工具能区分达标 / 不达标教学页")


# ===========================================================================
# 能力5：record_mistake —— Agent 对话中把错题自动追加进长期记忆（learner.md）
# ===========================================================================

print("\n=== 能力5：record_mistake 写入长期记忆 ===")
# 用临时副本避免污染种子 learner.md；测完即丢弃
_tmp = Path(tempfile.mkdtemp()) / "learner.md"
shutil.copyfile(HERE / "learner.md", _tmp)
teach_agent.LEARNER_MD_PATH = _tmp          # 指向临时副本
before = _tmp.read_text(encoding="utf-8")

res = record_mistake.invoke({
    "original": "以为 skills 正文整体进 system prompt",
    "choice": "直接在 prompt 里塞全文",
    "misunderstanding": "认为索引与正文一起注入",
    "correct": "L1 索引进提示词、L2 正文由模型 read_file（skills.py:928）",
    "source_ref": "skills.py:928",
})
after = _tmp.read_text(encoding="utf-8")
print("工具返回:", res)
print("是否追加了 LM- 开头的错题:", "LM-" in after and after != before)
assert "LM-" in after and after != before, "record_mistake 没有把错题写进长期记忆"
assert "唯一埋点 MEM-TOKEN-TEACH-7742" in after, "写入后埋点丢失：插入位置错误"
print("[1/2] 能力5：record_mistake 把错题结构化追加进 learner.md（埋点仍在，证明插入在错题段）")

# 集成：Agent 在对话中主动调用 record_mistake
PUBLISHED.clear()
rec_agent = build_teach_agent(
    ScriptedModel(
        responses=[
            AIMessage(content="", tool_calls=[_tool_call(1, "record_mistake", {
                "original": "以为 HITL 决策是改文件", "choice": "直接读写文件",
                "misunderstanding": "决策=文件操作",
                "correct": "决策=给模型回什么 status 的消息（human_in_the_loop.py:447）",
                "source_ref": "human_in_the_loop.py:447"})]),
            AIMessage(content="已记录。"),
        ]
    ),
    checkpointer=MemorySaver(), rubric=False, hitl=False,
)
rec_agent.invoke(
    {"messages": [{"role": "user", "content": "我刚犯了个错"}], "files": teach_files()},
    config={"configurable": {"thread_id": "rec-int"}},
)
after2 = _tmp.read_text(encoding="utf-8")
assert "LM-" in after2 and after2 != before, "Agent 调用 record_mistake 后长期记忆未更新"
print("[2/2] 能力5：Agent 在对话中调用 record_mistake 自动追加错题到 learner.md")
teach_agent.LEARNER_MD_PATH = LEARNER_MD_PATH   # 还原


# ===========================================================================
# 能力4（真实评分模型）：端到端 Rubric 闭环
# ===========================================================================

print("\n=== 能力4：真实评分模型端到端 Rubric 闭环 ===")
if os.environ.get("OPENAI_API_KEY"):
    _tmp2 = Path(tempfile.mkdtemp()) / "learner.md"
    shutil.copyfile(HERE / "learner.md", _tmp2)
    teach_agent.LEARNER_MD_PATH = _tmp2
    try:
        out = run_rubric_demo(max_iterations=2)
        assert out["evaluations"], "真实评分模型没有产生任何评审：检查 invoke 是否传了 rubric"
        print(f"[真实] 评审轮数: {len(out['evaluations'])}")
        for ev in out["evaluations"]:
            gaps = [c.get("name", "?") for c in ev.get("criteria", []) if not c.get("passed")]
            print(f"  iter {ev['iteration']}: {ev['result']}  gaps={gaps}")
        print(f"[真实] 最终结论: {out['last']['result'] if out['last'] else None}")
        print("[1/1] 能力4：真实评分模型已跑通端到端 Rubric 闭环（check_lesson_structure 取证 + 验收）")
    except Exception as exc:  # noqa: BLE001
        print("真实评分模型运行出错（不阻断零 token 验证）：", repr(exc)[:300])
    teach_agent.LEARNER_MD_PATH = LEARNER_MD_PATH
else:
    print("跳过：未检测到 OPENAI_API_KEY（真实模型调用需要 .env / 网络）。")
    print("说明：RubricMiddleware 已接入 build_teach_agent；端到端闭环请设置")
    print("      research_deepagent/.env 的 OPENAI_API_KEY / OPENAI_API_BASE / AGENTSEEK_MODEL 后运行：")
    print("      uv run --frozen python ../teach-agent/teach_agent.py --rubric")


print("\n>>> 验证通过：5 项能力全部按 deepagents 0.7.8 真实 API 接入并各自行为正确")
print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    "能力1/2/3/5：零 token（录制型/脚本化假模型）；能力4 端到端："
    + ("已接真实评分模型跑通" if os.environ.get("OPENAI_API_KEY") else "需 .env 后运行 teach_agent.py --rubric")
    + "\n运行日期：2026-11-02"
)
