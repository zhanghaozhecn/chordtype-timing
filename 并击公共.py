#!/usr/bin/env python3
"""
并击公共.py — 分析脚本共用口径 (口径唯一来源, 防止脚本间漂移)
含: TSV 读取 / 分段量提取 / 序号块稳定期边界 / 分位 / 参考组合 / 拼读并击在用组合表
口径定义见 README §4.1（三段）、§5（稳定期）、§4.4（剔除）
"""
from pathlib import Path
import math
import numpy as np

BASE = Path(__file__).parent
LEFT, RIGHT = 'qwertasdfgzxcvb', 'yuiophjkl;nm,./'
LEFT_SET, RIGHT_SET = set(LEFT), set(RIGHT)

# ── 键盘几何与组合空间 (口径唯一来源: 采集/分析脚本共用; 约束①② 见 README §4.1) ──
import itertools
ROWS = ['qwertyuiop', 'asdfghjkl;', 'zxcvbnm,./']
KEY_POS = {c: (r, i) for r, row in enumerate(ROWS) for i, c in enumerate(row)}
COL_FINGER_L = {0: 0, 1: 1, 2: 2, 3: 3, 4: 3}   # 左手列→指: 小无中食食
COL_FINGER_R = {5: 4, 6: 4, 7: 5, 8: 6, 9: 7}   # 右手列→指: 食食中无小
MAX_ROW_D = 1                                    # 约束②: 跨行 ≤1

def _valid_combos(keys, col_finger):
    """该手全部合法组合: 15 单键 + 满足约束①②的双键 (canonical 键盘序)"""
    out = list(keys)
    for a, b in itertools.combinations(keys, 2):
        (ra, ca), (rb, cb) = KEY_POS[a], KEY_POS[b]
        if col_finger[ca] != col_finger[cb] and abs(ra - rb) <= MAX_ROW_D:
            out.append(a + b)
    return out
LEFT_COMBOS = _valid_combos(LEFT, COL_FINGER_L)      # 78
RIGHT_COMBOS = _valid_combos(RIGHT, COL_FINGER_R)    # 78

# 3 键组合 (sdf 左 / jkl 右): 同排三指顺指, 各手**唯一** 3 键组合。
# 2026-09-30 用户决策: 它**不再是判定的参考锚** —— 采样与 2 键同比例 (采集工具 REF_BOOST 取消),
#   数据作为副产品存在; 判定改为"同角色、同键数的组合总体中心" (见 role_ref_vals / REF_MODE_DEFAULT)。
#   保留常量的理由: ① 组合空间自测断言"唯一 3 键"; ② 通用模型留一个 3 键数据点。
REF_COMBO = {'l': 'sdf', 'r': 'jkl'}
LEFT_COMBOS.append(REF_COMBO['l'])
RIGHT_COMBOS.append(REF_COMBO['r'])                  # → 各 79 (78 + 1 三键)

# 击结构 (|左|,|右|) 采样权重 — 近似实用击型分布 (README §4.4)
SIZE_WEIGHTS = {(1,1):24, (1,2):18, (2,1):16, (2,2):22, (1,0):10, (2,0):6, (0,1):8, (0,2):2}
# 单键:双键:三键 结构权重 (三键 = REF_COMBO, 2026-09-30 起不加权)
COMBO_W = {1: 2.0, 2: 1.0, 3: 1.0}

def _by_size(combos):
    d = {}
    for c in combos:
        d.setdefault(len(c), []).append(c)
    return d
_LEFT_BY_SIZE, _RIGHT_BY_SIZE = _by_size(LEFT_COMBOS), _by_size(RIGHT_COMBOS)

def sample_stroke(rng):
    """按实用击型分布采样一击 → (左组合, 右组合); 单手击的另一侧为 ''"""
    (nl, nr) = rng.choices(list(SIZE_WEIGHTS), weights=list(SIZE_WEIGHTS.values()), k=1)[0]
    L = rng.choice(_LEFT_BY_SIZE[nl]) if nl else ''
    R = rng.choice(_RIGHT_BY_SIZE[nr]) if nr else ''
    return L, R

# 稳定期边界方法常量 (口径移植自姊妹项目串击 `better-keystroke-timing` 的序号块口径)
BLOCK, BAND, REF_LAST, SMOOTH, MIN_BLOCKS = 100, 1.10, 5, 3, 8
# 稳定期边界判据 = **平台中心包络**（2026-10-11 用户决策, 移植自姊妹项目串击同日决策
# 「稳定期边界改用与水平解耦的判据」）: 上沿 = median(平台平滑值) + NSIG·1.4826·MAD(平台平滑值),
# 从相对带**种子边界**迭代至不动点。与旧相对带「平滑值 ≤ R×band」的区别: 上沿锚定**平台自身
# 分布中心**而非 R（快端统计量）—— R 随水平下降而下降、R×band 上沿跟着下降, 早期平台块会被
# 重新判成练习段（串击实测: 2键 R 62→60 使边界块[0]→块[12] 回摆）; 包络判据下平台没变边界
# 就不变（串击实测 1-2 轮收敛）。BAND 降级为**种子带宽**（只作迭代起点; 串击按码长分带
# {4:1.10, 3:1.10, 2:1.15}, 本项目分类型, 两类暂同带 1.10）。
NSIG = 3.0                                   # 包络宽度 (平台中心 + 3σ_b; 与串击同值)

# ── 错误成本: 指定常数 (2026-09-24 用户决策, 不再实测; README §4.2) ──────────
# 值 = 姊妹项目 击键测速 实测「错误修正时间」净成本 782.2ms (n=278 episode,
#   产物/错误修正时间-实测值.txt) 的移植锚, 非本机实测。
# 为什么不自己测 (用户 2026-09-07 判断 + 2026-09-24 定案):
#   · 不可分解: 纠错是整任务行为 (察觉跨手 + 退格 + 整击重打), 没有按键时间那样的
#     可加链式分解 → 单手数据推不出双手纠错;
#   · 直接测双手的代价过高: 连续键位图串读图成本大 (工具已备, 见 实验/, 不参与主线)。
# 两个反向偏差量级相抵, 故不校正: ① 重打单位是**整击** (比单键贵 → 偏高)
#   ② 每词错误机会 = 2 击 vs 串击 3 段 (机会少 → 偏低)。
# **方向性**: cost 越大越有利于并击 (错误机会更少) → 取实测锚而非更大的圆整数
#   (如 1000ms), 避免用常数美化本项目方案。
# 用法: 错误当量 = ERR_COST_MS × P_err (P_err 由 M1 主采集 error/err_type 列建模)。
# 兜底: M3 组装层必须对 ERR_COST_MS 做敏感性扫描 (0 / 400 / 782 / 1000 / 2000),
#   确认方案排名与结论不翻转 —— 这是"指定常数而不实测"的代价与验证方式。
ERR_COST_MS = 782.2

# 拼读并击在用组合 (说明书 251223 原始写法 → canonical 化), ●标记用
SCHEME_LEFT_RAW = ["zv","d","e","sd","w","sg","eg","xg","c","qf","t","f","xc","cv","af","wf","zf",
    "dg","cf","se","xd","b","x","wg","as","sf","v","xv","cg","z","er","ag","a","sr","df","sv",
    "r","dr","g","we","qr","dv","s","wr","qg","q","ef","xf","zg","av","ar"]
SCHEME_RIGHT_RAW = [";","U","L","J","N","UL","MK","IO","K","P","M","H","HO","HL","HI","J;","UK","M;",
    "J,",".","UI","/","M,","O","JP","HK",",.","JI","JO","UO","I","Y","H;","JK","J.","U;","M/",
    "KL","J/","ML","UP","M.","JL",","]
_canon = lambda c, keys: ''.join(sorted(c.lower(), key=keys.find))
SCHEME_L = {_canon(c, LEFT) for c in SCHEME_LEFT_RAW}
SCHEME_R = {_canon(c, RIGHT) for c in SCHEME_RIGHT_RAW}

def scheme_used(combo):
    """该组合是否被拼读并击方案使用 (剔除时的冲突提示)"""
    return combo in (SCHEME_L if set(combo) <= LEFT_SET else SCHEME_R)

def hand_of(combo):
    return 'l' if set(combo) <= LEFT_SET else 'r'

def read_tsv(path, required=("code", "session")):
    """读 TSV → [dict]; 跳过并发写入的半行。
    表头健全性检查 (required 列缺失 ⇒ 表头缺失/损坏, 明确报警而非静默错读)"""
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        first = f.readline().rstrip("\n")
        hdr = first.split("\t")
        if any(c not in hdr for c in required):
            print(f"⚠ {path.name} 表头异常 (首行非表头?): {first[:60]!r}\n"
                  f"  该文件不可解析, 请检查采集工具是否写入过表头")
            return []
        out = []
        for line in f:
            r = line.rstrip("\n").split("\t")
            if len(r) == len(hdr):
                out.append(dict(zip(hdr, r)))
        return out

def anchors(r, stroke, hand):
    """该击该手 (fd, ld, fu, lu) ms (缺失为 0.0)"""
    return tuple(float(r[f"{hand}{p}{stroke}"]) for p in ("fd", "ld", "fu", "lu"))

def hand_segments(r, hand):
    """单模式行的该手三段量 → dict; 该手缺任一击则 {}
      S1/S2/S3 = 三段 (词首占用/换手间隙/词尾占用), wc = S1+S2+S3 (词占用)
      spread1/spread3 = 两击成形散布 (ld−fd, 组合难度)
      combo1/combo2 = 两击组合串"""
    parts = r["code"].split("|")
    if len(parts) < 2:
        return {}
    side = LEFT_SET if hand == 'l' else RIGHT_SET
    c1 = ''.join(c for c in parts[0] if c in side)
    c2 = ''.join(c for c in parts[1] if c in side)
    if not c1 or not c2:
        return {}
    fd1, ld1, _, lu1 = anchors(r, 1, hand)
    fd2, ld2, _, lu2 = anchors(r, 2, hand)
    if lu1 <= 0 or lu2 <= 0:
        return {}
    return {"S1": lu1 - fd1, "S2": fd2 - lu1, "S3": lu2 - fd2, "wc": lu2 - fd1,
            "spread1": ld1 - fd1, "spread3": ld2 - fd2, "combo1": c1, "combo2": c2}

# 角色 × 指标 → hand_segments 字段名
ROLE_METRIC_KEY = {("S1", "spread"): "spread1", ("S3", "spread"): "spread3",
                   ("S1", "occ"): "S1", ("S3", "occ"): "S3"}

def trial_type(r):
    """1 = 一击试次 (孤立组合/一击词), 2 = 二击试次 (二字词); 0 = 不可解析"""
    parts = [p for p in r.get("code", "").split("|") if p]
    return len(parts) if parts else 0

def type_metric(r, hand):
    """该类型试次的稳定期边界指标 (README §3.5):
      1 击 → occ = lu−fd (孤立组合占用)
      2 击 → wc = lu2−fd1 (词占用)
    无效 (错误行/缺锚) → None"""
    t = trial_type(r)
    if t == 1:
        a = anchors(r, 1, hand)
        return a[3] - a[0] if a[3] > 0 else None      # occ = lu − fd (只用到首末锚)
    if t == 2:
        return hand_segments(r, hand).get("wc")
    return None

def split_by_type(rows, hand):
    """rows → {1: [(行序, metric)], 2: [(行序, metric)]} (仅有效行; 保持试次类型内的时间序)"""
    out = {1: [], 2: []}
    for i, r in enumerate(rows):
        if r.get("error") != "0":
            continue
        v = type_metric(r, hand)
        if v is not None:
            out[trial_type(r)].append((i, v))
    return out

def stable_by_type(rows, hand, block=BLOCK, min_blocks=MIN_BLOCKS):
    """**分类型**稳定期 (混采协议, README §3.5)。两类试次时间尺度不同 → 各自跑边界方法;
    少数类样本不足以自成边界时, 按主类的稳定起点**同截归属** (姊妹项目做法:
    少数类型不参与边界计算, 按时间序自稳定起点同截)。
    → {类型: {"method": "own"/"shared"/None, "cut_row": 全局截断行号,
              "stable": [全局行号…], "msg": 摘要}}"""
    seqs = split_by_type(rows, hand)
    own, scored = {}, {}
    for t, seq in seqs.items():
        vals = [v for _, v in seq]
        if len(vals) // block < min_blocks:
            continue
        start, msg = stable_start(vals, block=block, min_blocks=min_blocks)
        if start is not None:
            own[t] = (seq[start][0], msg)                      # (全局行号, 摘要)
            scored[t] = len(vals)
    main = max(scored, key=scored.get) if scored else None          # 主类 = 样本最多且有边界者
    cut = own[main][0] if main is not None else None
    out = {}
    for t, seq in seqs.items():
        if t in own:
            row0, msg = own[t]
            out[t] = {"method": "own", "cut_row": row0,
                      "stable": [i for i, _ in seq if i >= row0],
                      "msg": f"{msg} | 该类试次 n={len(seq)}"}
        elif cut is not None:
            st = [i for i, _ in seq if i >= cut]
            out[t] = {"method": "shared", "cut_row": cut, "stable": st,
                      "msg": f"样本不足自成边界 → 按主类({main}击)稳定起点同截 | "
                             f"该类试次 n={len(seq)}, 稳定期 {len(st)}"}
        else:
            out[t] = {"method": None, "cut_row": None, "stable": [],
                      "msg": f"数据不足 ({len(seq)} 试次, 需 {min_blocks*block}+) 且无主类边界可借"}
    return out

def stable_rows(rows, hand):
    """分类型稳定期的并集行集合 (建模用) → (行序集合, {类型: 摘要})"""
    st = stable_by_type(rows, hand)
    rows_set = set()
    for t in st:
        rows_set.update(st[t]["stable"])
    return rows_set, st

def word_occ(r, hand):
    """该手词占用 wc = lu2 − fd1 (稳定期边界指标); 无效 → None"""
    return hand_segments(r, hand).get("wc")

def _band_boundary(vals, block, band, ref_last, smooth):
    """旧相对带边界 (现只作包络的**种子**): → (k, R, nb)。
    k=None: 块数<2 (数据不足); k==nb: 末块即超带 (退化)。"""
    nb = -(-len(vals) // block)
    if nb < 2:
        return None, None, nb
    med = np.array([np.median(vals[b*block:(b+1)*block]) for b in range(nb)])
    sm = np.array([np.median(med[max(0, i-smooth+1):i+1]) for i in range(nb)])
    R = float(np.median(sm[-ref_last:]))
    k = nb
    while k - 1 >= 0 and sm[k-1] <= R * band:
        k -= 1
    return k, R, nb

def _block_boundary_envelope(vals, block, seed_band, ref_last, smooth, nsig=NSIG,
                             max_iter=10):
    """平台中心包络边界（与水平解耦, 2026-10-11 用户决策; 移植自姊妹项目串击
    `分析-按键时间.py._block_boundary_envelope` 同名函数, 不另立口径）:
    块中位 → smooth 滚动中位 → 从种子边界（相对带）迭代:
      c = median(平台平滑值), σ_b = 1.4826·MAD(平台平滑值), 上沿 = c + nsig·σ_b,
      新边界 = 自末向前最早连续 ≤ 上沿 的块, 至不动点（实测 1-2 轮收敛）。
    σ_b 必须在**平滑值**上测（原始块中位的 MAD 被平台自身散布抬高, 会把练习段放进来）。
    返回 (k, R, nb, c, sig, edge); nb<2 → (None,None,nb,None,None,None);
    数据不足/末块超带时退化沿用种子结果 (c/sig/edge = None)。"""
    nb = -(-len(vals) // block)
    if nb < 2:
        return None, None, nb, None, None, None
    med = np.array([np.median(vals[b*block:(b+1)*block]) for b in range(nb)])
    sm = np.array([np.median(med[max(0, i-smooth+1):i+1]) for i in range(nb)])
    R = float(np.median(sm[-ref_last:]))
    k0, _, _ = _band_boundary(vals, block, seed_band, ref_last, smooth)
    if k0 is None or k0 >= nb:                       # 退化 (数据不足/末块超带)
        return k0, R, nb, None, None, None
    k = k0
    c = sig = edge = None
    for _ in range(max_iter):
        plat = sm[k:]
        c = float(np.median(plat))
        sig = float(1.4826 * np.median(np.abs(plat - c)))
        if sig <= 0:                                 # 平台全等值 (理论罕见): 退回 SD
            sig = float(np.std(plat, ddof=1)) or 1.0
        edge = c + nsig * sig
        kn = nb
        while kn - 1 >= 0 and sm[kn-1] <= edge:
            kn -= 1
        if kn == k:
            break
        k = kn
    return k, R, nb, c, sig, edge

def stable_start(vals, block=BLOCK, band=BAND, ref_last=REF_LAST, smooth=SMOOTH,
                 min_blocks=MIN_BLOCKS):
    """序号块稳定期边界 → (起始下标 or None, 摘要串)
    判据 = **平台中心包络**（与水平解耦, 2026-10-11 用户决策, 移植自串击）:
    上沿 = median(平台平滑值) + NSIG·1.4826·MAD(平台平滑值), 从相对带种子边界迭代至不动点;
    `band` 降级为种子带宽（传旧值即可复现旧相对带对照的种子步骤, 包络仍会迭代）。"""
    nb = -(-len(vals) // block)
    if nb < min_blocks:
        return None, f"块数 {nb} < {min_blocks} (数据不足 {len(vals)}, 需 ~{min_blocks*block})"
    k, R, nb, c, sig, edge = _block_boundary_envelope(vals, block, band, ref_last, smooth)
    if k is None:
        return None, f"块数 {nb} < 2 (数据不足 {len(vals)})"
    if k >= nb:
        return None, f"末块即超带 (退化): 块数 {nb}, 参考 R={R:.0f}ms"
    start = k * block
    med = np.array([np.median(vals[b*block:(b+1)*block]) for b in range(nb)])
    slope = float(np.polyfit(np.arange(nb), med, 1)[0])
    drift = (med[0] - R) / R * 100 if R else 0.0
    tail = (f"σ_b={sig:.1f} 平台中心={c:.0f} 上沿={edge:.0f}ms (包络, 种子带 {band:.2f})"
            if sig is not None else f"种子带 {band:.2f} (退化, 无包络)")
    return start, (f"块数 {nb} ({block}/块) | 稳定期起始行 {start} (块 {k+1}) | "
                   f"稳定期样本 {len(vals)-start} | 首块中位 {med[0]:.0f} → R {R:.0f}ms "
                   f"(漂移 {drift:+.0f}%) | 斜率 {slope:+.1f}ms/块 | {tail}")

def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]

# ═══════════════ 角色 (段位) 模型: 剔除判据的唯一来源 (README §4.4, 2026-09-24) ═══════════════
# 口径: 击内 spread/occ 有**共用部分** (组合本身的成形难度) + **段位效应** (孤立/词首/词尾
# 的上下文差)。所以不按角色分家, 也不整体合并, 而是: **每个角色内与"同角色参考水平"配对求 log 比
# ⇒ 段位效应在差值里自动抵消**, 再把各角色的 log 比按权重平均 ⇒ 组合效应可用全部角色的样本。
# 一击数据必须参与 (孤立位置 = 一击词/一级字/简词的真实用法), 重要性 1击:2击 = 1:2。
# **参考水平** (2026-09-30 用户决策): 默认 = 判定对象总体 (该手 2 键组合) 在该角色的样本中位
#   (pooled); 旧口径 (参考组合 sdf/jkl) 降为 `--ref sdf` 对照。判定**不再依赖 sdf 的时间**。
ROLES = ("iso", "S1", "S3")                 # 孤立 (1 击试次) / 词首 / 词尾
ROLE_GROUP = {"iso": "one", "S1": "two", "S3": "two"}
IMPORTANCE_ONE_TWO = (1, 2)                 # 1 击组 : 2 击组 的权重比 (用户 2026-09-24 定)
MIN_ROLE_N = 5                              # 单个角色进入综合比值所需的最小样本
REF_MODE_DEFAULT = "pooled"                 # 参考水平口径: pooled (全体组合中心) | sdf (旧锚, 对照)
REF_MODES = ("pooled", "sdf")
Z_FWER = 3.46                               # 189 判定单元族错误率 5% 对应的 z (自适应阈值用)
SIGMA_LOG_FALLBACK = 0.87                   # log 尺度 sd 兜底 (无数据时; spread 口径)
# 各指标的无数据兜底 σ (2026-09-30 实测, 与 实验/实验-方差分解.py 同法取数):
#   spread (ld−fd 成形难度) σ_resid ≈ 0.87 (S1) → 兜底 0.87
#   occ    (lu−fd 整击占用) σ_resid ≈ 0.13 (S1 单独) ~ 0.19 (三角色合并) → 取保守的 0.19
METRIC_SIGMA_FALLBACK = {"spread": SIGMA_LOG_FALLBACK, "occ": 0.19}

def sigma_fallback(metric="spread"):
    """该指标 log 尺度的兜底 σ (无数据/样本不足时用)"""
    return METRIC_SIGMA_FALLBACK.get(metric, SIGMA_LOG_FALLBACK)

def role_ref_vals(vals, hand, combos=None, mode=REF_MODE_DEFAULT):
    """该手各角色的**参考样本** → {role: [值]} (口径唯一来源: "参考水平"只能在这里定义)
      mode="pooled" (默认, 2026-09-30 用户决策): 参考 = **判定对象总体** (combos = 该手 2 键组合)
        在该角色的全部样本。语义 = "同角色、同键数的全体组合中心";
        · 段位效应在"同角色比值"里抵消, 共同漂移在比值里自动抵消;
        · 参考由全体组合测量 ⇒ n 远大于单组合锚 ⇒ 阈值里的参考噪声项 ≈0 (阈值更紧);
        · 自包含 (含被判组合自身, 权重 ~1/63) ⇒ 偏差方向 = 略低估偏离 = **保守**。
      mode="sdf": 参考 = REF_COMBO[hand] (v2.13 旧口径, 只作对照; 2026-09-30 起它不加权采样)
    """
    if mode == "sdf":
        return {role: vals.get((hand, role, REF_COMBO[hand]), []) for role in ROLES}
    combos = combos if combos is not None else two_key_combos(hand)
    return {role: [x for c in combos for x in vals.get((hand, role, c), [])] for role in ROLES}

def iso_segment(r, hand):
    """孤立角色 (1 击试次的该手单击) → {"combo","spread","occ"}; 非 1 击行/该手无键 → {}
    刻意与 hand_segments 分开: 后者对 1 击行返回 {} 是**多脚本依赖的契约** (熟练度/数据检查
    以 {} 表示"该行无二击段"), 不能在那里就地改语义。"""
    parts = [p for p in (r.get("code", "") or "").split("|") if p]
    if len(parts) != 1:
        return {}
    side = LEFT_SET if hand == 'l' else RIGHT_SET
    c = ''.join(ch for ch in parts[0] if ch in side)
    if not c:
        return {}
    fd, ld, _, lu = anchors(r, 1, hand)
    if lu <= 0:
        return {}
    return {"combo": c, "spread": ld - fd, "occ": lu - fd}

def role_segments(r, hand, metric="spread"):
    """该行该手全部可判定角色 → [(role, combo, 值)] (错误行 → [])
    2 击行 → S1/S3; 1 击行 → iso。所有剔除/诊断取数都走这里, 保证角色枚举唯一。"""
    if r.get("error", "0") != "0":
        return []
    seg = hand_segments(r, hand)
    if seg:
        return [(role, seg["combo1" if role == "S1" else "combo2"],
                 seg[ROLE_METRIC_KEY[(role, metric)]]) for role in ("S1", "S3")]
    s = iso_segment(r, hand)
    return [("iso", s["combo"], s[metric])] if s else []

def role_weights(counts, importance=IMPORTANCE_ONE_TWO):
    """各角色样本数 → 权重: 让 1 击组与 2 击组的总权重 = 重要性比 (默认 1:2),
    组内按样本数分配。⇒ 孤立角色按"重要性"加权, 而非仅按它可怜的样本量。"""
    tot = {g: sum(n for r, n in counts.items() if ROLE_GROUP[r] == g) for g in ("one", "two")}
    return {r: (n / tot[ROLE_GROUP[r]] * importance[0 if ROLE_GROUP[r] == "one" else 1]
                if tot[ROLE_GROUP[r]] else 0.0)
            for r, n in counts.items()}

def joint_log_ratio(vals, ref_vals, weights=None, min_role_n=MIN_ROLE_N):
    """**综合比值** (共享击内效应 + 段位抵消):
      各角色内 log(med(组合)/med(同角色参考)) 按权重平均 → exp(...) 倍比。
    段位效应 b_role 在配对差值里抵消 (组合与参考同角色), 故无需拟合角色系数,
    但组合效应可用到全部角色的样本量 ⇒ n_eff 远大于单角色。
      vals / ref_vals: {role: [值]};  weights: {role: w} (默认按样本数)
    → (ratio, n_eff, detail) ; detail = {role: (n, med, ref_med, ratio)}; 无可用角色 → None"""
    detail, num, den, var = {}, 0.0, 0.0, 0.0
    for role, v in sorted(vals.items()):
        rv = ref_vals.get(role, [])
        if len(v) < min_role_n or len(rv) < min_role_n:
            continue
        m, mr = pct(v, 0.5), pct(rv, 0.5)
        if m <= 0 or mr <= 0:                       # 单键组合 spread≡0 → 该角色不可用
            continue
        w = (weights or {}).get(role, len(v))
        if w <= 0:
            continue
        detail[role] = {"n": len(v), "med": m, "n_ref": len(rv), "med_ref": mr, "ratio": m / mr}
        num += w * math.log(m / mr)
        den += w
    if not detail:
        return None
    for role, d in detail.items():                  # n_eff: 中位数方差 (1.253σ)²/n 的加权合成
        w = (weights or {}).get(role, d["n"]) / den
        var += w * w * (1.0 / d["n"] + 1.0 / d["n_ref"])
    n_eff = 1.0 / var if var > 0 else 0.0
    return math.exp(num / den), n_eff, detail

def margin_adaptive(n, sigma, z=Z_FWER):
    """随样本量自适应的阈值**倍数** (README §4.4/§6.2-6): 固定 margin=1.0 在零假设下恒约
    50% 越线, 不是判据; 阈值必须 >= 中位估计的抽样噪声 ⇒
        margin = exp(z · 1.253σ/√n)      ← **乘性**形式 (log 尺度上是 z·SE)
    (写成 1 + z·SE 是错的: z·SE 大时严重低估阈值 —— 实测误剔数高数倍)
    n 用 joint_log_ratio 返回的**有效样本量 n_eff** (已含参考那一侧的噪声)"""
    return math.exp(z * 1.253 * sigma / math.sqrt(max(1.0, n)))

def margin_adaptive2(n_c, n_ref, sigma, z=Z_FWER):
    """单角色判据的两侧阈值倍数: 组合与**参考**的中位估计各有噪声, 比的是两者之差 ⇒
        margin = exp(z · 1.253σ · √(1/n_c + 1/n_ref))
    (只按组合的 n 算会漏掉参考的噪声 ⇒ 阈值过松)"""
    return math.exp(z * 1.253 * sigma * math.sqrt(1.0 / max(1.0, n_c) + 1.0 / max(1.0, n_ref)))

def sigma_of_log(vals, metric="spread"):
    """一组正值样本在 log 尺度的 sd (**pooled**; 样本不足 → 该指标兜底值)。
    ⚠ 作阈值时应优先用 `sigma_within_log`: pooled 把组合/段位/会话差异都算进噪声 ⇒ 阈值偏宽"""
    lg = [math.log(x) for x in vals if x > 0]
    if len(lg) < 10:
        return sigma_fallback(metric)
    m = sum(lg) / len(lg)
    return math.sqrt(sum((x - m) ** 2 for x in lg) / (len(lg) - 1))

def sigma_within_log(vals_by_cell, min_n=3, min_df=10):
    """**单元内（残差）sd** —— 中位数抽样 SE 该用的 σ（2026-09-24 方差分解结论）:
    pooled sd 含 组合/段位/会话 差异, 用它算阈值会偏宽（实测偏宽 5~7%）→ 漏剔真难组合。
    做法 = 各 (组合, 角色) 单元内部 sd 的池化（单元样本 < min_n 不参与; df 不足 → 退回 pooled）"""
    ss, df = 0.0, 0
    for v in vals_by_cell.values():
        lg = [math.log(x) for x in v if x > 0]
        if len(lg) < min_n:
            continue
        m = sum(lg) / len(lg)
        ss += sum((x - m) ** 2 for x in lg)
        df += len(lg) - 1
    if df < min_df:
        return None
    return math.sqrt(ss / df)

# ═══════════════ 选码配额: 78 → ≤52 (2026-10-11 用户决策, 由 60 收紧; 原始决策 2026-09-30) ═══
# 需求: 单手组合空间 = 79 (78 + 唯一 3 键组合 sdf/jkl); 78 = 15 单键 + 63 双键。
#   方案单手最多 **52** 个码位 (15 单键 + 37 双键) ⇒ 从 63 双键里取 ≤37 用于方案, 淘汰 26。
#   (这是通用模型的一个**用量**; 模型本身不承担任何具体方案的覆盖需求。
#    方案兼容性核对 2026-10-11: 拼读并击 左手需双键 36 ≤ 37 (余 1) / 右手 29 ≤ 37 (余 8)。)
#   · 单键在 spread 口径下恒 ≡0 (单指无成形难度) 且一级字/简词必需 ⇒ **单键默认全留**
#     ⇒ 配额落在双键: 63 里留 37、淘汰 26。
#   · 排序量 = **occ (整击占用 lu−fd, "这个组合实际花掉的时间")**, 不是 spread:
#     实测 σ_resid 0.19 vs 0.87 (2026-09-30, 实验/实验-方差分解.py) ⇒ 同样本量下
#     两两可辨 1.30× vs 3.34× (n=20/角色) ⇒ 只有 occ 才可能"采集早期就确定淘汰"。
#     spread 保留为"成形难度/舒适度"诊断列 (难度异常判据仍用它)。
#   · 判据三层 (阶梯: 证据越足、动作越硬 —— 2026-09-30 用户决策):
#       ① 配额切分 (quota_cut, 按 occ 比升序切在第 37 名) —— 给出"要淘 26 个"的**名单**;
#       ② 保守淘汰 (dominator_count: 有 **37** 个组合显著更优 ⇒ 确定出局) ⇒ 硬剔 (不可逆);
#       ③ **软降权** (soft_*): 疑似出局但未确定 ⇒ 只把采样权重乘一个系数 (可回滚)。
#     三档的测量口径完全一致: 同角色参考配对 + 1击:2击 = 1:2 权重。
#   · 为什么软层门槛可以更宽 (SOFT_N_MIN < n_min): 硬剔不可逆 ⇒ 要 ② 的强证据;
#     降权只是少采一点、随时能回滚 ⇒ 可用"点估计排名"这种弱证据提前减预算。
#   · 52 配额的额外红利 (2026-10-11 目标函数分析): 割线移进排序曲线更陡段 (37/38 名差
#     > 44/45 名差) ⇒ 割线更易辨; J 收益 +7.11 ms/词 (vs 留45 +4.97)。
SINGLES_PER_HAND = sum(1 for c in LEFT_COMBOS if len(c) == 1)
TWO_KEY_PER_HAND = sum(1 for c in LEFT_COMBOS if len(c) == 2)
assert (SINGLES_PER_HAND, TWO_KEY_PER_HAND) == (15, 63), \
    f"组合空间变了 (单键 {SINGLES_PER_HAND} / 双键 {TWO_KEY_PER_HAND}) ⇒ 配额常数需复核"
QUOTA_MAX_CODES = 52                                     # 方案单手最多码位数 (v3, 2026-10-11; 原 60)
QUOTA_KEEP_TWO_KEY = QUOTA_MAX_CODES - SINGLES_PER_HAND  # 37 = 双键保留数 (淘汰 26)

# ── 软降权 (③) 的口径 ─────────────────────────────────────────────────────────
SOFT_WEIGHT_DEFAULT = 0.25      # 疑似出局组合的采样权重倍数 (0 = 关闭软降权层)
SOFT_N_MIN_DEFAULT = 8          # 软降权的 n_eff 门槛 (硬剔 n_min 默认 20 ⇒ 软层更早生效)
SOFT_MARGIN_DEFAULT = 5         # 支配者带: 支配者 ≥ K − margin 也算疑似 (次要信号)
WEIGHT_TXT_NAME = "组合降权表.txt"

# ── 动作表的**写表门禁** (v2.20, 2026-09-30 闭环模拟结论) ──────────────────────────
# 依据 = 实验/实验-新口径样本量.py (把判据接回采样器的闭环模拟, 48 条链):
#   · 降权集在 **1000 试次/手** 时只有 ~78% 正确 (1500 试次 58%, 2500 试次 85%,
#     ≥4500 试次 94%) ⇒ 早写表会把点估计靠后的**好组合**也降权, 而这些组合的
#     样本量恢复不过来 (预算被抽走的那些轮次补不回来)。
#   · 实测代价: 早启动 (n_eff ≥ 8, ≈1000 试次就写) vs 不降权 ⇒ "保留码 occ 全达 ±5%"
#     晚 **50%**、±3% 晚 27%、"63/63 可排名"晚 50%; 等到 ① 能排名绝大多数双键
#     (**≈2000 试次/手**) 再写 ⇒ 这些里程碑 **+0%**。
#   ⇒ 门禁判据用"① 可排名的双键比例"(与样本量同向、与采样速率无关, 不写死试次数)。
QUOTA_WRITE_RANK_FRAC = 0.90    # 可排名 (n_eff ≥ --n-min) 的双键比例达该值才允许写动作表

def quota_write_gate(n_rankable, n_total=TWO_KEY_PER_HAND, frac=QUOTA_WRITE_RANK_FRAC):
    """动作表写表门禁 → (放行?, 说明)。样本不足阶段写表 = 用掷硬币的结果去改采样预算,
    而且**改错了补不回来** (见上方注释) ⇒ 宁可不写, 只出名单 (--dry-run 仍可随时看)。"""
    need = math.ceil(frac * n_total)
    return n_rankable >= need, f"① 可排名 {n_rankable}/{n_total} (放行线 ≥{need} = {frac:.0%})"

def dominator_band(dom_counts, keep_two_key=QUOTA_KEEP_TWO_KEY, margin=SOFT_MARGIN_DEFAULT):
    """支配者计数 → **疑似出局**集 (dom ≥ K − margin)。
    dom = 有多少个组合显著优于它 ⇒ dom ≥ K 即确定出局; 从 K−margin 起算"差一点就确定"。
    dom_counts = {combo: 支配者数}"""
    return {c for c, n in (dom_counts or {}).items() if n >= keep_two_key - margin}

def two_key_combos(hand):
    """该手参与配额排序的双键组合 (不含参考) —— 判定对象唯一来源"""
    combos = LEFT_COMBOS if hand == 'l' else RIGHT_COMBOS
    return [c for c in combos if len(c) == 2 and c != REF_COMBO[hand]]

# ── 左右镜像 (对称映射; 2026-10-01 用户提问引入) ─────────────────────────────────
# 背景: 并击方案普遍采用"左右手对称的组合→编码映射"(同一**指形**在两手承担对应码位),
#   所以方案采用的组合往往成镜像对。而剔除是**逐手**做的 (各自的 pooled 参考与 n_eff) ⇒
#   同一对组合左手可能进割线、右手不进 ⇒ 名单不镜像, 对称映射被破坏。
#   镜像的定义 = 键盘**列 9−col** (左右手同指、同行、同列距) —— 这是唯一的几何对偶。
# 结构事实 (自测断言): 左手 78 组合 ↦ 右手 78 组合是**双射**; 几何(行差)+手指(指位)特征
#   逐对一致; 三键参考 sdf ↔ jkl。⇒ "镜像对" 是良定义的判定单位。
_KEY_AT = {KEY_POS[ch]: ch for ch in "".join(ROWS)}
MIRROR_KEY = {ch: _KEY_AT[(r, 9 - c)] for ch, (r, c) in KEY_POS.items()}

def mirror_combo(c):
    """该组合的**对侧镜像** (左手→右手 / 右手→左手; 按键盘列 9−col; canonical 化到对侧键序)"""
    keys = RIGHT if hand_of(c) == 'l' else LEFT
    return ''.join(sorted((MIRROR_KEY[ch] for ch in c), key=keys.find))

def pair_id(c):
    """组合 → 它所属**镜像对**的 id (统一取左手 canonical 形式, 便于跨手汇总)"""
    return c if hand_of(c) == 'l' else mirror_combo(c)

def mirror_pairs():
    """镜像对表 → [(左手双键, 右手镜像)] (63 对; 顺序 = 左手键盘序) —— 对称映射的判定单位"""
    return [(c, mirror_combo(c)) for c in two_key_combos('l')]

def z_for(n_tests, alpha=0.05):
    """n_tests 个比较、族错误率 α (单侧) 对应的 z (Bonferroni)。
    序贯审阅时把审阅次数乘进 n_tests ⇒ 阈值自动收紧 (反复偷看不膨胀错误率)"""
    from statistics import NormalDist
    return NormalDist().inv_cdf(1.0 - alpha / max(1, n_tests))

def quota_cut(ranked, unrankable, keep_two_key=QUOTA_KEEP_TWO_KEY, sigma=SIGMA_LOG_FALLBACK,
              z_boundary=None, et=None):
    """**① 配额切分** (occ 比升序 = 快→慢, 越小越该留):
      ranked     = {combo: (ratio, n_eff)}  可排名者 (同角色参考配对的综合 occ 比)
      unrankable = set() 不可排名者 (样本不足) —— **不判不切**, 但它们占用保留名额
                   (数据不足时切 = 掷硬币, 宁可保留)
      sigma      = log 尺度 σ (只用于报告"割线两侧是否可辨")
      et         = {combo: 错误时间 ms} (**mot-only Et**, 2026-10-11 用户决策; None = 关闭)。
                   **割线平手决胜**: occ 不可辨的窗口内 (窗口 = 与割线两侧比值差都在
                   exp(se_gap) 噪声带内的连续段), 按 Et 升序重排 —— 错误项只在 occ 证据
                   无差别处说话 (理论目标函数 K = occ + P_err×C 的最小侵入落地形式)
    → (keep:set, cut:set, info:dict)   keep/cut 只含可排名者 (调用方把 unrankable 并入保留)
      info: n_rankable / n_unrankable / keep_slots / gap / se_gap / decisive / boundary / reason
            + tiebreak (dict: noise/window/changed/boundary_eff; 未触发 = None)
    """
    keep_slots = keep_two_key - len(unrankable)
    order = sorted(ranked, key=lambda c: (ranked[c][0], c))
    info = {"n_rankable": len(ranked), "n_unrankable": len(unrankable),
            "keep_slots": keep_slots, "gap": None, "se_gap": None, "decisive": None,
            "boundary": None, "reason": "", "tiebreak": None}
    if keep_slots <= 0:
        info["reason"] = (f"可排名 {len(ranked)} 个, 不可排名 {len(unrankable)} 个已占满 "
                          f"{keep_two_key} 个保留名额 ⇒ 数据不足, 本轮不切")
        return set(order), set(), info
    keep, cut = set(order[:keep_slots]), set(order[keep_slots:])
    if cut:
        c_last, c_next = order[keep_slots - 1], order[keep_slots]
        r1, n1 = ranked[c_last]
        r2, n2 = ranked[c_next]
        gap = math.log(r2) - math.log(r1)                      # ≥0 (升序)
        se = 1.253 * sigma * math.sqrt(1.0 / max(1.0, n1) + 1.0 / max(1.0, n2))
        zb = z_boundary if z_boundary is not None else z_for(max(1, len(ranked)))
        info.update(gap=gap, se_gap=se, decisive=bool(gap > zb * se), boundary=(c_last, c_next))
    # ── Et 平手决胜 (v2.36, 2026-10-11 用户确认): **仅割线不可辨时**, 窗口内按 Et 升序重排 ──
    if et and cut and info["se_gap"] is not None and not info["decisive"]:
        noise = math.exp(info["se_gap"])                       # 与报告的"噪声 ×"同源
        r_lo = ranked[info["boundary"][1]][0] / noise          # 窗口下沿 (割线后一侧 / 噪声)
        r_hi = ranked[info["boundary"][0]][0] * noise          # 窗口上沿 (割线前一侧 × 噪声)
        window = [c for c in order if r_lo <= ranked[c][0] <= r_hi]
        if len(window) > 1:
            win_sorted = sorted(window, key=lambda c: (et.get(c, float("inf")), c))
            i0 = order.index(window[0])
            new_order = order[:i0] + win_sorted + order[i0 + len(window):]
            keep_new = set(new_order[:keep_slots])
            changed = [(c, "保留" if c in keep else "淘汰",
                        "保留" if c in keep_new else "淘汰")
                       for c in window if (c in keep) != (c in keep_new)]
            keep, cut = keep_new, set(new_order[keep_slots:])
            info["tiebreak"] = {
                "noise": noise, "window": window,
                "changed": changed,
                "boundary_eff": (new_order[keep_slots - 1], new_order[keep_slots])
                if keep_slots <= len(new_order) else None,
                "reason": (f"occ 不可辨 (噪声 {noise:.3f}×) ⇒ 窗口 {len(window)} 名按 "
                           f"错误时间 Et 升序决胜; 名单变化 {len(changed)} 个")}
    info["reason"] = (f"可排名 {len(ranked)} (留 {len(keep)} / 淘 {len(cut)}) + "
                      f"不可排名 {len(unrankable)} (保留, 不判不切)")
    return keep, cut, info

def dominator_count(combo, vals_by_combo, sigma, z, min_role_n=MIN_ROLE_N):
    """**② 保守淘汰** (可选开关): 有多少个组合**显著优于** combo。
      显著 = 同角色配对 log 比 > margin_adaptive(n_eff, σ, z) (配对差里段位效应抵消);
      不可判的配对 (样本不足/无共同可用角色) **不计数** ⇒ 保守 (宁可漏淘, 不误淘)。
      vals_by_combo = {combo: {role: [值]}}
    → (count, hits=[(j, ratio, n_eff)…])"""
    cv = vals_by_combo.get(combo) or {}
    if not cv:
        return 0, []
    count, hits = 0, []
    for j, jv in sorted(vals_by_combo.items()):
        if j == combo:
            continue
        counts = {r: len(cv.get(r, [])) + len(jv.get(r, [])) for r in set(cv) | set(jv)}
        res = joint_log_ratio(cv, jv, weights=role_weights(counts), min_role_n=min_role_n)
        if res is None:
            continue
        ratio, n_eff, _ = res
        if ratio > margin_adaptive(n_eff, sigma, z):
            count += 1
            hits.append((j, ratio, n_eff))
    return count, hits

def selftest_quota():
    """选码配额口径自测 (纯函数, 不依赖真实数据):
    割线正确 / 不可排名者被保护 / 数据不足不切 / 边界可辨性 / Bonferroni z / 支配者计数"""
    import random
    rs = random.Random(5)
    C = TWO_KEY_PER_HAND
    # (a) 割线: 前 37 快、后 26 慢 1.6× → 切掉的必是后 26 个
    ranked = {f"c{i:02d}": (math.exp(0.0 if i < QUOTA_KEEP_TWO_KEY
                                     else math.log(1.6) + rs.gauss(0, 0.02)), 50.0)
              for i in range(C)}
    keep, cut, info = quota_cut(ranked, set(), sigma=0.19)
    assert len(keep) == QUOTA_KEEP_TWO_KEY and len(cut) == C - QUOTA_KEEP_TWO_KEY, info
    assert all(int(c[1:]) >= QUOTA_KEEP_TWO_KEY for c in cut), sorted(cut)
    assert info["decisive"] is True, info
    # (b) 不可排名者占名额: 保留名额相应减少, 且它们不被切
    un = {f"c{i:02d}" for i in range(10)}
    keep2, cut2, info2 = quota_cut({c: v for c, v in ranked.items() if c not in un}, un, sigma=0.19)
    assert len(keep2) == QUOTA_KEEP_TWO_KEY - 10 and not (cut2 & un) \
        and len(cut2) == C - QUOTA_KEEP_TWO_KEY, info2
    # (c) 数据不足 (不可排名者已超名额) → 一个都不切
    _, cut3, info3 = quota_cut({}, {f"c{i:02d}" for i in range(50)})
    assert not cut3 and info3["keep_slots"] < 0, info3
    # (d) 边界不可辨: 相邻名次差 1% 而噪声大 → decisive False
    ranked4 = {f"c{i:02d}": (math.exp(0.01 * i), 10.0) for i in range(C)}
    _, _, info4 = quota_cut(ranked4, set(), sigma=0.19)
    assert info4["decisive"] is False, info4
    # (e) Bonferroni z: 189 单元 ≈ 现用 Z_FWER; 测试越多越严
    assert abs(z_for(189) - Z_FWER) < 0.02, z_for(189)
    assert z_for(2000) > z_for(189) > z_for(1) > 1.6, [z_for(n) for n in (1, 189, 2000)]
    # (f) 支配者带 (软降权 ③): dom ≥ K−margin 才进疑似; K 以上本就是硬剔
    dom = {f"c{i:02d}": i for i in range(0, 55)}         # dom 0..54
    band = dominator_band(dom, keep_two_key=45, margin=5)  # dom ≥ 40
    assert band == {f"c{i:02d}" for i in range(40, 55)}, sorted(band)
    assert not dominator_band({}, 45) and not dominator_band({"zz": 39}, 45)
    assert SOFT_N_MIN_DEFAULT < 20 and 0 < SOFT_WEIGHT_DEFAULT < 1   # 软层比硬剔更宽松且非零
    # (g) 支配者计数: 一个明显慢的 → 几乎全部显著更优; 一个正常的 → 0
    vals = {f"c{i:02d}": {"S1": [100.0 * (1.6 if i == 0 else 1.0) * math.exp(0.19 * rs.gauss(0, 1))
                                for _ in range(50)]} for i in range(C)}
    n_dom, _ = dominator_count("c00", vals, 0.19, z_for(2000))
    assert n_dom >= 55, n_dom
    assert dominator_count("c01", vals, 0.19, z_for(2000))[0] == 0
    # (g) 兜底 σ 按指标分开 (occ 不能沿用 spread 的 0.87)
    assert sigma_fallback("occ") < sigma_fallback("spread") and sigma_of_log([], "occ") == 0.19
    # (h) 写表门禁 (v2.20): 样本不足不放行 (含"一个都排不出"的现状), 63/63 或 ≥90% 放行
    ok0, msg0 = quota_write_gate(0)
    assert not ok0 and not quota_write_gate(56)[0] and quota_write_gate(57)[0]
    assert quota_write_gate(C)[0] and "≥57" in msg0 and "0/63" in msg0, (ok0, msg0)
    # (i) 左右镜像 (对称映射的判定单位): 双射 / 对合 / 参考对偶 / 63 对
    assert all(MIRROR_KEY[ch] in RIGHT_SET for ch in LEFT_SET), "镜像应把左手键映到右手键"
    _l78 = {c for c in LEFT_COMBOS if c != REF_COMBO['l']}
    assert {mirror_combo(mirror_combo(c)) for c in _l78} == _l78, "镜像应为对合"
    assert {mirror_combo(c) for c in _l78} == {c for c in RIGHT_COMBOS if c != REF_COMBO['r']}, \
        "78 组合应镜像双射"
    assert mirror_combo(REF_COMBO['l']) == REF_COMBO['r'] and len(mirror_pairs()) == C
    assert pair_id(pair_id('qg')) == 'qg' and pair_id(mirror_combo('qg')) == 'qg'
    print("选码配额自测通过: 割线/不可排名者保护/数据不足不切/边界可辨性/z_for/支配者计数/兜底σ/"
          "写表门禁/左右镜像")

# ── 段级异常剔除 (MAD 单侧上围栏; 移植自 击键测速 分析-按键时间.mad_filter_segments) ──
# 口径: **异常只可能偏大** —— 注意力中断/失手/抢跑只让段变慢, 不会让它变快 ⇒ 单侧上围栏
# (双侧公式的 MAD 下界在右偏分布下恒为负, 实测下侧剔除恒 0, 与单侧数值等价)。
# 分桶 = (角色, 击内键数): 两维上尺度都不同 (iso/S1/S3 水平不同; 单键/双键/参考键数不同)。
# 桶内样本不足 → 不设栏 (宁可漏剔, 不误删基准键对)。
MAD_K = 3.0
MAD_SCALE = 1.4826        # MAD → σ 的一致性系数 (正态下)
MAD_MIN_N = 8             # 桶内最小样本 (不足则不设栏)

def segment_rows(rows, hand, metric="spread"):
    """该手全部有效段 → [(行序 i, role, combo, n_keys, 值)] (错误行/零值跳过后)"""
    from collections import defaultdict as _dd           # 局部导入避免顶层再引一次
    out = []
    for i, r in enumerate(rows):
        for role, combo, v in role_segments(r, hand, metric):
            if v and v > 0:
                out.append((i, role, combo, len(combo), float(v)))
    return out

def mad_upper_fence(vals, k=MAD_K, min_n=MAD_MIN_N):
    """单侧上围栏 = med + k·1.4826·MAD; 样本不足 → inf (不设栏)"""
    if len(vals) < min_n:
        return float("inf")
    med = pct(vals, 0.5)
    mad = pct([abs(v - med) for v in vals], 0.5)
    return med + k * MAD_SCALE * mad

def mad_filter(segs, k=MAD_K, min_n=MAD_MIN_N):
    """段级单侧围栏剔除 → (保留, 剔除, 各桶围栏 {(角色,键数): fence})"""
    from collections import defaultdict as _dd
    by = _dd(list)
    for s in segs:
        by[(s[1], s[3])].append(s[4])
    fences = {bk: mad_upper_fence(v, k, min_n) for bk, v in by.items()}
    keep = [s for s in segs if s[4] <= fences[(s[1], s[3])]]
    drop = [s for s in segs if s[4] > fences[(s[1], s[3])]]
    return keep, drop, fences

def selftest_roles():
    """角色模型自测: (a) 段位效应抵消 (b) 1:2 权重 (c) n_eff 合成 (d) 单键 spread=0 剔除"""
    # (a) 组合×0.5, 参考同分布, 但三角色段位差极大 (iso 低 2 倍、S3 高 2 倍)
    vals = {"iso": [10.0] * 20, "S1": [20.0] * 20, "S3": [40.0] * 20}
    ref = {"iso": [20.0] * 20, "S1": [40.0] * 20, "S3": [80.0] * 20}
    ratio, n_eff, detail = joint_log_ratio(vals, ref)
    assert abs(ratio - 0.5) < 1e-9, ratio          # 三角色都是 0.5 倍 ⇒ 综合必为 0.5
    assert abs(n_eff - 30) < 1.0, n_eff            # 3角色×20 样本与同规模锚比 ⇒ n_eff = 20×3/2
    assert len(detail) == 3 and detail["iso"]["n_ref"] == 20
    # (b) 1:2 重要性权重: iso 独占 1/3 权重 (尽管样本数相同)
    w = role_weights({"iso": 20, "S1": 20, "S3": 20})
    assert abs(w["iso"] / (w["S1"] + w["S3"]) - 0.5) < 1e-9, w
    # 综合比值在"仅 iso 超标"时的表现: iso=2×, S1/S3=1× → 权重 1/3 ⇒ 综合 = 2^(1/3)
    r2, _, _ = joint_log_ratio({"iso": [20.0] * 20, "S1": [10.0] * 20, "S3": [10.0] * 20},
                               {"iso": [10.0] * 20, "S1": [10.0] * 20, "S3": [10.0] * 20})
    assert abs(r2 - 2 ** (1 / 3)) < 1e-9, r2
    # (c) 角色样本不足 → 只用够的角色
    r3, _, d3 = joint_log_ratio({"iso": [10.0] * 3, "S1": [20.0] * 20},
                                 {"iso": [10.0] * 20, "S1": [10.0] * 20})
    assert list(d3) == ["S1"] and abs(r3 - 2.0) < 1e-9, (r3, d3)
    # (d) 单键 spread≡0 → 该角色不可用 (不参与综合, 也不会被误当成"快")
    assert joint_log_ratio({"S1": [0.0] * 30}, {"S1": [10.0] * 30}) is None
    # (e) 自适应阈值: 单调下降, **乘性**形式 (n=20,σ=0.87,z=3.46 → exp(0.843)=2.32)
    assert margin_adaptive(20, 0.87) > margin_adaptive(50, 0.87) > margin_adaptive(200, 0.87)
    assert abs(margin_adaptive(20, 0.87) - math.exp(0.843)) < 0.01, margin_adaptive(20, 0.87)
    assert margin_adaptive2(20, 20, 0.87) > margin_adaptive(20, 0.87)      # 计入锚噪声更严
    assert abs(margin_adaptive2(20, 10**9, 0.87) - margin_adaptive(20, 0.87)) < 0.01
    # (f) 段级 MAD 单侧围栏: 上层离群被剔、下层不动 (异常只偏大)、小桶不设栏
    segs = [(0, "S1", "ab", 2, 10.0)] * 20 + [(1, "S1", "ac", 2, 200.0)] + \
           [(2, "S1", "ad", 2, 0.5)] + [(3, "iso", "a", 1, 5.0)] * 3
    keep, drop, fences = mad_filter(segs)
    assert len(drop) == 1 and drop[0][4] == 200.0, drop          # 只剔上层离群
    assert fences[("iso", 1)] == float("inf"), fences             # 3 个样本 → 不设栏
    assert any(s[4] == 0.5 for s in keep)                        # 低值保留 (单侧语义)
    print("角色模型自测通过: 段位抵消 / 1:2 权重 / n_eff 合成 / 不足角色绕开 / 单键零值 / "
          "自适应阈值 / 段级 MAD 单侧围栏")
