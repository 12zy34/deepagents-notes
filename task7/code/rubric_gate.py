"""Task7（ch13）：把"失败关闭（Fail-Closed）验收门"写成可执行测试。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/

课程里最重要的一行是：

    accepted = final_evaluation is not None and final_evaluation["result"] == "satisfied"

它看起来平淡，但和"有最终消息就放行"只差一个条件，后果完全相反。本脚本用五条断言证明：
  1. 没有评审记录 → 不放行；
  2. needs_revision / failed / grader_error / max_iterations_reached → 都不放行；
  3. satisfied 但 unverified=True（评分没覆盖全部标准）→ 不放行；
  4. 只有 satisfied 且 unverified=False → 放行；
  5. 反例：`bool(messages)` 会在 needs_revision 时误放行。

运行（在 research_deepagent 目录下，复用 .venv，无需 .env）：
    uv run --frozen python ../notes/task7/code/rubric_gate.py
"""

import platform


def fail_closed(evaluations: list[dict]) -> bool:
    """只有"最后一条评审明确 satisfied 且未被降级"才放行。"""
    if not evaluations:
        return False
    last = evaluations[-1]
    return last.get("result") == "satisfied" and not last.get("unverified", False)


def naive_gate(messages: list[str]) -> bool:
    """错误示范：把"有最终消息"当成"验收通过"。"""
    return bool(messages)


CASES = [
    ("没有任何评审记录", [], False, "未知状态默认拒绝"),
    ("首轮就需要修订", [{"result": "needs_revision"}], False, "有 gap 时不能放行"),
    ("预算耗尽", [{"result": "max_iterations_reached"}], False, "没通过就是没通过"),
    ("评分认为标准无法评估", [{"result": "failed"}], False, "失败不是通过"),
    ("评分链路异常", [{"result": "grader_error"}], False, "异常不是通过"),
    ("声称通过但覆盖不全", [{"result": "satisfied", "unverified": True}], False, "降级结论不放行"),
    ("明确通过", [{"result": "satisfied", "unverified": False}], True, "唯一放行条件"),
    ("多轮后通过", [{"result": "needs_revision"}, {"result": "satisfied"}], True, "只看最后一轮"),
]

print("$ uv run --frozen python ../notes/task7/code/rubric_gate.py\n")
print("=== 验收门对五种结果的判定 ===")
for name, evaluations, expected, why in CASES:
    got = fail_closed(evaluations)
    print(f"{name:12s} → accepted={got!s:5s}（期望 {expected!s:5s}） {why}")

print("\n=== 反例：用 bool(messages) 当验收门 ===")
rejected_candidate = ["def find_duplicates(values): ...（第一轮候选，测试未过）"]
print("有最终消息:", bool(rejected_candidate), "｜评审结论: needs_revision")
print("→ bool(messages) 会放行一份被评审拒绝的候选答案")

print("\n=== 断言 ===")
for name, evaluations, expected, _ in CASES:
    assert fail_closed(evaluations) is expected, f"{name} 判定错误"
print("[1/3] 五种非 satisfied 结果全部不放行（含 unverified=True 的降级通过）")
print("[2/3] 只有 satisfied 且 unverified=False 才放行")

assert naive_gate(rejected_candidate) is True, "反例没复现：bool(messages) 竟然没放行"
assert fail_closed([{"result": "needs_revision"}]) is False
print("[3/3] 反例成立：bool(messages)=True 但 fail_closed=False，差一条状态判断")

print("\n>>> 验证通过：未知状态默认拒绝；有候选答案 ≠ 验收通过")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + 无模型调用\n"
    "运行日期：2026-10-31"
)
