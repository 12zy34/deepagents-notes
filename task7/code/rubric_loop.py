"""Task7（ch13）：用真实模型跑 Rubric 闭环 —— 弱 Rubric 与强 Rubric 的对照。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/

这个脚本把两个零 token 实验接起来（证据工具 + 验收门），中间补上"评分模型"这一环。
关键是做两轮对照：

  Phase 1（弱 Rubric）：只写功能标准，不写"回答必须是纯代码"。
      → 评分模型很可能第一轮就 satisfied，但独立复核会因 Markdown 围栏/说明文字而失败。
      → 结论：Rubric 没写的标准，评分模型不会替你管；satisfied ≠ 正确。

  Phase 2（强 Rubric）：补上"只返回 Python 源码、无围栏、无说明"与"语法必须能解析"。
      → 评分模型必须拿证据才能通过；若仍不合格，按 fail-closed 拒绝。

断言：
  1. 两阶段都至少发生一次评审；
  2. accepted 严格等于"最后一条评审 result == satisfied"；
  3. Phase 2 若被放行，独立复核必须通过（证明放行有证据支撑）；
  4. 记录 Phase 1 是否出现"satisfied 但复核失败"的差异（存在即说明弱 Rubric 有缺口）。

运行（在 research_deepagent 目录下，复用 .venv 与 .env；约 4–10 次真实调用）：
    uv run --frozen python ../notes/task7/code/rubric_loop.py
"""

import os
import platform
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / "research_deepagent" / ".env")

from deepagents import RubricMiddleware, create_deep_agent  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

SAFE_BUILTINS = {
    "all": all, "any": any, "abs": abs, "bool": bool, "dict": dict,
    "enumerate": enumerate, "float": float, "int": int, "isinstance": isinstance,
    "len": len, "list": list, "max": max, "min": min, "range": range,
    "reversed": reversed, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "type": type, "zip": zip,
    # 候选代码常用异常类型：缺了它们，合法代码会以 NameError 的形式"假失败"
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError,
}


def _run(code: str) -> dict:
    namespace: dict = {"__builtins__": SAFE_BUILTINS}
    try:
        exec(code, namespace)  # noqa: S102 - 教学用途，非沙箱
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "failures": [f"load_error: {type(exc).__name__}: {exc}"]}

    fn = namespace.get("find_duplicates")
    if not callable(fn):
        return {"ok": False, "failures": ["missing_function: find_duplicates is not defined"]}

    tests = [
        ("test_basic", [1, 2, 2, 3, 1], [2, 1]),
        ("test_empty", [], []),
        ("test_no_duplicates", [1, 2, 3], []),
        ("test_unhashable", [[1], [1], 2], [[1]]),
    ]
    failures: list[str] = []
    for name, values, expected in tests:
        original = deepcopy(values)
        try:
            actual = fn(values)
            if actual != expected:
                failures.append(f"{name}: expected {expected}, got {actual}")
            if values != original:
                failures.append(f"{name}: input was mutated")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return {"ok": not failures, "failures": failures}


@tool
def run_test_suite(code: str) -> dict:
    """Run behavioral tests against candidate code and return ok/failures.

    Call this with the latest candidate source before returning satisfied.
    """
    return _run(code)


TASK = """
Implement find_duplicates(values). Return each duplicated value once,
ordered by where it appears for the second time. Support unhashable values,
do not mutate the input, and return only executable Python source code.
""".strip()

WEAK_RUBRIC = """
- Before returning satisfied, call run_test_suite with the latest candidate code.
- The run_test_suite result must contain ok=true.
- The function is named find_duplicates and accepts one list argument.
- Each duplicated value appears exactly once.
- Result order follows where each value appears for the second time.
- Unhashable values such as nested lists are supported.
- The input list is not mutated.
""".strip()

STRONG_RUBRIC = WEAK_RUBRIC + """
- The final answer contains only Python source code: no prose, no explanations, no Markdown fences.
- The returned code must parse as valid Python (no stray non-code characters).
""".strip()


def extract_code(text: str) -> str:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            block = parts[1]
            if block.startswith("python"):
                block = block[len("python"):]
            return block.strip()
    return text


def format_ok(text: str) -> bool:
    """检查"回答本身"是否纯代码：无围栏、无开场白。

    extract_code 会从围栏里抠代码，所以它能"救"回可运行代码；
    但 Rubric 要求的是回答本身为纯代码，这个检查不能被 extract_code 掩盖。
    """
    raw = text.strip()
    if "```" in raw:
        return False
    head = raw.lstrip()
    return head.startswith(("def ", "from ", "import ", "class ", "@"))


def make_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("AGENTSEEK_MODEL", "agnes-3.0-flash"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_API_BASE"],
        temperature=0,
    )


def run_phase(name: str, rubric: str, thread: str) -> dict:
    evaluations: list[dict] = []

    def record(ev: dict) -> None:
        evaluations.append(dict(ev))
        gaps = [c.get("name", "?") for c in ev.get("criteria", []) if not c.get("passed")]
        print(f"  [{name}] iteration {ev['iteration']}: {ev['result']}")
        for gap in gaps:
            print(f"      gap: {gap}")

    agent = create_deep_agent(
        model=make_model(),
        system_prompt=(
            "You are a careful Python engineer. Return only executable Python source code, "
            "without Markdown fences. When the rubric grader reports a gap, revise the latest "
            "implementation to address that exact gap."
        ),
        middleware=[
            RubricMiddleware(
                model=make_model(),
                tools=[run_test_suite],
                max_iterations=3,
                on_evaluation=record,
            )
        ],
        checkpointer=MemorySaver(),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": TASK}], "rubric": rubric},
        config={"configurable": {"thread_id": thread}},
    )
    final_text = result["messages"][-1].text
    last = evaluations[-1] if evaluations else None
    accepted = bool(last) and last.get("result") == "satisfied"
    verification = _run(extract_code(final_text))
    return {
        "evaluations": evaluations,
        "last": last,
        "accepted": accepted,
        "verification": verification,
        "final_text": final_text,
        "format_ok": format_ok(final_text),
    }


print("$ uv run --frozen python ../notes/task7/code/rubric_loop.py\n")

print("=== Phase 1：弱 Rubric（只写功能，不写输出格式）===")
phase1 = run_phase("weak", WEAK_RUBRIC, "task7-weak")
print(f"  最终结论: {phase1['last']['result'] if phase1['last'] else None}")
print(f"  accepted: {phase1['accepted']}")
print(f"  独立复核: {phase1['verification']}")
print(f"  回答是纯代码: {phase1['format_ok']}")
print(f"  回答开头: {phase1['final_text'][:60]!r}")

print("\n=== Phase 2：强 Rubric（补上「纯代码 + 可解析」）===")
phase2 = run_phase("strong", STRONG_RUBRIC, "task7-strong")
print(f"  最终结论: {phase2['last']['result'] if phase2['last'] else None}")
print(f"  accepted: {phase2['accepted']}")
print(f"  独立复核: {phase2['verification']}")
print(f"  回答是纯代码: {phase2['format_ok']}")
print(f"  评分说明: {phase2['last'].get('explanation', '')[:120] if phase2['last'] else None}")

print("\n=== 断言 ===")
assert phase1["evaluations"], "Phase 1 没有任何评审：检查 invoke 是否传了 rubric"
assert phase2["evaluations"], "Phase 2 没有任何评审"
print(f"[1/4] 两阶段都发生了评审（{len(phase1['evaluations'])} / {len(phase2['evaluations'])} 轮）")

for label, phase in (("Phase 1", phase1), ("Phase 2", phase2)):
    last_result = phase["last"].get("result") if phase["last"] else None
    assert phase["accepted"] == (last_result == "satisfied"), f"{label} 验收门与结论不一致"
print("[2/4] accepted 严格等于「最后一条评审是 satisfied」")

if phase2["accepted"]:
    assert phase2["verification"]["ok"] is True, f"Phase 2 放行了但复核失败：{phase2['verification']}"
    assert phase2["format_ok"] is True, "Phase 2 放行了但回答不是纯代码（格式标准没被执行）"
    print("[3/4] Phase 2 放行时：独立复核通过 + 回答是纯代码")
else:
    print(f"[3/4] Phase 2 未放行（{phase2['last'].get('result')}）—— fail-closed 拒绝，符合预期")

phase1_bad = bool(phase1["accepted"]) and (not phase1["verification"]["ok"] or not phase1["format_ok"])
print(f"[4/4] 弱 Rubric 是否出现「satisfied 但复核/格式不达标」：{phase1_bad}")
if phase1_bad:
    print("      → Rubric 漏写的标准，评分模型不会替你补：satisfied ≠ 正确")
else:
    print("      → 本轮模型恰好达标；换模型或重跑可能复现差异（首轮已提示过）")

print("\n>>> 实验结束：弱 Rubric 结论 =", phase1["last"].get("result") if phase1["last"] else None,
      "｜强 Rubric 结论 =", phase2["last"].get("result") if phase2["last"] else None)

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + deepagents {version('deepagents')}\n"
    f"模型：{os.environ.get('AGENTSEEK_MODEL', 'agnes-3.0-flash')}（working + grader）\n"
    "运行日期：2026-10-31"
)
