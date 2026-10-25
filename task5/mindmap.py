# -*- coding: utf-8 -*-
"""生成 task5 的思维导图（PNG），与 task1–task4 的图同级放在 notes/task5/ 下。

为什么用代码画而不是 AI 生图：图中每个叶子都是机制断言，中文错一个字就废，
代码渲染可以随时改字重出图。

编辑方法：改下面的 BRANCHES，然后：
    uv run --with matplotlib python notes/task5/mindmap.py
"""

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch

TASK_DIR = Path(__file__).resolve().parent
OUT = TASK_DIR / "Skills能力包.png"

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

TITLE = "第 7 章 · Skills —— 可复用的 Agent 能力包"
SUBTITLE = "叶片写机制，不写功能名 · 依据 deepagents 0.7.8：skills.py:294 / 613-644 / 861-971，graph.py:676 / 761 / 818"
FOOTER = "配套：lessons/0002 交互课 · reference/ch07-skills-mechanics.html 速查 · outputs/*.log 断言日志"

BRANCHES = [
    ("① 它是什么", [
        "Skill = 目录 + SKILL.md + 可选 scripts/assets",
        "规范来自 agentskills.io，30+ 工具共用",
        "与 Tool 的差别：流程 + 知识，不是原子操作",
    ]),
    ("② L1：只取元数据", [
        "before_agent：ls 一层 → 下载 → 只解析 frontmatter",
        "写入 state['skills_metadata']（PrivateStateAttr）",
        "多源 all_skills[name] = skill → last wins",
        "最后一个源标 (higher priority)",
    ]),
    ("③ L1′：索引每轮重拼", [
        "wrap_model_call 每次调用都拼 system prompt",
        "每行 = name + description + Read `path`",
        "成本 = Σdescription × 模型调用次数",
    ]),
    ("④ L2/L3：模型自己读", [
        "提示词要求 read_file(limit=1000)，默认 100 行",
        "正文以 ToolMessage 落进 messages",
        "所以过不了委派边界：子 Agent 得自己读",
        "自定义子 Agent：spec 的 skills 为真值才装",
        "GP 的「继承」= graph.py:761 复制同一份列表",
    ]),
    ("⑤ 代价与失败模式", [
        "同 thread 不重扫：改 SKILL.md 不生效",
        "忘传 files → 索引空，且空列表也被缓存",
        "name ≠ 目录名：只 warning，静默加载",
        "深于一层扫不到；索引是快照，删文件仍列着",
    ]),
    ("⑥ 面试高频", [
        "三级加载里，只有 L1 是中间件干的",
        "索引不穿边界；skills 是装配不是继承",
        "skills=[] 两种判空：is not None vs 真值",
        "deny/interrupt 拦 write；Composite 剥前缀",
    ]),
]

WRAP = 40
ASCII_TOKEN = re.compile(r"[A-Za-z0-9_\-./:<>=()\[\]{}\"'`]+")


def wrap_tokens(text, limit=WRAP):
    """折行，但不切断英文标识符（read_file、skills_metadata 之类必须保持完整）。"""
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

    # 根节点
    root_x, root_w, root_cx = 0.030, 0.118, 0.030 + 0.118 / 2
    root_y = 0.50
    root_h = 0.148
    ax.add_patch(FancyBboxPatch(
        (root_x, root_y - root_h / 2), root_w, root_h,
        boxstyle="round,pad=0.006,rounding_size=0.014",
        facecolor=ACCENT, edgecolor="none",
    ))
    ax.text(root_cx, root_y + 0.030, "Skills", fontproperties=FB, fontsize=15, color="white", ha="center", va="center")
    ax.text(root_cx, root_y, "渐进式披露", fontproperties=FB, fontsize=15, color="white", ha="center", va="center")
    ax.text(root_cx, root_y - 0.034, "L1 元数据 · L2 自读",
            fontproperties=F, fontsize=8.0, color="#F0D6D0", ha="center", va="center")

    branch_x, branch_w = 0.205, 0.145
    leaf_x = 0.395
    cursor = top

    for i, ((name, _), lines_per_leaf) in enumerate(zip(BRANCHES, wrapped)):
        # 注意是"行数"不是"叶子数"：折成两行的叶子占两行高度（task4 的旧版按叶子数算，
        # 长叶子会压到下一个分支上）。
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
