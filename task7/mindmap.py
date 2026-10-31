# -*- coding: utf-8 -*-
"""生成 task7 的思维导图（PNG），放在 notes/task7/ 下。

编辑方法：改 BRANCHES，然后：
    uv run --with matplotlib python notes/task7/mindmap.py
"""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch

TASK_DIR = Path(__file__).resolve().parent
OUT = TASK_DIR / "评分量规.png"

REG = r"C:\Windows\Fonts\msyh.ttc"
BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
F = FontProperties(fname=REG)
FB = FontProperties(fname=BOLD) if Path(BOLD).exists() else F

INK = "#16150F"
SOFT = "#454134"
FAINT = "#83806F"
RULE = "#D8D2C1"
PAPER = "#FDFCF8"
ACCENT = "#8A2B2B"
TINTS = ["#F3EAE6", "#EDEFE7", "#F2EFE4", "#E9EDEA", "#F3EAE6", "#EDEFE7"]

TITLE = "第 13 章 · 评分量规：让验收有证据"
SUBTITLE = "叶片写机制 · deepagents 0.7.8 RubricMiddleware（model / tools / max_iterations / on_evaluation）"
FOOTER = "配套：lessons/0006 · notes/task7/code/ 四个实验（三个零 token）"

BRANCHES = [
    ("① 起点：停止≠完成", [
        "模型停手只是生成结束",
        "不可哈希用例直接 TypeError",
        "自检与生成共享盲点",
        "重试不知道差在哪一条",
    ]),
    ("② 证据：可取证", [
        "测试返回 ok + failures",
        "顺序错靠不等比较抓住",
        "改输入也能被断言抓到",
        "exec 不是沙箱，生产要隔离",
    ]),
    ("③ 闭环：四角色", [
        "Working 生成/修订，不自评",
        "Rubric 声明标准，不跑测试",
        "Grader 取证判定，不替代测试",
        "Evidence 返回事实，不放行",
    ]),
    ("④ 五种结果", [
        "satisfied 唯一放行",
        "needs_revision 写回 gap",
        "failed / grader_error 停止",
        "max_iterations 停止且不算过",
    ]),
    ("⑤ 归属：谁看什么", [
        "TASK 给工作，RUBRIC 给评分",
        "RubricMiddleware.tools 只给评分",
        "create_deep_agent.tools 给工作",
        "最终消息是候选，不是结论",
    ]),
    ("⑥ 代价与失败模式", [
        "Rubric 漏标准 = 评分不会查",
        "grader_error 也算没通过",
        "callback 抛错会被抑制",
        "上限不是修复按钮",
    ]),
]

WRAP = 30
ASCII_TOKEN = re.compile(r"[A-Za-z0-9_\-./:<>=()\[\]{}\"'`]+")


def wrap_tokens(text, limit=WRAP):
    tokens, pos = [], 0
    for m in ASCII_TOKEN.finditer(text):
        if m.start() > pos:
            tokens.extend(text[pos:m.start()])
        tokens.append(m.group())
        pos = m.end()
    if pos < len(text):
        tokens.extend(text[pos:])

    lines, cur = [], ""
    for tok in tokens:
        if len(cur) + len(tok) > limit and cur:
            lines.append(cur)
            cur = tok
        else:
            cur += tok
    if cur:
        lines.append(cur)
    return lines


def main():
    wrapped = [[wrap_tokens(leaf) for leaf in leaves] for _, leaves in BRANCHES]
    total_lines = sum(len(w) for branch in wrapped for w in branch)

    fig, ax = plt.subplots(figsize=(16, 13.5), dpi=150)
    fig.patch.set_facecolor(PAPER)
    ax.set_facecolor(PAPER)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.030, 0.968, TITLE, fontproperties=FB, fontsize=18, color=INK, va="top")
    ax.text(0.030, 0.933, SUBTITLE, fontproperties=F, fontsize=9, color=FAINT, va="top")
    ax.plot([0.030, 0.970], [0.915, 0.915], color=RULE, lw=0.9)

    top, bottom = 0.878, 0.070
    gap_units = 0.9 * len(BRANCHES)
    unit = (top - bottom) / (total_lines + gap_units)

    root_x, root_w, root_cx = 0.030, 0.118, 0.030 + 0.118 / 2
    root_y = 0.50
    root_h = 0.148
    ax.add_patch(FancyBboxPatch(
        (root_x, root_y - root_h / 2), root_w, root_h,
        boxstyle="round,pad=0.006,rounding_size=0.014",
        facecolor=ACCENT, edgecolor="none",
    ))
    ax.text(root_cx, root_y + 0.030, "评分量规", fontproperties=FB, fontsize=14, color="white", ha="center", va="center")
    ax.text(root_cx, root_y, "验收有证据", fontproperties=FB, fontsize=14, color="white", ha="center", va="center")
    ax.text(root_cx, root_y - 0.034, "停手 ≠ 通过", fontproperties=F, fontsize=8.0, color="#F0D6D0", ha="center", va="center")

    branch_x, branch_w = 0.205, 0.145
    leaf_x = 0.395
    cursor = top

    for i, ((name, _), lines_per_leaf) in enumerate(zip(BRANCHES, wrapped)):
        block_h = sum(len(lines) for lines in lines_per_leaf) * unit
        branch_cy = cursor - block_h / 2

        ax.add_patch(FancyBboxPatch(
            (branch_x, branch_cy - 0.030), branch_w, 0.060,
            boxstyle="round,pad=0.005,rounding_size=0.010",
            facecolor=TINTS[i % len(TINTS)], edgecolor=RULE, lw=0.9,
        ))
        ax.text(branch_x + branch_w / 2, branch_cy, name,
                fontproperties=FB, fontsize=11.4, color=INK, ha="center", va="center")

        ax.annotate(
            "",
            xy=(branch_x, branch_cy),
            xytext=(root_x + root_w + 0.006, root_y),
            arrowprops=dict(arrowstyle="-", color=RULE, lw=1.2,
                            connectionstyle="arc3,rad=%.2f" % (-0.05 + 0.025 * i)),
        )

        y = cursor
        for lines in lines_per_leaf:
            leaf_cy = y - len(lines) * unit / 2
            ax.plot([branch_x + branch_w, leaf_x - 0.010], [branch_cy, leaf_cy], color=RULE, lw=0.85)
            ax.plot([leaf_x - 0.010, leaf_x], [leaf_cy, leaf_cy], color=RULE, lw=0.85)
            ax.scatter([leaf_x], [leaf_cy], s=10, color=ACCENT, zorder=3)
            ax.text(leaf_x + 0.008, leaf_cy, "\n".join(lines),
                    fontproperties=F, fontsize=10.0, color=SOFT,
                    ha="left", va="center", linespacing=1.55)
            y -= len(lines) * unit

        cursor -= block_h + 0.9 * unit

    ax.text(0.030, 0.020, FOOTER, fontproperties=F, fontsize=8.4, color=FAINT, va="bottom")

    fig.savefig(OUT, facecolor=PAPER, bbox_inches="tight", pad_inches=0.24)
    print("已生成:", OUT)


if __name__ == "__main__":
    main()
