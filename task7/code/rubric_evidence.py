"""Task7（ch13 Grading Rubrics）：先验证"证据工具"，不调用任何模型。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/

本章的真实起点是一个"看起来做完了"的函数：
  find_duplicates([1, 2, 2, 3, 1]) -> [2, 1]     通过
  find_duplicates([[1], [1]])      -> TypeError  ← 任务要求支持不可哈希值

本脚本验证三件事（零 token、不联网）：
  1. 用 set 的实现会在"不可哈希"用例上抛错 —— 生成结束 ≠ 任务完成；
  2. 用"排序去重"的实现不会崩，但顺序错 —— 只有测试能发现这种静默错误；
  3. 用列表 + 相等比较的实现能通过全部用例，且不修改输入。

这正是 Rubric 里"可取证"那一项：把能由测试确定的事实交给工具，而不是让模型读代码猜。

运行（在 research_deepagent 目录下，复用 .venv，无需 .env）：
    uv run --frozen python ../notes/task7/code/rubric_evidence.py
"""

import platform
from copy import deepcopy
from importlib.metadata import version

SAFE_BUILTINS = {
    "all": all,
    "any": any,
    "enumerate": enumerate,
    "len": len,
    "list": list,
    "range": range,
    "set": set,
    "sorted": sorted,
    "tuple": tuple,
}


def run_test_suite(code: str) -> dict:
    """在受限 builtins 下加载候选代码，跑四条行为测试，返回结构化事实。

    注意：这不是沙箱，生产环境必须用隔离进程/容器（课程原文强调）。
    """
    namespace: dict = {"__builtins__": SAFE_BUILTINS}
    try:
        exec(code, namespace)  # noqa: S102 - 教学用途，非沙箱
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "failures": [f"load_error: {type(exc).__name__}: {exc}"]}

    find_duplicates = namespace.get("find_duplicates")
    if not callable(find_duplicates):
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
            actual = find_duplicates(values)
            if actual != expected:
                failures.append(f"{name}: expected {expected}, got {actual}")
            if values != original:
                failures.append(f"{name}: input was mutated")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    return {"ok": not failures, "failures": failures}


BAD_SET = """
def find_duplicates(values):
    seen = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates
""".strip()

WRONG_ORDER = """
def find_duplicates(values):
    duplicates = []
    for value in values:
        if values.count(value) > 1 and value not in duplicates:
            duplicates.append(value)
    return sorted(duplicates)
""".strip()

GOOD = """
def contains(items, target):
    return any(item == target for item in items)

def find_duplicates(values):
    seen = []
    duplicates = []
    for value in values:
        if contains(seen, value) and not contains(duplicates, value):
            duplicates.append(value)
        seen.append(value)
    return duplicates
""".strip()


print("$ uv run --frozen python ../notes/task7/code/rubric_evidence.py\n")

cases = [("set 实现（会崩）", BAD_SET), ("排序去重（结果对、顺序错）", WRONG_ORDER), ("列表 + 相等比较（正确）", GOOD)]
results = {}
for name, code in cases:
    result = run_test_suite(code)
    results[name] = result
    print(f"=== {name} ===")
    print(result)
    print()

print("=== 断言 ===")

bad = results["set 实现（会崩）"]
assert bad["ok"] is False, "set 实现居然通过了：测试没覆盖不可哈希用例"
assert any("unhashable" in f for f in bad["failures"]), f"没抓到 unhashable：{bad['failures']}"
print("[1/4] set 实现被抓到：test_unhashable 抛 TypeError")

wrong = results["排序去重（结果对、顺序错）"]
assert wrong["ok"] is False, "排序实现居然通过了：测试没校验顺序语义"
assert any("expected [2, 1], got [1, 2]" in f for f in wrong["failures"]), (
    f"没抓到顺序错误（可能只是缺 builtins）：{wrong['failures']}"
)
print("[2/4] 排序实现被抓到：test_basic 期望 [2, 1]、实际 [1, 2]（顺序语义）")

good = results["列表 + 相等比较（正确）"]
assert good["ok"] is True and good["failures"] == [], f"正确实现没通过：{good}"
print("[3/4] 正确实现四条用例全过，且未修改输入")

# 再单独确认"不修改输入"这条能被抓到
MUTATING = """
def find_duplicates(values):
    out = []
    for value in values:
        if values.count(value) > 1 and value not in out:
            out.append(value)
    values.clear()
    return out
""".strip()
mut = run_test_suite(MUTATING)
assert any("mutated" in f for f in mut["failures"]), f"没抓到输入被修改：{mut}"
print("[4/4] 修改输入的实现被抓到：input was mutated")

print("\n>>> 验证通过：证据工具能抓住三类问题——崩溃、语义顺序错、修改输入")
print(">>> 这正是 Rubric 要求的「可取证」：能由测试确定的事，不交给模型猜")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + 无模型调用\n"
    f"deepagents 版本（环境）：{version('deepagents')}\n"
    "运行日期：2026-10-31"
)
