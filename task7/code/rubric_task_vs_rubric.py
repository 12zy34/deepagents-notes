"""Task7（ch13）：为什么叫"Rubric 漏写"，而不是"任务没传达"。

对应课程：https://datawhalechina.github.io/deepagents-in-action/chapters/ch13-grading-rubrics/

这是 Lesson 0006 测验 Q4 的专项实验。它把两份文件并排检查：

  TASK   —— 写给【工作模型】看："做什么"
  RUBRIC —— 写给【评分模型】看："验收什么"

真实翻车里，TASK 明确写了 "return only executable Python source code"，
但 RUBRIC 的 7 条里没有任何一条关于输出格式。评分模型只读 RUBRIC，
所以它不知道要检查格式 —— 这就是 "satisfied 但回答带说明文字和围栏" 的直接原因。

运行（在 research_deepagent 目录下，复用 .venv，无需 .env）：
    uv run --frozen python ../notes/task7/code/rubric_task_vs_rubric.py
"""

import platform

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

STRONG_RUBRIC = WEAK_RUBRIC + "\n" + """
- The final answer contains only Python source code: no prose, no explanations, no Markdown fences.
- The returned code must parse as valid Python (no stray non-code characters).
""".strip()

FORMAT_KEYWORDS = ["only executable python source code", "no prose", "markdown fence", "parse as valid python"]


def bullets(rubric: str) -> int:
    return len([line for line in rubric.splitlines() if line.strip().startswith("-")])


def format_coverage(doc: str) -> list[str]:
    low = doc.lower()
    return [k for k in FORMAT_KEYWORDS if k in low]


print("$ uv run --frozen python ../notes/task7/code/rubric_task_vs_rubric.py\n")

rows = [
    ("TASK（工作模型读）", bullets(TASK), format_coverage(TASK)),
    ("WEAK_RUBRIC（评分模型读）", bullets(WEAK_RUBRIC), format_coverage(WEAK_RUBRIC)),
    ("STRONG_RUBRIC（评分模型读）", bullets(STRONG_RUBRIC), format_coverage(STRONG_RUBRIC)),
]

print("=== 「输出必须是纯代码」这条要求，写在哪份文件里？ ===")
for name, count, hits in rows:
    print(f"{name:28s} 条目数={count:<2d} 命中格式要求={hits or '无'}")

print("\n=== 评分模型实际读的是哪份？ ===")
print("RUBRIC（不是 TASK）—— 所以 WEAK_RUBRIC 没写，它就不知道要检查。")

print("\n=== 断言 ===")
assert format_coverage(TASK), "TASK 里没有格式要求：案例前提不成立"
print("[1/3] TASK 里确实写了「只返回可执行代码」——所以不是「任务没传达」")

assert not format_coverage(WEAK_RUBRIC), "弱 Rubric 竟然覆盖了格式要求，案例不成立"
print("[2/3] WEAK_RUBRIC 的 7 条里没有任何格式标准——评分模型看不到这条要求")

assert format_coverage(STRONG_RUBRIC), "强 Rubric 没有补上格式要求"
print("[3/3] STRONG_RUBRIC 补上两条格式标准后，评分模型才有东西可检查")

print("\n>>> 结论：要求写在 TASK 里 = 工作模型知道；写在 RUBRIC 里 = 评分模型才会查")
print(">>> 所以「satisfied 但不合格」的直接原因是 Rubric 漏写，不是任务没传达")

print(
    "\n---\n"
    f"运行环境：{platform.system()} + Python {platform.python_version()} + 无模型调用\n"
    "运行日期：2026-10-31"
)
