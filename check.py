# -*- coding: utf-8 -*-
"""
对话粗筛器（对应 rules.md 4.9 第一层）

定位：只列候选，不下结论。它的产物是「待判清单」，不是合格证。
用法： python check.py 正文-v2/006-xxx.md

设计原则（v2）：
  1. 不再用疑问词表当唯一判据——按句末标点切分，逐句过筛
  2. 短句 + 句号 一律列入，不管有没有疑问词
  3. 区分「裸台词」和「已带标记」，裸的优先级高
  4. 增加复述检测（4.8）
"""
import io
import os
import re
import sys

MATH = re.compile(r"[×÷=]|\d+\s*[加减乘除]\s*\d+")
DIALOG = re.compile(r'["“]([^"”]+)["”]')
SENT = re.compile(r"[^。！？…]+[。！？…]?")

SHORT = 6          # 短句阈值（不含标点）
Q_WORDS = ["什么", "怎么", "哪", "谁", "吗", "呢", "多少", "几", "是不是", "能不能"]


def chars(text):
    return len(re.sub(r"\s", "", text))


def strip_punct(s):
    return re.sub(r'[。！？…，、,\.\?!\s"“”]', "", s)


def main():
    if len(sys.argv) < 2:
        print("用法: python check.py <章节文件.md>")
        return 2
    path = sys.argv[1]
    text = io.open(path, encoding="utf-8").read()
    lines = text.split("\n")
    body = "\n".join(lines[1:])

    hard = []      # 硬指标，确定是错的
    cand = []      # 待判清单，需要审读层判断

    # ---------- 1 标题 ----------
    h1 = lines[0].strip()
    m = re.match(r"# 第 (\d+) 章[：: ](.*)$", h1)
    if not m:
        hard.append("H1 格式不对，应为「# 第 001 章：四字标题」→ " + h1)
    else:
        title = m.group(2).strip()
        if len(title) != 4:
            hard.append("标题「%s」是 %d 字，规则要求正好 4 字" % (title, len(title)))

    # ---------- 2 字数 ----------
    n = chars(body)
    if n > 2500:
        hard.append("正文 %d 字，超上限 2500" % n)
    elif n < 1700:
        cand.append("正文 %d 字，低于下限 1700" % n)

    # ---------- 3 算式 ----------
    maths = MATH.findall(body)
    if maths:
        hard.append("出现算式 %d 处：%s" % (len(maths), maths[:5]))

    # ---------- 4 台词逐句过筛 ----------
    all_lines = []   # (行号, 台词, 裸台词?) 按出现顺序，用于复述检测
    for i, line in enumerate(lines, 1):
        outside = strip_punct(DIALOG.sub("", line))
        bare = len(outside) <= 2
        for mm in DIALOG.finditer(line):
            speech = mm.group(1).strip()
            if not speech:
                continue
            all_lines.append((i, speech, bare))
            for sm in SENT.finditer(speech):
                s = sm.group(0).strip()
                if not s:
                    continue
                core = strip_punct(s)
                if not core:
                    continue
                punct = s[-1]
                L = len(core)
                has_q = any(w in core for w in Q_WORDS)
                tag = "★裸" if bare else "已带标记"

                if L <= SHORT and punct == "。":
                    cand.append("第 %d 行 [%s] 短句用句号，判不出语气：%s" % (i, tag, s))
                elif has_q and punct == "。":
                    cand.append("第 %d 行 [%s] 含疑问词却用句号：%s" % (i, tag, s))
                elif L <= 2 and punct == "？":
                    cand.append("第 %d 行 [%s] 极短问句，确认不是陈述误标：%s" % (i, tag, s))

    # ---------- 5 复述检测（4.8）----------
    for k in range(len(all_lines) - 1):
        l1, s1, _ = all_lines[k]
        l2, s2, _ = all_lines[k + 1]
        if l2 - l1 > 4:
            continue
        a, b = strip_punct(s1), strip_punct(s2)
        if len(b) >= 3 and b in a:
            cand.append("第 %d 行 疑似原样复述上一句（第 %d 行）：%s → %s" % (l2, l1, s1[:16], s2[:16]))

    # ---------- 6 章内重复片段 ----------
    seg = [re.sub(r"\s", "", s) for s in re.split(r"[。！？\n]", body) if 7 <= len(s) <= 20]
    seen = {}
    for s in seg:
        seen[s] = seen.get(s, 0) + 1
    dup = [(s, c) for s, c in seen.items() if c >= 2]
    if dup:
        cand.append("重复片段 %d 例：%s" % (len(dup), [d[0] for d in dup[:3]]))

    # ---------- 7 章末断章（0.3）----------
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip() and p.strip() != "---"]
    if paras:
        last = paras[-1]
        HALF = ["试着", "伸手去", "伸手拿", "准备", "打算", "决定", "刚要", "要去", "想要", "伸手想"]
        hit = [w for w in HALF if last.startswith(w) or ("他" + w) in last[:8]]
        if hit:
            hard.append("章末像是半截动作（%s）：%s" % (hit[0], last[:30]))
        if any(last.startswith(w) for w in ["他不知道的是", "接下来"]):
            hard.append("用了廉价钩子：%s" % last[:26])

    # ---------- 8 人物首现（4.10）----------
    # 只判「全书首次出现」：同名若在更早的章里出现过，说明身份已经交代过，跳过
    cdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "01-characters")
    vdir = os.path.dirname(os.path.abspath(path))
    cur = os.path.basename(path)[:3]
    if os.path.isdir(cdir):
        names = sorted(f[:-3] for f in os.listdir(cdir) if f.endswith(".md"))
        earlier = ""
        for f in sorted(os.listdir(vdir)):
            if f.endswith(".md") and f[:3].isdigit() and f[:3] < cur:
                earlier += io.open(os.path.join(vdir, f), encoding="utf-8").read()
        POST = ["管", "派", "登记", "盖", "看大门", "门房", "业务", "科", "炉", "烧",
                "师傅", "主任", "护", "医", "司机", "保安", "值班", "账", "库", "工",
                "修", "这行", "干这", "前上司", "手下"]
        for nm in names:
            if nm in earlier:
                continue
            for i, line in enumerate(lines, 1):
                if nm in line:
                    # 主角允许「先展示专业、再落身份」，按整章判；其余人物按出现处 9 行窗口
                    seg = body if nm == "沈砚" else "".join(lines[i - 1:i + 9])
                    if not any(w in seg for w in POST):
                        cand.append("人物首现无身份线索（4.10）：%s 全书首次出现在第 %d 行「%s」"
                                    % (nm, i, line.strip()[:26]))
                    break

    # ---------- 输出 ----------
    print("=" * 52)
    print("文件：%s" % path)
    print("标题：%s（%d 字）" % (m.group(2) if m else "?", len(m.group(2)) if m else 0))
    print("字数：%d（目标 2000 / 上限 2500 / 下限 1700）" % n)
    print("台词：%d 条" % len(all_lines))
    print("=" * 52)

    if hard:
        print("\n[硬指标] %d 条，确定是错" % len(hard))
        for e in hard:
            print("  x " + e)

    if cand:
        cand.sort(key=lambda x: 0 if "★裸" in x else 1)
        print("\n[待判] %d 条，交审读层判断（★=裸台词，优先处理）" % len(cand))
        for w in cand:
            print("  - " + w)
        print("\n  以上不是错误清单，是候选清单。逐句判：提问／复述求证／反问／陈述。")
    elif not hard:
        print("\n粗筛无候选。仍需跑审读层——本层只能看见形态，看不见语义。")

    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
