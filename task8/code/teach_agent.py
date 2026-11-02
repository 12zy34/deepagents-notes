# -*- coding: utf-8 -*-
"""teach_agent.py — 把"teach skill"升级成可复现教学 Agent（deepagents 0.7.8）。

复用已学的 4 项课程能力，并明确每处改造点：

  能力1 Skills   —— teach 本身是 skills=["/skills/teach/"] 加载的 SKILL.md（渐进式披露：
                   索引进 system prompt，正文由模型自行 read_file，会话快照 last wins）。
  能力2 长期记忆 —— memory=["/memories/learner.md"] 全文注入，记错题/偏好；
                   同 thread 走快照不重扫；HTML 注释在注入前被剥除。
                   ★ 升级点：record_mistake 工具让 Agent 在对话中把错题自动追加进 learner.md。
  能力3 HITL     —— publish_page 触发 interrupt_on，生成教学页后暂停等你审批
                   （approve / edit / reject），reject 不执行且给模型 status=error。
  能力4 Rubric   —— RubricMiddleware 用 check_lesson_structure 取证，按 rubric 验收，
                   只有 satisfied 放行（fail-closed），其余四种结果一律拒绝。
                   ★ 升级点：接真实评分模型跑端到端闭环（run_rubric_demo）。

运行（在 research_deepagent 目录下，复用 .venv）：
    uv run --frozen python ../teach-agent/verify_teach_agent.py
    uv run --frozen python ../teach-agent/teach_agent.py            # 组装冒烟测试
    uv run --frozen python ../teach-agent/teach_agent.py --rubric   # 接真实评分模型跑闭环
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from deepagents import RubricMiddleware, create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

HERE = Path(__file__).resolve().parent

SKILL_FILE_PATH = "/skills/teach/teach/SKILL.md"   # skills=["/skills/teach/"] 扫描到的子目录
MEMORY_FILE_PATH = "/memories/learner.md"

# record_mistake 写入的长期记忆文件（默认即 learner.md；测试/演示时可覆盖为临时副本避免污染种子）
LEARNER_MD_PATH = HERE / "learner.md"

# 给 backend 的文件：skills 与 memory 都从 StateBackend 的 files 取正文
TEACH_SYSTEM_PROMPT = (
    "你是 DeepAgents 课程陪练教师。严格遵守 /skills/teach/teach/SKILL.md 的教学技能。"
    "每节课先按四层递进产出教学页，然后调用 publish_page 提交人工审批；"
    "若发现学习者做错或想歪，必须调用 record_mistake 把错题追加进长期记忆，再继续。"
)


# ---------------------------------------------------------------------------
# 从磁盘加载技能与记忆（单一信息源，避免与 SKILL.md / learner.md 漂移）
# ---------------------------------------------------------------------------

def _load_skill(path: Path) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{path} 缺少 frontmatter"
    _, fm, body = text.split("---", 2)
    name = description = None
    for line in fm.strip().splitlines():
        if line.startswith("name:"):
            name = json.loads(line[len("name:"):].strip())
        elif line.startswith("description:"):
            description = json.loads(line[len("description:"):].strip())
    assert name and description, f"{path} 的 frontmatter 缺少 name / description"
    return name, description, body.strip("\n")


def _skill_file_data() -> dict:
    name, description, body = _load_skill(HERE / "SKILL.md")
    wrapped = (
        "---\n"
        f"name: {json.dumps(name, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
        f"{body}\n"
    )
    return {SKILL_FILE_PATH: create_file_data(wrapped)}


def _memory_file_data() -> dict:
    return {MEMORY_FILE_PATH: create_file_data((HERE / "learner.md").read_text(encoding="utf-8"))}


def teach_files() -> dict:
    """首次 invoke 时随 payload.files 带上技能与记忆正文。"""
    return {**_skill_file_data(), **_memory_file_data()}


# ---------------------------------------------------------------------------
# 能力3 的工具：publish_page（HITL 触发点）
# ---------------------------------------------------------------------------

PUBLISHED: list[str] = []


@tool
def publish_page(content: str) -> str:
    """把一节教学页提交给人工审批。调用即触发 HITL 暂停，等待 approve / edit / reject。"""
    PUBLISHED.append(content)
    return f"已提交教学页，长度 {len(content)} 字符，等待审批。"


# ---------------------------------------------------------------------------
# 能力2 的升级工具：record_mistake（让 Agent 对话中自动追加错题到长期记忆）
# ---------------------------------------------------------------------------

_MISTAKE_MARKER = "唯一埋点 MEM-TOKEN-TEACH-7742"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _append_to_memory(entry: str) -> None:
    """把一条错题追加进 LEARNER_MD_PATH 的『## 错题』段（插在末尾埋点之前，保持埋点最后）。"""
    path = LEARNER_MD_PATH
    text = path.read_text(encoding="utf-8")
    line = entry.rstrip("\n") + "\n"
    if _MISTAKE_MARKER in text:
        text = text.replace(_MISTAKE_MARKER, line + _MISTAKE_MARKER, 1)
    else:
        text = text.rstrip() + "\n" + line
    path.write_text(text, encoding="utf-8")


@tool
def record_mistake(
    original: str,
    choice: str,
    misunderstanding: str,
    correct: str,
    source_ref: str = "",
) -> str:
    """把一条错题追加进长期记忆 learner.md（'## 错题' 段），供后续 thread 注入 system prompt。

    Args:
        original: 原题 / 场景（学习者当时在做什么）。
        choice: 学习者当时选了什么、或以为是什么。
        misunderstanding: 他的错误理解是什么。
        correct: 正确机制（尽量带源码坐标，如 skills.py:928）。
        source_ref: 证据来源（可空，如 skills.py:928）。
    """
    tag = f"LM-{_stamp()}"
    entry = (
        f"- {tag}: 原题={original}｜当时选择={choice}｜错误理解={misunderstanding}"
        f"｜正确机制={correct}"
        + (f"｜来源={source_ref}" if source_ref else "")
        + "\n"
    )
    _append_to_memory(entry)
    return f"已记录错题 {tag} 到长期记忆 learner.md。"


# ---------------------------------------------------------------------------
# 能力4 的证据工具：check_lesson_structure（给评分模型取证）
# ---------------------------------------------------------------------------

REQUIRED_BLOCKS = [
    ("真实案例切入", ["真实", "类比", "新闻", "事件"]),
    ("可运行代码+真实输出", ["代码", "运行", "输出", "结果"]),
    ("机制解释(带源码坐标)", ["源码", "行号", "为什么", "机制"]),
    ("用法/失败模式/代价", ["失败", "代价", "用法", "边界"]),
    ("面试追问", ["面试官", "追问"]),
    ("错题记录", ["错题", "错误理解", "正确机制"]),
]


@tool
def check_lesson_structure(lesson_text: str) -> dict:
    """按四层递进标准检查教学页结构，返回 {ok, failures}。评分模型用它对候选页取证。"""
    failures: list[str] = []
    low = lesson_text.lower()
    for name, keywords in REQUIRED_BLOCKS:
        if not any(kw in low for kw in keywords):
            failures.append(f"missing_block: {name}")
    if len(lesson_text) < 400:
        failures.append("too_short: 教学页过短，未展开四层")
    return {"ok": not failures, "failures": failures}


# ---------------------------------------------------------------------------
# 能力4 的评分标准（真实评分模型按它验收教学页）
# ---------------------------------------------------------------------------

TEACH_RUBRIC = """
- 教学页必须按四层递进组织：①真实案例/类比切入 ②可运行代码+真实输出 ③机制解释(带源码坐标 file:line) ④用法/失败模式/代价。
- 必须通过调用 check_lesson_structure 对教学页取证，且返回 ok=true 才可考虑 satisfied。
- 收尾必须包含『面试官追问』与可背的 90 秒答案。
- 术语首次出现即解释，英文术语保留原词（如 messages、state_update、middleware）。
- 若发现学习者有错误理解，必须已调用 record_mistake 写入长期记忆。
- 只有在 check_lesson_structure.ok=true 且以上各条都满足时才返回 satisfied；否则返回 needs_revision 并指出缺口。
""".strip()


# ---------------------------------------------------------------------------
# 组装教学 Agent：4 项能力一次性接入同一张图
# ---------------------------------------------------------------------------

def build_teach_agent(
    model,
    *,
    grader_model=None,
    checkpointer=None,
    rubric: bool = True,
    hitl: bool = True,
    rubric_max_iterations: int = 3,
    on_evaluation=None,
):
    """返回一张 compose 了 Skills + Memory + HITL + Rubric 的 DeepAgents 图。

    - model        : 工作模型（生成/修订教学页、调用 record_mistake）
    - grader_model : 评分模型（默认复用工作模型）；Rubric 闭环用它取证判定
    - checkpointer : 不传则用 MemorySaver（同 thread 走 skills/memory 快照）
    - rubric       : 是否接入 RubricMiddleware（默认 True）
    - hitl         : 是否接入 publish_page 的 HITL 中断（默认 True）。
                     端到端 Rubric 演示用 False，避免中断挡住评分闭环。
    - rubric_max_iterations : RubricMiddleware 的最大迭代轮数
    - on_evaluation: 真实评分时回调，接收每次 RubricEvaluation（iteration/result/criteria/explanation）
    """
    grader = grader_model or model
    tools = [record_mistake]          # 能力2 升级：工作模型可写长期记忆
    interrupt_on: dict = {}
    if hitl:
        tools.append(publish_page)    # 能力3：HITL 触发点
        interrupt_on = {"publish_page": {"allowed_decisions": ["approve", "edit", "reject"]}}

    middleware = [TodoListMiddleware()]
    if rubric:
        # 能力4：RubricMiddleware 做验收，用 check_lesson_structure 取证
        # 注意：这是"评分模型"的工具箱，与上面的工作模型 tools 不通用（LR-0006）
        middleware.append(
            RubricMiddleware(
                model=grader,
                tools=[check_lesson_structure],
                max_iterations=rubric_max_iterations,
                on_evaluation=on_evaluation,
            )
        )
    return create_deep_agent(
        model=model,
        backend=StateBackend(),
        # 能力1：teach 本身就是技能，L1 索引进提示词、正文由模型自读
        skills=["/skills/teach/"],
        # 能力2：长期记忆，全文注入，记错题/偏好
        memory=[MEMORY_FILE_PATH],
        # 工作模型的工具箱：record_mistake + （可选）publish_page
        tools=tools,
        interrupt_on=interrupt_on,
        middleware=middleware,
        system_prompt=TEACH_SYSTEM_PROMPT,
        checkpointer=checkpointer or MemorySaver(),
    )


# ---------------------------------------------------------------------------
# 真实评分模型（接 .env 的 OPENAI_API_KEY / OPENAI_API_BASE / AGENTSEEK_MODEL）
# ---------------------------------------------------------------------------

def make_openai_model(temperature: float = 0.0):
    """读取 .env 配置构造 ChatOpenAI（课程 rubric_loop.py 同款）。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=os.environ.get("AGENTSEEK_MODEL", "agnes-3.0-flash"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_API_BASE"],
        temperature=temperature,
    )


def run_rubric_demo(
    topic: str = "Skills 的渐进式披露（L1 索引进提示词、L2 正文由模型自读）",
    thread_id: str = "teach-rubric-demo",
    max_iterations: int = 2,
):
    """接真实评分模型跑端到端 Rubric 闭环：产出教学页 → check_lesson_structure 取证 → 验收。

    返回 {result, evaluations, final_text, last}；evaluations 来自 on_evaluation 回调。
    """
    working = make_openai_model()
    grader = make_openai_model()
    evaluations: list[dict] = []

    # 端到端 Rubric 演示不触发 HITL 中断，让评分闭环能在工作模型自然停止后运行
    agent = build_teach_agent(
        working,
        grader_model=grader,
        hitl=False,
        rubric_max_iterations=max_iterations,
        on_evaluation=lambda ev: evaluations.append(dict(ev)),
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"讲一节关于『{topic}』的课：按四层递进产出一节教学页，"
                        "先用 check_lesson_structure 自查结构，再交给我。"
                    ),
                }
            ],
            "files": teach_files(),
            "rubric": TEACH_RUBRIC,
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    final_text = result["messages"][-1].text
    last = evaluations[-1] if evaluations else None
    return {"result": result, "evaluations": evaluations, "final_text": final_text, "last": last}


if __name__ == "__main__":
    import sys

    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage

    if "--rubric" in sys.argv:
        # 端到端真实评分模型闭环（需要 .env 里的 OPENAI_API_KEY 等）
        out = run_rubric_demo()
        print("=== 端到端 Rubric 闭环（真实评分模型）===")
        for ev in out["evaluations"]:
            gaps = [c.get("name", "?") for c in ev.get("criteria", []) if not c.get("passed")]
            print(f"  iter {ev['iteration']}: {ev['result']}  gaps={gaps}")
            print(f"      explanation: {ev.get('explanation', '')[:160]}")
        print("最终结论:", out["last"]["result"] if out["last"] else None)
    else:
        # 冒烟测试：不调用模型，仅验证图能组装（Rubric 需要 grader 对象但不触发网络）
        agent = build_teach_agent(FakeMessagesListChatModel(responses=[AIMessage(content="ok")]))
        print("teach_agent 组装成功：Skills + Memory + HITL + Rubric 已接入同一张图")
        print("skills 源:", "/skills/teach/")
        print("memory 源:", MEMORY_FILE_PATH)
        print("HITL 中断工具:", "publish_page")
        print("长期记忆写入工具:", "record_mistake")
        print("Rubric 证据工具:", "check_lesson_structure")
