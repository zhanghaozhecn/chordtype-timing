#!/usr/bin/env python3
"""
分析-难度剔除.py — 组合**名次候选 + 显著性**判定 → 维护 组合排除表.txt (**唯一一种剔除方法**)

v3 (2026-10-12 用户决策; 取代 判据 A / 判据 B 三层阶梯 / 软降权 / Et 决胜 / 双手交集):
  用户原话 (第一轮): "只要一边确定最慢 (**其参与 一击:二击 = 1:2 的各个组合产生的坏影响**排
    61 名之后), 就剔除对称的该键位。**61 名是保险, 故意多采**。**15 个单键和 1 个 3 键固定不剔除**。"
  用户原话 (第二轮澄清, **定规则**): "**不是 61 名之后就硬剔**, 我的意思是最多只剔除 **28 对**,
    要剔除还是要**分析显著性**。"

  · **名单** = 该手全部组合 (15 单键 + 63 双键 + 1 三键参考 = 79) 按"坏影响"**升序** (快→慢)。
    "坏影响" = 综合 occ 比 θ = 各角色与**同角色参考水平**配对的 log 比, 按 **1击:2击 = 1:2**
    加权平均 (**并击公共.joint_log_ratio + role_weights**, 不另立口径); occ = 整击占用 lu−fd。
    用 occ 而非 spread: 实测 σ_resid 0.19 vs 0.87 ⇒ 同样本量下名次才排得动 (spread 排序 = 噪声)。
  · **① 保险线 = 第 60 名**: 名次 ≤ `--line` (默认 60) ⇒ **保险保留** (永不剔, "故意多采");
    名次 > 60 ⇒ **候选** —— 只是候选, **不自动出局**。
  · **② 显著性闸门** (`elim_significant`; 用户第三轮"只比较 occ 段时间, **时间显著大于基准名的
    排除**"; 2026-10-13 用户把**基准时间**改成"第 52 名的 **occ 模型时间**"): 候选里只有 **occ 时间
    显著大于第 `line` 名那个组合** 的才允许出局。
    · `--bench model`（**默认**）= 基准取**模型 occ 时间**（`_bench_model_theta`; 与判定同池的
      `ShrunkModel`）, 视为已知 ⇒ `θ > θ_52·exp(z·1.253σ/√n_eff)`（**只算候选侧噪声**）;
    · `--bench data` = 基准取**第 52 名的数据 θ**（旧口径）⇒ `θ > θ_52·exp(z·1.253σ·√(1/n_eff+1/n_eff_52))`
      （**两侧噪声都算**）—— 只作对照与复现历史读数。
    σ = 单元内 σ(log occ); z 默认 = **Bonferroni** `z_for(候选判定数 × --looks)`。
    比较量 = occ 综合比 θ (1击:2击 = 1:2 加权、段位配对抵消) —— **不掺 spread/gap/错误项**。
    ⚠ **错误率不进剔除（2026-10-14 用户决策, 硬规则）**: "错误时间在并击中难以估计, 且 1 类错误中
    可能包含真实错误和读图错误…以后**不再将错误率加入当量, 也不再用错误率加入剔除分析**。"
    ⇒ 判据只用 occ（现状即如此）; **任何形态**的错误项/错误时间（含旧 `quota_cut(et=)` 的平手决胜）
    都不许重新进入, 新增判据量前先自查这一条。
    ⇒ **名次到线但没显著慢于第 52 名 ⇒ 保留**。⚠ model 档是**用户显式选择的更宽口径**（阈值中位低
    3–4%, 本快照并集 13 → 15 对）——不是"模型更准": m=3 的收缩对 n≈50–70 的组合只挪 ~4%, 基准的
    抽样误差基本还在, 只是被当成已知（详见 `并击公共.elim_significant` 的文档）。
  · **③ 行动上限**: 镜像并集后**最多剔 `--max-pairs` (默认 28) 对** (按坏影响降序; 超出部分
    本轮不动, 报告里列出)。
  · **保护** = 15 单键 + 1 三键参考 (`并击公共.elim_protect`): **固定不剔**, 名次再差也不动
    (单键 = 一级字/简词必需; 3 键按设计只有一个数据点, 采集器本就拒绝排除 3 键)。
  · **对称** = **任一侧出局 ⇒ 镜像对两侧一起出局** (`并击公共.elim_mirror`; 方案要求左右手
    可用组合对称)。"一边**确定**最慢"里的"确定" = 该侧过了上面的显著性闸门。
  · **不可排名者** (n_eff < `--n-min`) **不判不动**: 不进名单 (不占候选名额), 也不写进排除表。
  · **写表门禁** = 可排名双键比例 ≥ 90% (取最差手) 才允许写表, 否则拒写 (只出名单);
    `--force` 越过 (依据 实验/实验-新口径样本量.py 的闭环结论: 剔错了补不回来)。

  **只有一张表**: `组合排除表.txt` = 单一列表 (自动段 + `# [manual]` 附录; 2026-10-12 用户决策
  "现在只需要一个排除表，合并掉")。**组合降权表已删除** (软降权层早已撤除, 采集器不再读任何权重表)。
  自动段 = **追加式 (只增不减)**: 硬剔不可逆 ⇒ 工具不自动撤销既有条目; 恢复采样 = 手工删行。

用法: python 分析-难度剔除.py [--hand l|r|both] [--window 0] [--n-min 20] [--line 52]
                              [--max-pairs 28] [--z Z] [--looks N] [--no-sig]
                              [--pool stable|full] [--dry-run] [--force]
                              [--table [PATH]] [--selftest] [--no-plot]

  ★ **样本池 = 全量窗口**（2026-10-13 用户「这样采集效率太低了, **改回用全部数据判断剔除**」;
  默认 `--pool full`）: 窗口内**全部成功行**立刻可用（含练习期）。`--pool stable` = 稳定期
  （与模型同一池, 供"当前状态"审阅对照）—— ⚠ 它样本量只有全量的 ~44–48%、名单常短于保险线
  ⇒ 一个都不剔, 且**池大小由数据重新估的边界决定 ⇒ 对采集量不单调**（实测会缩）。

  ★ **判断标准 = occ 综合时间是否显著大于第 52 名所在的时间**: 候选需 **occ 时间显著大于第 `line`
  名那个组合**（`--bench data` = **默认**: 第 52 名的**数据 θ**, **两侧噪声都算**; `--bench model` =
  第 52 名的 **occ 模型时间**, 视为已知 ⇒ 只算候选侧噪声 —— 实测更快, 用户判定"太快了"后只作对照）。

  ★ **每次 occ 剔除都出一张图** (2026-10-13 用户要求): 判定的副产品 = **`组合相对耗时-双手.png`**
  —— **键位组合击内时间柱状图**。**左右手一张图、按名次交错** (左1 右1 左2 右2 …, 共 158 根);
  左手深色 / 右手同色系浅色 (+ 右手道浅灰底纹); 刻度 = 各手自己的名次 + 组合名。
  **柱高 = 绝对时间 (ms)** = 该手参考中心(ms) × 综合比 θ（纯单调换算, 名次/标记不变）;
  误差棒 ±1.253σ/√n_eff; 标记 = **斜纹 = 本轮显著出局（拟剔）**（「52 后不显示标记」⇒ 无 ▼,
  2026-10-13 用户「柱状图不要体现现有硬剔, 只用斜线体现显著慢的键位组合」⇒ **不画表状态**）。
  `--no-plot` 跳过 (只影响出图, 判定/写表一行不变)。`--hand l|r` 诊断路径出同名单手图。
"""
import sys, argparse, time, math, random, importlib
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from 并击公共 import (BASE, REF_COMBO, read_tsv, role_segments, scheme_used, stable_start, pct,
                     word_occ, LEFT_COMBOS, RIGHT_COMBOS, ROLES, canon,   # canon = 组合串唯一归一化
                     DATA_TSV,
                     role_weights, joint_log_ratio, sigma_of_log, sigma_within_log, sigma_fallback,
                     margin_adaptive, mirror_combo, pair_id, role_ref_vals,
                     TWO_KEY_PER_HAND, SINGLES_PER_HAND, REF_MODE_DEFAULT, REF_MODES,
                     ELIM_LINE, ELIM_PROTECT, ELIM_MAX_PAIRS, elim_protect, elim_significant,
                     elim_rank, elim_cap_pairs, elim_mirror,
                     elim_write_gate, z_for, selftest_elim, selftest_quota, selftest_boundary,
                     selftest_cells, selftest_layout, QUOTA_WRITE_RANK_FRAC,
                     # 9×7 分类 (列形态 × 行对; 2026-10-13 用户"按 9*7 的分类顺序写, 备注相对速度")
                     SLOT_NAME, ROW_NAME, COL_PAIRS, ROW_PAIRS,
                     cell_of, cell_name, col_pair, row_pair, cell_sort_key)

DATA = DATA_TSV
EXCLUDE_TXT = BASE / "组合排除表.txt"                  # **唯一一张动作表** (v2.59: 降权表已删除)


# ═══════════════ 组合排除表读写 (**单一列表**: 自动段 + [manual] 附录) ══════════════════
# v2.59 (2026-10-12 用户决策"现在只需要一个排除表，合并掉"): 旧的三段 ([difficulty] 历史 /
# [quota] 现行 / [manual] 手工) **合并成一张顺列表**; 段标记不再有语义 (读到也只当注释)。
# 语义 = **追加式 (只增不减)**: 硬剔不可逆 ⇒ 工具**不自动撤销**任何既有条目 (撤销 = 手工删行,
# 那是"恢复采样"的动作, 属用户决策)。所以自动段 = 本轮算出的出局集 ∪ 既有条目。
MANUAL_TAG = "# [manual]"


def read_existing(path):
    """组合排除表 → (auto: set, manual: set) —— **条目一律归一成镜像对的左手形式** (v2.60)
    `# [manual]` 之后的行归**手工段** (工具保留); 之前的全部行 = **自动段**。
    旧格式的 `# [difficulty]` / `# [quota]` 段标记只当注释 (单一列表口径)。
    v2.60 (2026-10-13 用户"只写左手键位, 右手由代码推导"): 读到右手组合 → `pair_id` 归一到左手形式
    (并提示); 非法行跳过。⇒ 追加式的"既有条目"比较也在**镜像对层面**做, 右手行不会被当成"新条目"。"""
    auto, manual, in_manual = set(), set(), False
    if not Path(path).exists():
        return auto, manual
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#"):
            if s.lower().startswith(MANUAL_TAG):      # 只有**以 `# [manual]` 开头的注释行**才是段标记
                in_manual = True                      # (头部注释里提到 '# [manual]' 不算 —— 必须 startswith)
            continue
        body = s.split("#", 1)[0].strip()             # ⚠ 条目行**行内可带 `#` 备注**（v10 修复:
        if not body:                                  #   旧版整行解析 ⇒ 带备注的条目被当无效行丢掉,
            continue                                  #   于是"追加式只增不减"静默失效: 若行动集缩小,
        try:                                          #   下次写表会把其余既有条目一起丢掉 = 偷偷恢复采样）
            form = pair_id(canon(body.lower()))       # 先 canon (槽位序, 旧写法容错) 再归一到左手
        except Exception:
            print(f"排除表忽略无效行: {s!r}")
            continue
        if form != body.lower():
            print(f"排除表提示: {body} 是右手组合 ⇒ 归一到左手形式 {form} (v2.60: 表只写左手)")
        (manual if in_manual else auto).add(form)
    return auto, manual


def write_exclude(path, auto, manual, header_lines, groups=None):
    """写排除表: 头部注释 → **按 9×7 分类顺序分组的自动段** (组标题 + `组合  # 备注`) → `# [manual]`

    `groups` = [(组标题, [(组合, 备注), …]), …] —— 分类顺序由调用方给 (9 列形态 → 7 行对);
    备注 = 相对速度等行内信息 (`#` 之后的内容, 采集器解析时会丢掉);
    不在任何组里的自动条目补一个"其他"段兜底 (绝不静默丢条目)。"""
    lines = list(header_lines)
    covered = set()
    for title, items in (groups or []):
        if not items:
            continue
        lines += ["", title]
        lines += [f"{c:<6} # {note}" if note else c for c, note in items]
        covered |= {c for c, _ in items}
    left = sorted(set(auto) - covered)                 # 兜底: 未分组的条目照样写出
    if left:
        lines += ["", "# [其他] 未归入 9×7 分类的自动条目 (兜底; 正常不该出现)"] + left
    if manual:
        lines += ["", MANUAL_TAG + " 手工追加条目 (工具保留; 自动段只增不减, 手工段原样保留)"] \
            + sorted(manual)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ═══════════════ 取数 (与其它脚本同源: role_segments / role_ref_vals) ═══════════════
POOLS = ("full", "stable")
POOL_DEFAULT = "full"     # 2026-10-13 用户「这样采集效率太低了, 改回用全部数据判断剔除」


def collect(rows, hands, metric, pool=POOL_DEFAULT):
    """窗口内该 metric 的样本 → {(手, 角色, 组合): [值]}

    **`pool="full"`（默认）** = 窗口内**全部成功行**（含练习期）—— 采样效率优先: 数据立刻全部可用。
    `pool="stable"` = **与模型同一池**（`分析-当量模型.build_samples` 的稳定期: 分类型各自截取 +
    质量/值围栏）—— 语义更贴"当前状态"（铁律 8）, 但**样本量只有全量的 ~44–48%**, 名单常短于保险线
    ⇒ 本轮一个都不剔; 且该池大小**由数据重新估的边界决定 ⇒ 对采集量不单调**（会缩）。
    沿革: 2026-10-13 用户先要稳定期池, 同日实测「采集效率太低」⇒ **改回 full 为默认**（stable 保留,
    供"当前状态"审阅对照）。"""
    vals = defaultdict(list)
    if pool == "stable":
        M = importlib.import_module("分析-当量模型")      # 惰性 import（口径唯一源; 不拖慢 --selftest）
        for h in hands:
            for _i, role, combo, v in M.build_samples(rows, h, use_stable=True)[metric]:
                vals[(h, role, combo)].append(v)
        return vals
    for r in rows:
        for h in hands:
            for role, combo, v in role_segments(r, h, metric):
                vals[(h, role, combo)].append(v)
    return vals


def hand_ref(vals, hand, args):
    """该手各角色的**参考水平** → ({(手,角色): (med, n)}, {(手,角色): [参考样本]}, missing)
      口径 = 并击公共.role_ref_vals (pooled = 该手 2 键组合总体中心, 不依赖 sdf);
      样本不足的角色不产出 (该角色不参与判定)"""
    combos = [c for c in (LEFT_COMBOS if hand == 'l' else RIGHT_COMBOS) if len(c) == 2] \
        if args.ref == "pooled" else None
    raw = role_ref_vals(vals, hand, combos, args.ref)
    ref, raw_ok, missing = {}, {}, []
    for role in ROLES:
        v = raw.get(role, [])
        need = args.n_min_iso if role == "iso" else args.n_min
        if len(v) >= need and pct(v, 0.5) > 0:
            ref[(hand, role)] = (pct(v, 0.5), len(v))
            raw_ok[(hand, role)] = v
        else:
            missing.append((hand, role, len(v), need))
    return ref, raw_ok, missing


def combo_vals(vals, hand, ref, combo):
    """该组合在参考可用角色上的样本 → {role: [值]} (不可用角色直接剔除, 保证配对语义)"""
    return {role: vals.get((hand, role, combo), []) for role in ROLES
            if (hand, role) in ref and vals.get((hand, role, combo))}


def _ctx(win, hands, metric, args):
    """完整判定上下文 → (vals, ref, ref_raw, σ, σ来源, missing)
    σ 口径与 main() 一致: 单元内 `sigma_within_log` 优先, 不足退回 `sigma_of_log`
    池由 `args.pool` 决定 (默认 stable = 稳定期, 与模型同一池)"""
    vals = collect(win, hands, metric, getattr(args, "pool", POOL_DEFAULT))
    a = argparse.Namespace(**vars(args))
    a.metric = metric
    sw = sigma_within_log(dict(vals))
    sig = sw or sigma_of_log([v for v in vals.values() for v in v], metric)
    src = "单元内(残差)" if sw else f"兜底({sigma_fallback(metric):.2f})"
    ref, ref_raw, missing = {}, {}, []
    for h in hands:
        r, raw, miss = hand_ref(vals, h, a)
        ref.update(r)
        ref_raw.update(raw)
        missing += miss
    return vals, ref, ref_raw, sig, src, missing


def _ratio_of(vals, ref, ref_raw, hand, combo, iso_imp):
    """该组合的综合比值 → (ratio, n_eff, detail) | None
    与判定同一函数 (`combo_vals` + `role_weights` + `joint_log_ratio`), 不另立口径"""
    vd = combo_vals(vals, hand, ref, combo)
    if not vd:
        return None
    ref_vals = {r: ref_raw.get((hand, r), []) for r in ROLES if (hand, r) in ref}
    w = role_weights({r: len(v) for r, v in vd.items()}, (iso_imp, 1.0)) if iso_imp else None
    return joint_log_ratio(vd, ref_vals, weights=w)


# ═══════════════ 判定 (单手名次 + 镜像并集; 唯一判据) ═══════════════════════════════
BENCH_KINDS = ("data", "model")
# **data = 默认**（2026-10-13 用户「现在剔除的太快了, 改成比 52 名显著**长**（**含两侧噪声**）」——
#   即回到"候选 occ 综合时间显著长于第 52 名, 两侧噪声都算"）;
# model = 同日晚些时候试过的一档（基准取第 52 名的 occ 模型时间、视为已知 ⇒ 只算候选侧噪声; 实测
#   同快照并集 21 对 vs data 的 13 对 —— 用户判定"太快了"⇒ 退回 data）。
BENCH_DEFAULT = "data"


def _bench_model_theta(vals, hand, ref, combo, args):
    """基准组合的 **occ 模型时间** → 同一个 θ 单位（供显著性闸门当基准）

    θ_模型 = exp( Σ_r w_r·log( occ模型(组合, r) / med_ref_r ) / Σ_r w_r ) —— 与判定的 θ **同单位**
    （分母仍是同角色 pooled 参考中位; w_r = 该组合自己的 1击:2击 权重, 与 `_ratio_of` 同口径）。
    模型 = **与判定同池**的 `ShrunkModel`（`分析-当量模型` = 口径唯一源）:
      `fit(该手 occ 样本, gap=[])` —— 本函数只用 occ 侧, 而 `ShrunkModel` 的 occ/gap **独立拟合**,
      故不需要 gap 样本、也不必读 `产物/当量表-*.npz`（避免 npz 陈旧造成的口径漂移）。
    ⚠ 该值仍带抽样误差（m=3 的收缩对 n≈50–70 的组合只挪 ~4%）—— 闸门里把它当**已知**是用户的
      显式选择（更宽口径）, 不是"模型更准"。"""
    if not combo:
        return None
    M = importlib.import_module("分析-当量模型")
    occ = [(0, role, c, v) for (hh, role, c), vs in vals.items() if hh == hand for v in vs]
    if not occ:
        return None
    mdl = M.ShrunkModel().fit(occ, [])
    vd = combo_vals(vals, hand, ref, combo)
    if not vd:
        return None
    imp = float(getattr(args, "iso_importance", 0.5) or 0.5)
    w = role_weights({r: len(v) for r, v in vd.items()}, (imp, 1.0))
    den = sum(w[r] for r in vd if w[r] > 0)
    if den <= 0:
        return None
    return math.exp(sum(w[r] * math.log(mdl.occ(combo, r) / ref[(hand, r)][0])
                        for r in vd if w[r] > 0) / den)


def judge_quota(vals, ref, ref_raw, args, hand):
    """**单手名次 + 显著性判定** (现行唯一判据) → dict | None (该手无可用参考 ⇒ 不判)
    名单 = 该手 79 组合按综合 occ 比升序; **名次 ≤ `args.line` (60) = 保险保留**,
    名次 > line = **候选** (只是候选); 候选里只有** occ 时间显著大于第 `line` 名**(= 保险线上那
    个组合, 由 `elim_significant(ref=)` 做两侧噪声比较) 的才出局,
    z = Bonferroni `z_for(候选数 × 审阅次数)`;
    不可排名者 (n_eff < `args.n_min`) 不判不动。
    `args.z` 为 None ⇒ **不做显著性筛** (cut = ∅) —— 供调用方"先数候选、再定 z"的两遍流程。
    本函数不含**镜像并集**与 **28 对上限** (都需要两手, 见 elim_mirror / elim_cap_pairs)。
    → ranked/unrankable/detail/keep/cut/hard/cand/insig/sig/margins/rank/order/info/anchors/keep_all
      (soft/ranked_loose 恒空, 只为历史实验脚本接线)
    注: 函数名沿用旧判据 B 的入口名 —— 语义已改为"名次候选 + 显著性闸门", 调用方只接线不另立口径。"""
    if not any((hand, r) in ref for r in ROLES):
        return None
    line = int(getattr(args, "line", ELIM_LINE))
    z = getattr(args, "z", None)
    sigma = float(getattr(args, "sigma", None) or sigma_fallback("occ"))
    imp = getattr(args, "iso_importance", 0.5)
    prot = elim_protect(hand)
    ref_all = ref                    # ⚠ 下面 `ref` 会被重绑成基准 (θ, n_eff) 元组 —— 模型基准要用**全表**
    ref_vals = {r: ref_raw.get((hand, r), []) for r in ROLES if (hand, r) in ref}
    res = {"ranked": {}, "unrankable": set(), "detail": {}, "keep": set(), "cut": set(),
           "hard": set(), "soft": set(), "ranked_loose": {}, "rank": {}, "order": [],
           "info": None, "keep_all": set(), "protect": prot, "line": line, "z": z,
           "cand": set(), "insig": set(), "sig": set(), "margins": {},
           "anchors": {r: ref[(hand, r)] for r in ROLES if (hand, r) in ref}}
    for combo in sorted(LEFT_COMBOS if hand == 'l' else RIGHT_COMBOS):
        vd = combo_vals(vals, hand, ref, combo)
        if not vd:
            res["unrankable"].add(combo)
            continue
        w = role_weights({r: len(v) for r, v in vd.items()}, (imp, 1.0)) if imp else None
        got = joint_log_ratio(vd, ref_vals, weights=w)
        if got is None:
            res["unrankable"].add(combo)
            continue
        ratio, n_eff, detail = got
        if n_eff >= args.n_min:                       # 可排名 (进名单的前提)
            res["ranked"][combo] = (ratio, n_eff)
            res["detail"][combo] = detail
        else:
            res["unrankable"].add(combo)
    _, order0, _ = elim_rank(res["ranked"], prot, line)      # 先排名 (拿参考)
    ref = ((order0[line - 1][2], order0[line - 1][3]) if len(order0) >= line else None)
    res["ref_combo"] = (order0[line - 1][1] if len(order0) >= line else None)
    res["ref_data"] = ref                                    # 基准的**数据** θ (留档/对照)
    if ref is not None and getattr(args, "bench", BENCH_DEFAULT) == "model":
        tm = _bench_model_theta(vals, hand, ref_all, res["ref_combo"], args)
        if tm is not None:                                   # ⇒ n_eff_ref = None (基准视为已知)
            res["ref_model"] = tm
            ref = (tm, None)
    res["ref_pair"] = ref
    sig, thr = (elim_significant(res["ranked"], sigma, z, ref=ref) if z is not None else (None, {}))
    cut, order, info = elim_rank(res["ranked"], prot, line, significant=sig)
    res.update(order=order, info=info, cut=set(cut), hard=set(cut), margins=thr,
               cand=set(info["cand"]), insig=set(info["insig"]), sig=set(sig or ()))
    res["keep"] = set(info["keep"])
    res["rank"] = {c: k for k, c, _t, _n in order}
    res["keep_all"] = res["keep"] | res["unrankable"] | (prot & set(res["ranked"]))
    return res


def _ev(res, combo):
    """组合在该手名单里的证据文字 = θ比/n_eff#名次 (不在名单里 = '—')"""
    if res is None or combo not in res["ranked"]:
        return "—"
    r, ne = res["ranked"][combo]
    return f"{r:.2f}/{ne:.0f}#{res['rank'].get(combo, '?')}"


def _cells(detail):
    """各角色 n/比 → 'iso 30/0.98 S1 …' (缺角色 = '-')"""
    detail = detail or {}
    return " ".join(f"{r} {detail[r]['n']}/{detail[r]['ratio']:.2f}" if r in detail
                    else f"{r} -" for r in ROLES)


def _wpad(s, w):
    """按**显示宽度**补空格 (CJK 记 2 列) —— 中文表头对齐用"""
    n = sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)
    return s + " " * max(0, w - n)


def _speed(t):
    """θ → 相对速度文字: `1.35 (+35%)` (比同角色、同键数组合参考中心慢/快多少)"""
    return f"{t:.2f} ({100 * (t - 1):+.0f}%)"


def _row_label(rp):
    """行对 → 可读标签 (槽位序; 同行写 同上/同中/同下)"""
    a, b = rp
    return f"同{ROW_NAME[a]}" if a == b else f"{ROW_NAME[a]}→{ROW_NAME[b]}"


def _col_label(cp):
    """列形态 → 可读标签 (如 小+无 / 中+食内)"""
    return "+".join(SLOT_NAME[x] for x in cp)


def cell_grid(res, hand, action=None):
    """**9×7 分类视图** (2026-10-13 用户"按照 9*7 的分类顺序来写，并备注相对速度"):
    行 = 9 个列形态 (槽位序), 列 = 7 个行对 (槽位序); 格内 = θ (相对速度, 参考中心 = 1.00),
    出局标 ✗; 每行末尾给该列形态的出局计数。左右手各一张 (镜像同格 ⇒ 逐格可比)。"""
    if res is None:
        return
    cell = cell_of(hand)
    head = "  " + _wpad("列形态 ＼ 行对", 16) + "".join(_wpad(_row_label(rp), 9)
                                                       for rp in ROW_PAIRS) + " 出局"
    print(head)
    for cp in COL_PAIRS:
        row, n_out, n_rank = _wpad(_col_label(cp), 16), 0, 0
        for rp in ROW_PAIRS:
            c = cell[(cp, rp)]
            got = res["ranked"].get(c)
            out = bool(action) and pair_id(c) in action
            if got is None:
                row += _wpad("未排名✗" if out else "未排名", 9)
            else:
                n_rank += 1
                row += _wpad(f"{got[0]:.2f}" + ("✗" if out else ""), 9)
            n_out += int(out)
        print(row + f" {n_out}/{n_rank}")
    print("  (θ = 综合 occ 比: 1.00 = 与同角色参考中心同速, 1.35 = 慢 35%; ✗ = 本轮出局/停采;"
          " 未排名 = n_eff 不足)")


def _sig_txt(args):
    """显著性闸门的口径文字（**按 `--bench` 分档, 只在这里写一次**）"""
    if getattr(args, "bench", BENCH_DEFAULT) == "model":
        return (f"θ_{args.line} = **第 {args.line} 名的 occ 模型时间** θ（`--bench model`; 基准视为"
                f"已知 ⇒ 阈值只含候选侧噪声: θ > θ_{args.line}·exp(z·1.253σ/√n_eff)）")
    return (f"θ_{args.line} = **第 {args.line} 名的数据 θ**（`--bench data`; 两侧噪声都算: "
            f"θ > θ_{args.line}·exp(z·1.253σ·√(1/n_eff+1/n_eff_{args.line}))）")


def report(runs, args):
    """打印两手名次表 (只读)"""
    print(f"\n═══ 组合名次判定 (保险线 {args.line}; **名次 > {args.line} 只是候选, 出局还要过显著性**) ═══")
    print("名单 = 该手 79 组合 (15 单键 + 63 双键 + 1 三键参考) 按**综合 occ 比**升序 (快→慢);")
    print("  θ = 同角色参考配对的 log 比, 按 1击:2击 = 1:2 加权 (并击公共.joint_log_ratio)")
    print(f"三闸门: ① 名次 ≤ {args.line} = **保险保留** (永不剔) | ② 候选 (名次 > {args.line}) 还要"
          f"**occ 时间显著大于第 {args.line} 名** ({_sig_txt(args)}, z = "
          f"{getattr(args, 'z_txt', '—')}, σ = {args.sigma:.2f})"
          f" | ③ 最多剔 **{args.max_pairs} 对** (镜像并集后)")
    print(f"保护 = {SINGLES_PER_HAND} 单键 + 1 三键参考 ({ELIM_PROTECT} 个, 固定不剔) | "
          f"进名单门槛 n_eff ≥ {args.n_min} (不可排名者不判不动) | 窗口 = 末 {args.win_n} 试次")
    if args.line >= 79:
        print(f"⚠ --line {args.line} ≥ 79 ⇒ 没有候选, 本轮不剔任何人")
    for h in ("l", "r"):
        res = runs.get(h)
        cn = "左" if h == "l" else "右"
        if res is None:
            print(f"\n[{cn}手] 无可用判定 (无数据或参考不足) ⇒ 本轮不判")
            continue
        print(f"\n[{cn}手] 参考水平 [{args.ref}]: " +
              "  ".join(f"{r}={m:.0f}ms(n={n})" for r, (m, n) in sorted(res["anchors"].items())))
        rb, rd = res.get("ref_pair"), res.get("ref_data")
        if res.get("ref_model") is not None:
            print(f"  基准 = 第 {res['line']} 名 **{res['ref_combo']}**: 数据 θ {rd[0]:.3f} "
                  f"(n_eff {rd[1]:.1f}) → **模型 θ {res['ref_model']:.3f}** "
                  f"({100 * (res['ref_model'] / rd[0] - 1):+.1f}%) ← `--bench model` (基准视为已知)")
        elif rb:
            print(f"  基准 = 第 {res['line']} 名 **{res['ref_combo']}**: θ {rb[0]:.3f} / "
                  f"n_eff {rb[1]:.1f} ← `--bench data` (两侧噪声都算)")
        else:
            print(f"  基准 = 第 {res['line']} 名 —(名单不足 ⇒ 无候选)")
        print(f"  {'#':>3} {'θ比':>6} {'比第N名':>8} {'n_eff':>6} {'显著阈':>7} {'组合':>5}  "
              f"{'判定':<14} | 各角色 n/比")
        for k, c, t_, n in res["order"]:
            prot = c in res["protect"]
            thr = res["margins"].get(c)
            rel = (f"{t_ / rb[0]:.3f}" if rb else "—")
            if k <= res["line"]:
                mark = "保留·保护" if prot else "保留 (保险线内)"
            elif prot:
                mark = "保留·保护"
            elif c in res["cut"]:
                mark = "候选→出局"
            else:
                mark = "候选→保留(不显著)"
            note = " ●方案在用" if scheme_used(c) else ""
            print(f"  {k:>3} {t_:>6.2f} {rel:>8} {n:>6.1f} "
                  f"{(f'{thr:.3f}' if (thr and c in res['cand']) else '—'):>7} "
                  f"{c:>5}  {mark:<14} | {_cells(res['detail'].get(c))}{note}")
        bd = res["info"]["boundary"]                 # 保险线两侧的比值差 (可辨性证据)
        if bd:
            t1, t2 = res["ranked"][bd[0]][0], res["ranked"][bd[1]][0]
            b = (f"; 保险线在第 {res['line']}/{res['line']+1} 名 ({bd[0]} θ {t1:.2f} → "
                 f"{bd[1]} θ {t2:.2f}, 差 {100 * (t2 / t1 - 1):+.1f}%)")
        else:
            b = ("; **名单不足保险线 ⇒ 没有候选**（稳定期池样本量还撑不满 52 名 ⇒ 按现行规则"
                 "**本轮一个都不剔** —— 这是设计意图: 不用练习史平均去剔; 继续采集即可）"
                 if getattr(args, "pool", POOL_DEFAULT) == "stable" else "; 名单不足保险线 ⇒ 没有候选")
        print(f"  ⇒ 名单 {len(res['order'])}/79 个有比值{b}")
        print(f"     候选 {len(res['cand'])} 个 (名次 > {res['line']}) ⇒ **occ 时间显著大于第 "
              f"{res['line']} 名 {len(res['cut'])}** 个 (出局)" +
              (f" · 未达显著 {len(res['insig'])} 个 ⇒ 保留: {' '.join(res['insig'])}"
               if res["insig"] else ""))
        n_dbl = sum(1 for c in res["ranked"] if len(c) == 2)
        keep_dbl = sum(1 for c in res["keep_all"] if len(c) == 2)
        print(f"     保留双键 {keep_dbl}/{n_dbl} 可排名双键 | "
              f"保护落在保险线外 {len(res['info']['protected_beyond'])} 个"
              f"{' (' + ' '.join(res['info']['protected_beyond']) + ')' if res['info']['protected_beyond'] else ''}")
        if res["unrankable"]:
            print(f"     不可排名 {len(res['unrankable'])} 个 (n_eff < {args.n_min}): "
                  f"{' '.join(sorted(res['unrankable']))} ⇒ 不判不动 (既不剔也不占候选名额)")
        cell_grid(res, h, action=getattr(args, "action", None))   # **9×7 分类视图** (含相对速度)
    print("\n动作 = **任一侧出局 ⇒ 镜像对两侧一起写 组合排除表.txt**"
          "（**只写左手键位**, 右手 = 镜像由采集器推导; 硬剔不可逆）; "
          f"方案在用组合带 ● 标记仅作提示 (通用模型不承担方案的覆盖约束)")


def action_set(runs, args):
    """**动作集 (唯一实现)** → (exclude: set(左手形式), dropped: set, excl_map: {左手: (左?, 右?)})
    = `elim_mirror` (任一侧显著出局 ⇒ 两侧一起) + `elim_cap_pairs` (≤ `--max-pairs` 对)。"""
    if any(runs.get(h) is None for h in ("l", "r")):
        return set(), set(), {}
    excl = elim_mirror(runs["l"]["cut"], runs["r"]["cut"])
    keep, drop = elim_cap_pairs(set(excl), {p: _pair_score(runs, p) for p in excl}, args.max_pairs)
    return set(keep), set(drop), excl


def _pair_score(runs, p):
    """镜像对的"坏影响" = **出局那一侧**的 θ 取最大 (慢手门控; 只计已出局的一侧)"""
    vals = []
    for h, c in (("l", p), ("r", mirror_combo(p))):
        res = runs.get(h)
        if res and c in res["cut"]:
            vals.append(res["ranked"][c][0])
    return max(vals) if vals else 0.0


def report_mirror(runs, args):
    """镜像并集 + **28 对上限** → (exclude: set of **左手形式**, reasons: [str])

    v2.60 (2026-10-13 用户决策"由于剔除是对称的，以后在写表和汇报时只需要写左手的组合键位，
    右手由代码推导"): **动作集只以左手组合呈现** —— 写排除表也只写左手键位, 右手由
    `采集-并击当量.load_excluded` 用 `mirror_combo` 推导 (判定单位 = 镜像对)。
    报告里"镜像·右"列是那一侧的**自体测量值** (不是左手值的换算), 供复核; 组合名只在左列出现。"""
    print("\n═══ 镜像并集 + 上限 (任一侧出局 ⇒ 两侧一起剔; 最多 "
          f"{args.max_pairs} 对; **只写左手键位, 右手 = 镜像**) ═══")
    if any(runs.get(h) is None for h in ("l", "r")):
        miss = [h for h in ("l", "r") if runs.get(h) is None]
        print(f"  ⚠ {'/'.join(miss)} 手无可用判定 (无数据或参考不足) ⇒ **并集无法成立, 本轮不动作**"
              f" (只手名单见上; 左右 1:1 随机单手混采补齐后自动生效)")
        return set(), []
    cut_l = {pair_id(c) for c in runs["l"]["cut"]}
    cut_r = {pair_id(c) for c in runs["r"]["cut"]}
    keep, dropped = args.action, args.dropped
    excl = args.excl_map
    score = {p: _pair_score(runs, p) for p in excl}
    print(f"  按 **9×7 分类顺序** (列形态 → 行对) 排列; θ = 相对速度 (1.35 = 比参考中心慢 35%)")
    print(f"  {'左手':<6}{'行对':<7}{'θ (相对速度) 名次':>20}{'镜像右 θ (相对速度) 名次':>26}  判定")
    for cp in COL_PAIRS:                              # 9 个列形态, 分类顺序
        grp = [p for p in excl if col_pair(p) == cp]
        if not grp:
            continue
        grp.sort(key=lambda p: ROW_PAIRS.index(row_pair(p)))
        print(f"  ── {'+'.join(SLOT_NAME[x] for x in cp)} "
              f"(本列形态出局 {sum(1 for p in grp if p in keep)}/{len(grp)} 命中, 7 格) ──")
        for p in grp:
            a, b = excl[p]
            rc = mirror_combo(p)
            st = ("两侧同出局" if a and b else
                  "★仅左手出局 → 并集带动右侧" if a else "★仅右手出局 → 并集带动左侧")
            tail = "" if p in keep else "  ⛔超上限, 本轮不动"
            tl = runs["l"]["ranked"].get(p)                  # 左手的 (θ, n_eff)
            tr = runs["r"]["ranked"].get(rc)                 # 镜像右手的 (θ, n_eff)
            evl = f"{_speed(tl[0])} #{runs['l']['rank'][p]}" if tl else "—"
            evr = f"{_speed(tr[0])} #{runs['r']['rank'][rc]}" if tr else "—"
            print(f"  {p:<6}{_row_label(row_pair(p)):<7}{evl:>20}{evr:>26}  {st}{tail}")
    n_both = sum(1 for a, b in excl.values() if a and b)
    print(f"  ⇒ 并集 {len(excl)} 对 = 两侧同判 {n_both} + 仅一侧 {len(excl) - n_both} "
          f"(单手名义出局: 左 {len(cut_l)} / 右 {len(cut_r)})")
    if dropped:
        print(f"  ⇒ **上限生效**: 保留坏影响最大的 {len(keep)} 对剔, {len(dropped)} 对超上限本轮不动 "
              f"({' '.join(sorted(dropped))}) —— 下次审阅再看 (名次会随数据更新)")
    reasons = []
    for p in sorted(keep):
        a, b = excl[p]
        rc = mirror_combo(p)
        why = ("两侧同出局" if a and b else "并集带动 (仅" + ("左" if a else "右") + "手显著出局)")
        reasons.append(f"# [理由·剔除] 对 {p}（右手 {rc} 由代码推导）: 左 {_ev(runs['l'], p)} · "
                       f"镜像右 {_ev(runs['r'], rc)} — {why} (名次 > {args.line} 且 θ > 显著阈; "
                       f"z={args.z_txt})")
    if dropped:
        reasons.append(f"# [本轮未动·超上限] {len(dropped)} 对: {' '.join(sorted(dropped))} "
                       f"(并集 {len(excl)} > 上限 {args.max_pairs}; 按坏影响升序取前 {args.max_pairs})")
    return set(keep), reasons                     # **只返回左手形式** (右手由采集器镜像推导)


# ═══════════════ 完整剔除分析表 (--table; 只读报告, 不碰动作表) ═════════════════════
TABLE_DEFAULT = "剔除分析表"
TABLE_COLS = ["手", "9×7格", "组合", "键数", "镜像对(左形式)", "行对", "occ比", "相对速度",
              "n_eff", "显著阈", "名次", "单手判定", "并集判定", "各角色(occ) n/比",
              "方案在用", "动作表"]


def write_table(win, hands, args, prefix):
    """完整剔除分析表 → `{prefix}.md` (人读) + `{prefix}.tsv` (可筛选; 带 BOM 便于 Excel)。
    **只读**: 不碰排除表。行 = 该手全部 79 组合; 单键/三键 = 保护 (名次只作信息)。"""
    vals, ref, ref_raw, sig, src, _miss = _ctx(win, hands, "occ", args)
    a = argparse.Namespace(**vars(args))
    a.sigma, a.sigma_src = sig, src
    a.line = int(getattr(args, "line", ELIM_LINE))
    a.n_min = int(getattr(args, "n_min", 20))
    a.max_pairs = int(getattr(args, "max_pairs", ELIM_MAX_PAIRS))
    a.z_txt = getattr(args, "z_txt", None) or (
        "**关闭**" if getattr(a, "z", None) is None else f"{a.z:.2f}")
    runs = {h: judge_quota(vals, ref, ref_raw, a, h) for h in hands}
    both = len(hands) == 2 and all(runs.get(h) is not None for h in ("l", "r"))
    pairs = elim_mirror(runs["l"]["cut"], runs["r"]["cut"]) if both else {}
    keep_p, drop_p = elim_cap_pairs(set(pairs), {p: _pair_score(runs, p) for p in pairs},
                                    a.max_pairs) if both else (set(), set())
    excl = set(keep_p) | {mirror_combo(p) for p in keep_p}
    cur_auto, cur_manual = read_existing(EXCLUDE_TXT)   # v2.59: 单一列表 (自动段 + [manual] 附录)
    old = set(cur_auto) | set(cur_manual)
    rows = []
    md = ["# 剔除分析表 (名次候选 + 显著性 + 镜像并集 + 上限; 只读报告)\n",
          f"- 数据快照: **{len(win)} 行** | 名单 = 该手 79 组合按综合 **occ 比**升序 "
          f"(1击:2击 = 1:2 加权; 同角色参考配对)",
          f"- 保险线: 名次 ≤ **{a.line}** ⇒ 保险保留 (永不剔); 名次 > {a.line} ⇒ **候选** "
          f"(保护 = {SINGLES_PER_HAND} 单键 + 1 三键参考, 固定不剔)",
          f"- 显著性闸门: 候选需 **occ 时间显著大于第 {a.line} 名** ({_sig_txt(a)}; "
          f"阈值列 = 绝对 θ 阈) | "
          f"z = {getattr(a, 'z_txt', '—')} [{getattr(a, 'z_src', '—')}] | σ(log occ) = {sig:.2f} [{src}] | "
          f"参考 [{a.ref}] | 池 [{getattr(a, 'pool', POOL_DEFAULT)}]",
          f"- 行动上限: 最多剔 **{a.max_pairs}** 个镜像对 (并集后按坏影响降序) | "
          f"门槛: 可排名 n_eff ≥ {a.n_min} (不可排名者不判不动)",
          "- 动作 = **任一侧出局 ⇒ 镜像对两侧一起剔**; **表与报告只写左手键位** (右手 = 镜像, "
          "代码推导; v2.60); **明细按 9×7 分类顺序** (列形态 → 行对) 排列, 并给**相对速度** "
          "(θ 与 +% = 比同角色参考中心慢多少; 2026-10-13 用户要求); 每次审阅先 `--dry-run`\n"]
    for h in hands:
        res = runs.get(h)
        if res is None:
            continue
        cn = "左" if h == "l" else "右"
        rb2, rd2 = res.get("ref_pair"), res.get("ref_data")
        md.append(f"## {cn}手 (名单 {len(res['order'])}/79; 候选 {len(res['cand'])}; "
                  f"显著出局 {len(res['cut'])}; 不可排名 {len(res['unrankable'])})"
                  + ((f" — 基准 = 第 {a.line} 名 {res['ref_combo']}: 数据 θ {rd2[0]:.3f} "
                      f"(n_eff {rd2[1]:.1f}) → **模型 θ {res['ref_model']:.3f}**\n")
                     if res.get("ref_model") is not None else
                     (f" — 基准 = 第 {a.line} 名 {res.get('ref_combo')} "
                      f"(数据 θ {rb2[0]:.3f} / n_eff {rb2[1]:.1f})\n" if rb2 else "\n")))
        for c in sorted(LEFT_COMBOS if h == 'l' else RIGHT_COMBOS, key=cell_sort_key):
            k = res["rank"].get(c)
            if k is None:
                verdict = "不可排名" if c in res["unrankable"] else "无数据"
            elif c in res["protect"]:
                verdict = "保留·保护" if k <= a.line else "保留·保护(保险线外)"
            elif k <= a.line:
                verdict = "保留 (保险线内)"
            elif c in res["cut"]:
                verdict = f"候选→出局 (显著大于第 {a.line} 名)"
            else:
                verdict = "候选→保留 (未达显著)"
            dbl = len(c) == 2
            t_ = res["ranked"][c][0] if c in res["ranked"] else None
            rows.append([cn, cell_name(c) if dbl else f"— ({len(c)} 键)",
                         c, len(c), pair_id(c), _row_label(row_pair(c)) if dbl else "—",
                         f"{t_:.3f}" if t_ else "",
                         f"{100 * (t_ - 1):+.0f}%" if t_ else "",
                         f"{res['ranked'][c][1]:.1f}" if c in res["ranked"] else "",
                         f"{res['margins'][c]:.3f}" if c in res["cand"] else "",
                         k or "", verdict, "出局" if pair_id(c) in excl else "",
                         _cells(res["detail"].get(c)), "是" if scheme_used(c) else "",
                         ("已在表" if c in cur_auto else
                          ("手工[manual]" if c in cur_manual else ""))])
    add = excl - old
    md.append("## 本轮若真写表 (预演)\n")
    md.append(f"- 自动段 **(追加式: 只增不减)**: 新增 **{len(add)}** 条; "
              f"既有条目 {len(old - excl)} 条保留 (硬剔不可逆 ⇒ 工具不自动撤销; 恢复采样须手工删行)")
    if both and pairs:
        md.append(f"- 并集 {len(pairs)} 对 → 上限 {a.max_pairs} ⇒ 实际剔 {len(keep_p)} 对")
        for p in sorted(keep_p, key=lambda p: -_pair_score(runs, p)):
            a1 = p in runs["l"]["cut"]
            b1 = mirror_combo(p) in runs["r"]["cut"]
            md.append(f"  - {p}（右手 {mirror_combo(p)} 由代码推导）: 左 {_ev(runs['l'], p)} · "
                      f"镜像右 {_ev(runs['r'], mirror_combo(p))} → "
                      f"{'两侧同出局' if a1 and b1 else '并集带动'}")
        for p in sorted(drop_p):
            md.append(f"  - ⛔超上限本轮不动: {p}（右手 {mirror_combo(p)}）"
                      f"(左 {_ev(runs['l'], p)} · 镜像右 {_ev(runs['r'], mirror_combo(p))})")
    md.append(f"- 手工段 (`# [manual]` 附录) 保留 {len(cur_manual)} 条: "
              f"{' '.join(sorted(cur_manual)) or '—'}")
    md.append("- ⚠ 硬剔**不可逆** (丢失的采样机会不可恢复) ⇒ 先 `--dry-run`, 由用户拍板写表\n")
    md.append("## 逐组合明细\n")
    md.append("| " + " | ".join(TABLE_COLS) + " |")
    md.append("|" + "---|" * len(TABLE_COLS))
    for r in rows:
        md.append("| " + " | ".join(str(x) for x in r) + " |")
    Path(prefix + ".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    tsv = ["\t".join(TABLE_COLS)] + ["\t".join(str(x) for x in r) for r in rows]
    Path(prefix + ".tsv").write_text("\ufeff" + "\n".join(tsv) + "\n", encoding="utf-8")
    print(f"\n完整剔除分析表 → {prefix}.md + {prefix}.tsv（只读报告; 未改排除表）")


# ═══════════════ 显著性 z 的唯一解析 (main 与出图共用) ══════════════════════════════
def resolve_z(vals, ref, ref_raw, args, hands):
    """显著性 z 的**唯一解析** (2026-10-13 出图接入时从 main 提取, 语义一行未改):
      `--no-sig` ⇒ None (诊断开关, 出局退化成纯名次); `--z` 给定 ⇒ 手动;
      否则 **Bonferroni** `z_for(候选判定数 × --looks)` —— 先数候选、再定 z (两遍, 序贯审阅不膨胀)。
    写回 `args.z` / `args.z_src` / `args.z_txt`; 返回 z。
    ⚠ 两遍流程里 `judge_quota` 的 σ 不参与 (z=None ⇒ 不做显著性筛) ⇒ 只影响候选计数, 与 σ 无关。"""
    if getattr(args, "no_sig", False):
        args.z, args.z_src = None, "**关闭** (--no-sig 诊断)"
    elif getattr(args, "z", None) is None:
        a0 = argparse.Namespace(**vars(args))
        a0.z, a0.sigma = None, getattr(args, "sigma", None)
        n_cand = sum(len(r["cand"]) for r in
                     (judge_quota(vals, ref, ref_raw, a0, h) for h in hands) if r)
        args.z = z_for(max(1, n_cand * max(1, getattr(args, "looks", 1))))
        args.z_src = f"Bonferroni z_for({n_cand} 候选 × {getattr(args, 'looks', 1)} 次审阅)"
    else:
        args.z_src = "手动指定"
    args.z_txt = "**关闭** (--no-sig)" if args.z is None else f"{args.z:.2f}"
    return args.z


# ═══════════════ 键位组合击内时间柱状图 (每次 occ 剔除时出图) ══════════════════════
# 2026-10-13 用户要求: "每次根据 occ 段进行剔除时, 画一张键位组合击内时间图, **格式和之前做过的
#   那张一样**" ⇒ 判定/审阅的**副产品图**。柱色 = 键数 · 误差棒 = ±1.253σ/√n_eff · 虚线 = 参考中心。
# ⭐ **柱高 = 绝对时间 (ms)**, 不是无量纲比值（2026-10-13 用户"如果是…不是的话, 按照预测的毫秒数来
#   绘制"）: 柱高 = 该组合的**综合 occ 期望耗时 = 该手参考中心(ms) × 综合比 θ** —— θ 就是判定用的
#   那个量（各角色与同角色参考配对的 log 比, 1击:2击 = 1:2 加权）, 乘上**每手一个常数**（参考中心）
#   是**纯单调换算** ⇒ 名次/斜纹与判据一字不变, 只是 y 轴从 0.7~1.5 变成 ~80~170 ms。
#   ⚠ 它是**判定口径的 ms 表达**（观测中位的加权合成, 无键级收缩、全量窗口）; `产物/当量表-并击-*.npz`
#   里的 occ = 生产模型预测（含键级收缩、稳定期口径）—— 两者不同, 本图跟随判据。
# ⚠ **标记按现行口径（2026-10-13 用户「柱状图不要体现现有硬剔」）**:
#     **斜纹 = 本轮显著出局（拟剔）**, 且**唯一**标记 —— 旧版另有"斜纹 = 已在排除表(硬剔) +
#     红边 = 本轮显著出局" 两档 (再往前的判据 B: 配额割线 ▼ / 降权表红边 已于 2026-10-12 撤除)。
#     为什么去掉"表状态"档: 判据与表两个层面混在一张图上会让人把"已停采"读成"本轮判定"。
# ⭐ **2026-10-13 用户改版**: "左右手放到一张柱状图里, **按排序放置, 即左1右1左2右2……**,
#   **52 后不显示标记**" ⇒ 产物只剩**一张** `组合相对耗时-双手.png`（不再出手单图）:
#   左右手各自按 occ 比升序、交错成 2×79 根; 左手深色 / 右手同色系浅色 (+ 右手道浅灰底纹);
#   刻度 = 各手自己的名次 + 组合名; **▼ 整档去掉** —— 它只画在「名次 > 保险线」处, 那些位置
#   全在 52 之后 ⇒ 按「52 后不显示标记」不画（"候选区"信息保留在标题计数里）。
# 唯一实现: 判定值走 `_ratio_of` (与判据同一函数同一参考), 标记走 `judge_quota` / `action_set` 的产出
#   ⇒ 不另立口径; `实验/实验-组合相对耗时柱状图.py` 已改成调用本函数 (同一产物名)。
KC_COLOR = {1: "#1f77b4", 2: "#2ca02c", 3: "#d62728"}


def plot_occ_bars(win, hands, args, vals=None, ref=None, ref_raw=None,
                  runs=None, action=None, sigma=None, sigma_src="", outdir=None):
    """画 **键位组合击内时间柱状图**（y = 综合 occ 期望耗时 ms; 左右手交错一张）→ `组合相对耗时-双手.png`

    `vals/ref/ref_raw/runs/action` 可注入 (main 已算好 ⇒ 省一遍 collect); 缺省则本函数自算
    (实验脚本可直接调用)。返回写出的路径列表 (matplotlib 不可用时返回 [] 并提示, **绝不让剔除
    流程因出图失败而中断**)。本图恒用**判定窗口**的样本 (与名单同源)。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        import numpy as np
    except Exception as e:
        print(f"⚠ 跳过出图 (matplotlib/numpy 不可用: {e})")
        return []
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    outdir = Path(outdir) if outdir is not None else BASE
    line = int(getattr(args, "line", ELIM_LINE))
    if vals is None:                                          # 自算路径 (实验脚本)
        vals, ref, ref_raw, sig0, src0, _miss = _ctx(win, hands, "occ", args)
        a = argparse.Namespace(**vars(args))
        a.sigma = float(getattr(args, "sigma", None) or sig0)
        a.sigma_src = getattr(args, "sigma_src", None) or src0
        a.line, a.n_min = line, int(getattr(args, "n_min", 20))
        a.n_min_iso = int(getattr(args, "n_min_iso", 10))
        a.max_pairs = int(getattr(args, "max_pairs", ELIM_MAX_PAIRS))
        resolve_z(vals, ref, ref_raw, a, hands)
        args = a
    if runs is None:
        runs = {h: judge_quota(vals, ref, ref_raw, args, h) for h in hands}
    sigma = float(sigma if sigma is not None
                  else (getattr(args, "sigma", None) or 0.0)) or sigma_fallback("occ")
    sigma_src = sigma_src or getattr(args, "sigma_src", "") or ""
    hands = tuple(h for h in ("l", "r") if h in tuple(hands) and runs.get(h))
    if not hands:
        return []
    if action is None:
        if len(hands) == 2:                     # 正式审阅: 动作集 = 镜像并集 + 上限
            action = action_set(runs, args)[0]
        else:                                   # 单手诊断: 并集需两侧 ⇒ 退画**该手名义出局** (cut)
            action = {pair_id(c) for c in (runs.get(hands[0]) or {}).get("cut", set())}
    act = {pair_id(c) for c in action}              # 动作集 = 左手形式 ⇒ 归一后按**镜像对**比较
    PROT3 = set(REF_COMBO.values())                 # {sdf, lkj}: 3 键永不剔 ⇒ 不画斜纹

    def is_out(c):
        return c not in PROT3 and pair_id(c) in act

    def hand_data(h):
        res = runs[h]
        data = []
        for c in (LEFT_COMBOS if h == "l" else RIGHT_COMBOS):
            got = _ratio_of(vals, ref, ref_raw, h, c, getattr(args, "iso_importance", 0.5))
            data.append(dict(c=c, nk=len(c), ratio=(got[0] if got else float("nan")),
                             n_eff=(got[1] if got else 0.0),
                             rank=res["rank"].get(c), cand=c in res["cand"]))
        data.sort(key=lambda d: (d["ratio"] if not np.isnan(d["ratio"]) else 9e9, d["c"]))
        for i, d in enumerate(data):            # 该手自己的名次 (0 基; 刻度用 i+1)
            d["idx"] = i
        return data

    def light(hexcolor, t=0.45):
        """颜色向白色混 t —— 右手用**同色系浅色**（保留「色码 = 键数」, 又能一眼分左右）"""
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % tuple(int(c + (255 - c) * t) for c in (r, g, b))

    wrote = []

    # ── **单张**柱状图（2026-10-13 用户「左右手放到一张柱状图里, 按排序放置, 即左1右1左2右2……,
    #    52后不显示标记」）: 两手都在 ⇒ **按名次交错**左1 右1 左2 右2 …; 只手 (诊断路径) ⇒ 顺排。
    #    ⚠ **去掉 ▼ 标记** —— 它只画在「名次 > 保险线」处, 那些位置全在 52 之后 ⇒ 按「52 后不显示
    #    标记」整档不画（"候选区"信息保留在标题计数里）。左手深色 / 右手同色系浅色 + 右手道浅灰底纹。
    two = len(hands) == 2
    dl = hand_data("l") if "l" in hands else []
    dr = hand_data("r") if "r" in hands else []
    if two:
        npair = max(len(dl), len(dr))
        slot = []                              # [(x, data, hand)] —— x = 2i (左) / 2i+1 (右)
        for i in range(npair):
            if i < len(dl):
                slot.append((2 * i, dl[i], "l"))
            if i < len(dr):
                slot.append((2 * i + 1, dr[i], "r"))
        fname = "组合相对耗时-双手.png"
    else:
        h0 = hands[0]
        d0 = dl or dr
        slot = [(i, d0[i], h0) for i in range(len(d0))]
        fname = f"组合相对耗时-{'左手' if h0 == 'l' else '右手'}.png"
    npos = max(x for x, _d, _h in slot) + 1
    iso_imp = float(getattr(args, "iso_importance", 0.5) or 0.5)

    def ref_ms(h):
        """该手的**加权参考中心 (ms)** = 各角色「双键 pooled 中位」按 1击:2击 权重 (iso_imp : 1) 的
        几何均值 —— 与 `_ratio_of` 的加权口径同源 ⇒ **柱高 = θ × 参考中心 = 该组合的综合 occ 期望
        耗时 (ms)**。这是**纯单调换算**（每手一个常数）⇒ 名次 / 斜纹与判据一字不变, 只是把
        无量纲的比值换成 ms（读数直观; 且左右手同轴 ⇒ 两手 ms 可直接比）。"""
        ns = {r: ref[(h, r)][1] for r in ROLES if (h, r) in ref}
        m = {r: ref[(h, r)][0] for r in ROLES if (h, r) in ref}
        if not ns:
            return float("nan")
        w = role_weights(ns, (iso_imp, 1.0))
        den = sum(w.values())
        return math.exp(sum(w[r] * math.log(m[r]) for r in ns if w[r] > 0) / den) if den > 0 \
            else float("nan")

    R = {h: ref_ms(h) for h in hands}
    for _x, d, h in slot:                      # ms = 综合比 × 该手参考中心
        d["ms"] = d["ratio"] * R[h]
    ys = [d["ms"] for _x, d, _h in slot if not np.isnan(d["ms"])]
    lo_v, hi_v = min(ys), max(ys)
    fig, ax = plt.subplots(figsize=(24 if two else 16, 7.5 if two else 6.5))
    if two:                                    # 右手道浅灰底纹（视觉分组）
        for i in range(npos // 2):
            ax.axvspan(2 * i + 0.5, 2 * i + 1.5, color="#f2f2f2", zorder=0)
    for x, d, h in slot:
        if np.isnan(d["ms"]):
            ax.text(x, lo_v - 0.015 * hi_v, "无数据", rotation=90, ha="center", va="top",
                    fontsize=5.0, color="#999")
            continue
        se = 1.253 * sigma / np.sqrt(max(1.0, d["n_eff"]))       # log 尺度 1σ（含参考侧）
        ax.bar(x, d["ms"], width=0.86 if two else 0.78,
               color=(KC_COLOR[d["nk"]] if h == "l" else light(KC_COLOR[d["nk"]])),
               hatch="///" if is_out(d["c"]) else None,
               edgecolor=("#222" if is_out(d["c"]) else "white"),
               linewidth=(1.2 if is_out(d["c"]) else 0.35))
        ax.errorbar(x, d["ms"], yerr=[[d["ms"] * (1 - np.exp(-se))],   # 幅度恒为正
                                      [d["ms"] * (np.exp(se) - 1)]],
                    fmt="none", ecolor="#555", elinewidth=0.7, capsize=1.2, alpha=0.7, zorder=4)
    for h, lx, col in (("l", 0.008, "#333"), ("r", 0.030, "#8a8a8a")):
        if h in R and not np.isnan(R[h]):      # 每手一条参考中心线（两手可能不同 ⇒ 两条）
            ax.axhline(R[h], color=col, lw=1.0, ls="--", zorder=3)
            ax.annotate(f"{'左手' if h == 'l' else '右手'}参考中心 = {R[h]:.0f} ms",
                        (lx, R[h]), xycoords=("axes fraction", "data"), ha="left",
                        va=("bottom" if h == "l" else "top"), fontsize=8.2, color=col)
    ax.set_xlim(-1, npos)
    ax.set_ylim(lo_v - 0.055 * hi_v, hi_v * 1.045)
    ax.grid(axis="y", alpha=0.25, ls=":")
    lab = [""] * npos                          # 刻度 = 该手自己的名次 + 组合名
    for x, d, h in slot:
        lab[x] = f"{d['idx'] + 1:02d} {d['c']}"
    ax.set_xticks(range(npos))
    ax.set_xticklabels(lab, rotation=90, fontsize=5.0 if two else 7.0, fontweight="bold")
    for t, (x, d, h) in zip(ax.get_xticklabels(), slot):   # 3 键名红色; 左手深 / 右手浅灰
        t.set_color("#d62728" if d["nk"] == 3 else ("#111" if h == "l" else "#777"))
    ax.set_ylabel("综合 occ 期望耗时 (ms)")
    n2 = {h: sum(1 for d in (dl if h == "l" else dr) if d["nk"] == 2) for h in ("l", "r")}
    nc = {h: sum(1 for d in (dl if h == "l" else dr) if d["cand"]) for h in ("l", "r")}
    nout = sum(1 for _x, d, _h in slot if is_out(d["c"]))
    head = ("键位组合击内时间 (ms) — 左右手交错一张图: 左1 右1 左2 右2 … "
            f"（共 {npos} 根 = 2 × {len(dl)}）" if two else
            f"{'左手' if hands[0] == 'l' else '右手'} · 79 个键位组合的击内时间 (ms)")
    sub = ("深色 = 左手 / 浅色 = 右手（右手道另有浅灰底纹）; " if two else "")
    cnt = (f"双键 {n2['l']}/{n2['r']} 个（左/右）; 候选（名次 > {line}）{nc['l']}/{nc['r']} 个"
           if two else f"双键 {n2[hands[0]]} 个; 候选（名次 > {line}）{nc[hands[0]]} 个")
    ax.set_title(
        f"{head}\n{sub}按该手的综合 occ 比升序（= 判定名次）; 刻度 = 各手自己的名次 + 组合名（红字 = 3 键）\n"
        f"柱高 = 该手参考中心(ms) × 综合比 θ = 该组合的综合 occ 期望耗时"
        f"（θ = 各角色与同角色参考配对的 log 比, 1击:2击 = 1:2 加权 —— 判定用的同一量, 纯换算）; "
        f"误差棒 = ±1.253σ/√n_eff（log 尺度, 含参考侧）; σ(log occ) = {sigma:.2f} [{sigma_src}]",
        fontsize=11.5 if two else 11)
    ax.text(0.995, 0.965, f"{cnt}; 本轮出局 {len(act)} 对 × 2 手 = {nout} 根（斜线 = 拟剔, 已按镜像并集算）",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color="#333")
    ax.legend(handles=[Patch(fc=KC_COLOR[1], label="1 键（深 = 左手 / 浅 = 右手）" if two
                             else "1 键（保护: 固定不剔）"),
                       Patch(fc=KC_COLOR[2], label="2 键"),
                       Patch(fc=KC_COLOR[3], label="3 键 (sdf/lkj, 保护)"),
                       Patch(fc="white", ec="#222", hatch="///",
                             label=f"斜线 = 显著慢于第 {line} 名（拟剔, 镜像并集 {len(act)} 对）")],
               loc="upper left", fontsize=8.5, ncol=2)
    fig.tight_layout()
    p = outdir / fname
    fig.savefig(p, dpi=150)
    plt.close(fig)
    wrote.append(p)
    print(f"→ {p}")
    return wrote


# ═══════════════ 主流程 ══════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", choices=["l", "r", "both"], default="both",
                    help="只手 = 只出该手名单 (**不写表**: 镜像并集需要两侧)")
    ap.add_argument("--window", type=int, default=0,
                    help="滑动窗口试次数 (默认 0 = 全量; 窗口过小则每组合样本永远不够 n_min)")
    ap.add_argument("--n-min", type=int, default=20, help="进名单的门槛 (综合 n_eff)")
    ap.add_argument("--n-min-iso", type=int, default=10, help="iso 角色门槛 (孤立样本天然更少)")
    ap.add_argument("--line", type=int, default=ELIM_LINE,
                    help=f"**保险线** (默认 {ELIM_LINE}): 名次 ≤ 它 = 保险保留 (永不剔); "
                         f"名次 > 它 = **候选** (是否出局由显著性 + 上限决定)")
    ap.add_argument("--max-pairs", type=int, default=ELIM_MAX_PAIRS,
                    help=f"**行动上限** (默认 {ELIM_MAX_PAIRS}): 一次审阅最多剔多少个镜像对 "
                         "(用户 2026-10-12: 最多只剔除 28 对)")
    ap.add_argument("--z", type=float, default=None,
                    help="显著性 z (默认 auto = Bonferroni z_for(候选判定数 × --looks); 序贯审阅不膨胀)")
    ap.add_argument("--looks", type=int, default=1, help="序贯审阅次数 (Bonferroni 分摊到每次审阅)")
    ap.add_argument("--no-sig", action="store_true",
                    help="**诊断开关**: 关掉显著性闸门 (出局 = 纯名次 > --line) —— 仅对照用, 不可写表")
    ap.add_argument("--iso-importance", type=float, default=0.5,
                    help="1击组:2击组 权重比 (0.5 = 1:2, 用户 2026-09-24 定); 0 = 纯按样本数")
    ap.add_argument("--ref", choices=list(REF_MODES), default=REF_MODE_DEFAULT,
                    help="参考水平: pooled = 该手 2 键组合总体中心 (默认, 不依赖 sdf) | sdf = 旧锚 (对照)")
    ap.add_argument("--dry-run", action="store_true", help="只打印, 不写排除表")
    ap.add_argument("--force", action="store_true",
                    help=f"越过**写表门禁** (可排名双键比例 < {QUOTA_WRITE_RANK_FRAC:.0%} 时默认拒写; "
                         f"依据 实验/实验-新口径样本量.py 的闭环结论)")
    ap.add_argument("--table", nargs="?", const=TABLE_DEFAULT, default=None, metavar="PATH",
                    help=f"额外导出**完整剔除分析表** → PATH.md + PATH.tsv (默认前缀 {TABLE_DEFAULT}); "
                         f"**只读**, 不写排除表, 与 --dry-run 可同用")
    ap.add_argument("--pool", choices=list(POOLS), default=POOL_DEFAULT,
                    help="判定用的样本池: **full = 全量窗口（默认**; 2026-10-13 用户「这样采集效率太低了, "
                         "改回用全部数据判断剔除」—— 数据立刻全部可用) / stable = 稳定期（与模型同一池; "
                         "样本量只有 ~44–48%, 名单常短于保险线 ⇒ 一个都不剔; 供「当前状态」审阅对照）")
    ap.add_argument("--bench", choices=list(BENCH_KINDS), default=BENCH_DEFAULT,
                    help="显著性闸门的**基准时间**取法: **data = 第 N 名的数据 θ（默认**; "
                         "**两侧噪声都算** —— 2026-10-13 用户「现在剔除的太快了, 改成比 52 名显著**长**"
                         "（含两侧噪声）」) / model = 第 N 名的 occ 模型时间（与判定同池的 `ShrunkModel`, "
                         "视为已知 ⇒ 阈值只含候选侧噪声; 实测更快, 只作对照）")
    ap.add_argument("--selftest", action="store_true", help="合成数据自测判据")
    ap.add_argument("--no-plot", action="store_true",
                    help="跳过**键位组合击内时间柱状图** (默认每次 occ 剔除都出图: "
                         "组合相对耗时-双手.png; `--hand l|r` 出同名单手图)")
    args = ap.parse_args()
    args.metric = "occ"
    args.iso_importance = args.iso_importance if args.iso_importance > 0 else None
    if args.line < 1:
        ap.error("--line 须 ≥ 1")

    if args.selftest:
        selftest(args)
        return

    rows = read_tsv(DATA)
    if not rows:
        print(f"无数据: {DATA} (尚未开始采集)")
        return
    total = len(rows)
    win = rows[-args.window:] if args.window > 0 else rows
    args.win_n = len(win)
    hands = ("l", "r") if args.hand == "both" else (args.hand,)

    for h in hands:                                     # 稳定期参考 (仅报告, 不影响判定)
        vals_ = [v for v in (word_occ(r, h) for r in win if r.get("error", "0") == "0") if v]
        if vals_:                                       # 错误行须滤掉 (包络 σ_b 会被抬高而发散)
            _, msg = stable_start(vals_)
            print(f"[稳定期·{h}手 wc] {msg}")

    vals, ref, ref_raw, sig, sig_src, missing = _ctx(win, hands, "occ", args)
    for h, role, n, need in missing:
        what = REF_COMBO[h] if args.ref == "sdf" else "2键组合总体"
        print(f"⚠ 参考 {what}@{role} 样本不足 (n={n} < {need}) — 该角色不参与判定")
    print(f"数据 {total} 行" + (f" (窗口末 {len(win)})" if args.window > 0 else " (全量)") +
          f" | σ(log occ) = {sig:.2f} [{sig_src}] | 参考 [{args.ref}] | 保险线 名次 ≤ {args.line} | "
          f"池 [{args.pool}]" + ("（稳定期, 与模型同一池）" if args.pool == "stable" else "（全量窗口）") +
          f" | 基准 [{args.bench}]" + ("（第 N 名的 occ 模型时间, 视为已知）" if args.bench == "model"
                                     else "（第 N 名的数据 θ, 两侧噪声）"))
    # 显著性 z: 唯一解析见 resolve_z (--no-sig ⇒ None / --z ⇒ 手动 / 否则 Bonferroni 两遍)
    args.sigma = sig                          # σ 先落 args (resolve_z / 判定 / 出图共用)
    resolve_z(vals, ref, ref_raw, args, hands)
    z_txt = args.z_txt
    print(f"显著性闸门: z = {z_txt} [{args.z_src}] ⇒ 候选需 **occ 时间显著大于第 {args.line} 名** "
          f"({_sig_txt(args)}); 名次到线但证据不足 ⇒ 保留")
    if args.no_sig:
        print("  ⚠ --no-sig: 已关闭显著性闸门 (纯名次, 只看 --line) —— 仅供对照, 不可据此写表")
    runs = {h: judge_quota(vals, ref, ref_raw, args, h) for h in hands}
    # 动作集先算一次 (唯一实现) —— 供名次表的 9×7 视图标 ✗, 也供后面的镜像并集段与写表复用
    if len(hands) == 2:
        args.action, args.dropped, args.excl_map = action_set(runs, args)
    else:
        args.action, args.dropped, args.excl_map = set(), set(), {}
    report(runs, args)
    exclude, reasons = set(), []
    if len(hands) == 2:
        exclude, reasons = report_mirror(runs, args)
    else:
        print("\n(注: --hand 只手 ⇒ 只出名单, **不写表**; 镜像并集需要两侧 ⇒ 默认 --hand both)")

    # **键位组合击内时间柱状图** (2026-10-13 用户要求"每次根据 occ 段进行剔除时画一张…"):
    # 单次调用点 = 判定/动作集已定、写表之前 ⇒ 图里 斜纹 = **本轮显著出局 (拟剔)** (dry-run 与写表一致)
    if not args.no_plot:
        plot_occ_bars(win, hands, args, vals=vals, ref=ref, ref_raw=ref_raw,
                      runs=runs, action=args.action, sigma=sig, sigma_src=sig_src)

    if args.table:                                      # 完整分析表 (只读)
        tp = Path(args.table)
        write_table(win, hands, args, str(tp if tp.is_absolute() or tp.parent != Path(".")
                                          else BASE / tp))

    # ── 写表门禁: 证据不足时不写 (可排名双键比例, 取最差手) ──────────────────────
    n_dbl_rank = {h: sum(1 for c in (runs[h]["ranked"] if runs.get(h) else ()) if len(c) == 2)
                  for h in hands}
    gate_ok, gate_msg = elim_write_gate(min(n_dbl_rank.values(), default=0))
    print(f"\n样本量门禁 (写表): {gate_msg} ⇒ " +
          ("放行 —— 可排名已覆盖绝大多数双键, 名次不会误伤" if gate_ok else
           "**不放行** —— 名次还建立在掷硬币式的结果上; 继续采集, 只出名单"))
    print("   各手可排名双键: " + "  ".join(f"{h}手 {n}/{TWO_KEY_PER_HAND}"
                                            for h, n in sorted(n_dbl_rank.items())) +
          "  (门禁取最差手)")
    if len(hands) < 2:
        return
    if args.dry_run:
        print("(--dry-run: 未写入排除表)")
        return
    if not gate_ok and not args.force:
        print(f"⛔ 本轮**不写表** ({gate_msg}; 要强制写入加 `--force`)。\n"
              f"   排除表保持原样 (手工段不受影响); 名单见上方报告, 继续采集即可。")
        return
    if not gate_ok:
        print("⚠ --force: 越过写表门禁, 按当前 (证据不足的) 名次改写排除表 —— 后果自负。")
    if args.no_sig:
        print("⛔ --no-sig 是**诊断开关** (关掉了显著性闸门) ⇒ 本轮不写表; "
              "去掉它再跑才是正式动作。")
        return

    old_auto, old_manual = read_existing(EXCLUDE_TXT)
    legacy = sorted(old_auto - exclude)                # 既有但本轮规则不再产出 (判据 A 时代遗留)
    auto = set(exclude) | set(legacy)                  # **追加式: 只增不减** (硬剔不可逆)
    head = [
        "# 组合排除表 — **唯一一张动作表** (名次候选 + 显著性 + 镜像并集; README §4.4.1/§4.5)",
        f"# 名单 = 该手 79 组合 (15 单键 + 63 双键 + 1 三键参考) 按**综合 occ 比**升序 (快→慢); "
        f"θ = 同角色参考配对的 log 比, 1击:2击 = 1:2 加权; occ = 整击占用 lu−fd",
        f"# 出局 = ① 名次 > {args.line} (候选; 名次 ≤ {args.line} = 保险保留) ∧ ② **occ 时间显著大于"
        f"第 {args.line} 名** ({_sig_txt(args)}, z = {args.z_txt}) ∧ ③ 镜像并集后按坏影响取前 "
        f"{args.max_pairs} 对 (行动上限) ⇒ **硬剔, 不可逆**",
        f"# 保护 = {SINGLES_PER_HAND} 单键 + 1 三键参考 (固定不剔) | 不可排名者 (n_eff < "
        f"{args.n_min}) 不判不动 | 动作 = **任一侧出局 ⇒ 镜像对两侧一起写表** (并集)",
        "# **条目只写左手键位** (右手 = `mirror_combo(左)` 由采集器推导; 2026-10-13 用户决策 —— 剔除对称)",
        "# **分类顺序 = 9×7** (列形态 → 行对, 槽位序; 2026-10-13 用户要求): 自动段按列形态分组, "
        "每条的 `# 备注` = 行对 + **相对速度** (θ, 1.00 = 同角色参考中心; 1.35 = 慢 35%) + 判定",
        "# **自动段追加式 (只增不减)**: 硬剔不可逆 ⇒ 工具不自动撤销任何既有条目; 要恢复采样请**手工删行**",
        f"# σ(log occ) = {sig:.2f} [{sig_src}] | 窗口 = 末 {len(win)} 试次",
        f"# 参考水平 [{args.ref}]: " +
        "  ".join(f"{h}@{r}={m:.0f}ms(n={n})" for (h, r), (m, n) in sorted(ref.items())),
        f"# 生成于 {time.strftime('%Y-%m-%d %H:%M')}; 手工条目请置于 '# [manual]' 之后 (工具原样保留)",
    ]
    def _note(p):
        """条目行内备注: **行对 + 相对速度 (左右两侧) + 判定** (左手键位为准)"""
        if p not in args.excl_map:                     # 既有条目 (本轮规则未产出)
            return "既有条目 (本轮规则未产出; 硬剔不可逆 ⇒ 保留; 见 剔除分析表.md/.tsv)"
        a, b = args.excl_map[p]
        rc = mirror_combo(p)
        tl, tr = runs["l"]["ranked"].get(p), runs["r"]["ranked"].get(rc)
        evl = f"{_speed(tl[0])} #{runs['l']['rank'][p]}" if tl else "—"
        evr = f"{_speed(tr[0])} #{runs['r']['rank'][rc]}" if tr else "—"
        st = ("两侧同出局" if a and b else "仅左手出局(并集带动右)" if a else "仅右手出局(并集带动左)")
        return f"{_row_label(row_pair(p))} · 左 {evl} · 镜像右 {evr} · {st}"

    groups = []                                        # **按 9×7 分类顺序**分组 (列形态 → 行对)
    for cp in COL_PAIRS:
        grp = sorted([p for p in auto if col_pair(p) == cp],
                     key=lambda p: ROW_PAIRS.index(row_pair(p)))
        if grp:
            groups.append((f"# ── {'+'.join(SLOT_NAME[x] for x in cp)} "
                           f"(列形态 {COL_PAIRS.index(cp) + 1}/9; 出局 {len(grp)}/7 格) ──",
                           [(p, _note(p)) for p in grp]))
    if args.dropped:                                   # 超上限未动的对也记一行 (可追溯)
        head.append("# ⚠ 因行动上限未动的对: " +
                    " ".join(f"{p}({_row_label(row_pair(p))}, 左 {_speed(runs['l']['ranked'][p][0])})"
                             if p in runs["l"]["ranked"] else p for p in sorted(args.dropped)))
    write_exclude(EXCLUDE_TXT, auto, old_manual, head, groups)
    added = exclude - old_auto
    print(f"已写入 {EXCLUDE_TXT.name}: 自动段 {len(auto)} 条 "
          f"(本轮新增 {len(added)}; 既有保留 {len(old_auto - exclude)}" +
          (f", 其中遗留 {len(legacy)} 条: {' '.join(legacy)}" if legacy else "") + ")" +
          (f", 手工段原样保留 {len(old_manual)} 条" if old_manual else ""))
    if args.table:                                      # 写表后重出一次 (动作表列反映写入后状态)
        tp = Path(args.table)
        write_table(win, hands, args, str(tp if tp.is_absolute() or tp.parent != Path(".")
                                          else BASE / tp))


# ═══════════════ 合成数据自测 (合成真值: 一组 18 个双键 ×1.6 = 真慢 ⇒ 必须全部出局) ═══════
def _synth_vals(hand, n_per=40, slow=1.6, slow_set=None, seed=7):
    """合成该手样本 (自测用) → (vals, slow_set)
    真慢集默认 = 按键序**最后 18 个双键** (×slow); 单键/三键 ×0.85 (恒在前列, 与真实一致)"""
    rng = random.Random(seed + (0 if hand == 'l' else 1000))
    combos = sorted(LEFT_COMBOS if hand == 'l' else RIGHT_COMBOS)
    doubles = [c for c in combos if len(c) == 2]
    slow_set = set(doubles[-18:]) if slow_set is None else set(slow_set)
    vals = {}
    for c in combos:
        f = slow if c in slow_set else (0.85 if len(c) != 2 else 1.0)
        for role in ROLES:
            n = n_per // 2 if role == "iso" else n_per
            vals[(hand, role, c)] = [120.0 * f * math.exp(0.13 * rng.gauss(0, 1))
                                     for _ in range(n)]
    return vals, slow_set


def _selftest_read_existing():
    """排除表解析: **条目行内 `#` 备注必须被剥掉**（v10 修复的回归守卫）
    ⚠ 曾坏: 整行解析 ⇒ 带备注的条目全被当"无效行"丢掉 ⇒ 追加式"只增不减"静默失效
    （行动集缩小时, 下次写表会把其余既有条目一起丢掉 = 偷偷恢复采样）。"""
    import tempfile
    lines = ["# 头部注释（提到 # [manual] 也不算段标记）",
             "# ── 小+无 (列形态 1/9) ──",
             "qs     # 上→中 · 左 1.19 (+19%) #70 · 镜像右 1.42 (+42%) #78",
             "aw",                                     # canonical 槽位序 (旧写法 `wa` 同义)
             "pk     # 右手行（qd/pk 镜像对）⇒ 归一到左手形式 qd",
             "",
             "# [manual] 手工段",
             "sdf    # 3 键登记",
             "qg     # 手工条目带备注"]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write("\n".join(lines) + "\n")
        path = tf.name
    auto, manual = read_existing(path)
    Path(path).unlink()
    assert auto == {"qs", "aw", "qd"}, (sorted(auto),)   # pk → qd（镜像归一）
    # 注: 条目的**组合合法性**由采集器 `load_excluded` 负责（它按组合空间校验, 见其自测）;
    #     本处只保证"行内备注被剥掉 / 右手归一 / 段标记正确"。
    assert manual == {"sdf", "qg"}, sorted(manual)
    print(f"  ✓ 排除表解析: 行内 `#` 备注已剥掉（自动段 {len(auto)} 条 / 手工段 {sorted(manual)}）· "
          f"裸行兼容 · 右手行归一 · 非法行忽略")


def selftest(args):
    """合成数据自测: 口径纯函数 (并击公共) + 端到端 (名次候选 / 显著性闸门 / 28 对上限 /
    保护 / 镜像并集 / 保险线可调 / 数据不足 / 门禁)"""
    print("═══ 剔除口径自测 (名次候选 + 显著性 + 镜像并集 + 上限) ═══")
    _selftest_read_existing()
    selftest_layout()                    # 键盘布局/KEY_POS (2026-10-13 加, 防批量改名误伤布局串)
    selftest_elim()
    selftest_cells()                     # 9×7 分类 (63 双键 ↔ 9 列形态 × 7 行对)
    selftest_boundary()
    selftest_quota()                     # 已撤除层的纯函数 (历史实验脚本仍 import ⇒ 不许烂掉)
    a = argparse.Namespace(hand="both", window=0, n_min=20, n_min_iso=10, line=ELIM_LINE,
                           max_pairs=ELIM_MAX_PAIRS, z=4.0, looks=1, iso_importance=0.5,
                           ref=REF_MODE_DEFAULT, sigma=0.17, sigma_src="自测",
                           dry_run=True, force=False, metric="occ",
                           pool="full", bench="data")     # 自测钉**数据基准** (断言按它写的; 池不影响自测)
    vals, slow_l = _synth_vals('l')
    vals_r, slow_r = _synth_vals('r')
    vals.update(vals_r)
    ref, ref_raw = {}, {}
    for h in ("l", "r"):
        rr, raw, _miss = hand_ref(vals, h, a)
        ref.update(rr); ref_raw.update(raw)
    runs = {h: judge_quota(vals, ref, ref_raw, a, h) for h in ("l", "r")}
    # ① 强证据臂 (真慢 ×1.6 ⇒ 显著): 18 个真慢必须全部出局; 保护集不动; 名次连续
    #    (候选 = 名次 ELIM_LINE+1..79 = 79-ELIM_LINE 个 = 18 真慢 + 恰越线的快组合 ⇒ 后者不显著)
    n_fast_cand = 79 - ELIM_LINE - 18                     # 越线的快组合数 (随 ELIM_LINE 变)
    for h, slow in (("l", slow_l), ("r", slow_r)):
        res = runs[h]
        assert set(res["cut"]) == slow, (h, sorted(set(res["cut"]) ^ slow))
        assert len(res["cand"]) == 79 - ELIM_LINE and len(res["cut"]) == 18, len(res["cut"])
        assert len(res["insig"]) == n_fast_cand and set(res["insig"]) == set(res["cand"]) - slow, \
            sorted(res["insig"])
        assert res["ref_combo"] == res["info"]["boundary"][0], res["ref_combo"]
        assert not (set(res["cut"]) & elim_protect(h)), "保护集被剔"
        assert set(res["protect"]) <= set(res["rank"]) and not (set(res["protect"]) & set(res["cut"]))
        assert set(res["rank"]) == set(res["ranked"]) and len(res["rank"]) == 79, len(res["rank"])
        assert sum(1 for c in res["keep_all"] if len(c) == 2) == ELIM_LINE - ELIM_PROTECT, \
            f"保险线 = 第 {ELIM_LINE} 名 ⇒ 名义保留 = 15 单键 + {ELIM_LINE - ELIM_PROTECT} 双键 + 1 三键"
        assert not res["unrankable"] and res["soft"] == set()
    # ①b **模型基准臂** (`--bench model`, 2026-10-13 用户「改成比 52 名的 occ 模型时间显著大」):
    #     基准 = 第 ELIM_LINE 名的 **occ 模型时间**, 视为已知 ⇒ 阈值只含候选侧噪声
    #     ⇒ 阈值更低、出局 ⊇ 数据基准档 (单调放宽), 且真慢集仍全中。
    am = argparse.Namespace(**vars(a))
    am.bench = "model"
    runs_m = {}
    for h, slow in (("l", slow_l), ("r", slow_r)):
        rm = judge_quota(vals, ref, ref_raw, am, h)
        runs_m[h] = rm
        assert rm["ref_model"] is not None and rm["ref_pair"][1] is None, rm["ref_pair"]
        assert abs(rm["ref_model"] / rm["ref_data"][0] - 1) < 0.25, \
            (rm["ref_data"], rm["ref_model"])
        assert slow <= set(rm["cut"]), sorted(slow - set(rm["cut"]))
        assert set(runs[h]["cut"]) <= set(rm["cut"]), \
            f"模型基准应更宽 (出局 ⊇ 数据基准档): {sorted(set(runs[h]['cut']) - set(rm['cut']))}"
        n_lo = sum(1 for c in runs[h]["cand"] if rm["margins"][c] < runs[h]["margins"][c])
        assert n_lo > len(runs[h]["cand"]) * 0.8, (n_lo, len(runs[h]["cand"]))
    print(f"  ✓ 模型基准臂 (`--bench model`): 基准 θ 数据→模型 = "
          + " / ".join(f"{runs[h]['ref_data'][0]:.3f}→{runs_m[h]['ref_model']:.3f}" for h in ("l", "r"))
          + " · 出局 ⊇ 数据基准档 · 阈值全面更低 (基准噪声不再计入); `--bench data` 逐位复现旧口径")
    # ★ ② 弱证据臂 (真慢 ×1.05 < 显著阈): **名次到线但证据不足 ⇒ 一个都不出局** (用户第二轮要求)
    vm, slow_m = _synth_vals('l', slow=1.05)
    refm, rawm = {}, {}
    for h in ("l",):
        rr, raw, _m = hand_ref(vm, h, a)
        refm.update(rr); rawm.update(raw)
    rm = judge_quota(vm, refm, rawm, a, "l")
    assert len(rm["cand"]) == 79 - ELIM_LINE and rm["cut"] == set() \
        and set(rm["insig"]) == set(rm["cand"]), (len(rm["cand"]), sorted(rm["cut"]))
    # --no-sig (z=None): 关掉显著性闸门 ⇒ cut = 候选全量 (仅诊断口径)
    a0 = argparse.Namespace(**vars(a)); a0.z = None
    assert set(judge_quota(vm, refm, rawm, a0, "l")["cut"]) == set(rm["cand"])
    # ③ 镜像并集: 只手显著也一起剔 (右手真慢集 = 左手镜像去掉 1 个 + 另加 1 个 ⇒ 2 对只手差)
    doubles_l = sorted(c for c in LEFT_COMBOS if len(c) == 2)
    slow_r2 = {mirror_combo(c) for c in sorted(slow_l)[1:]} | {mirror_combo(doubles_l[0])}
    vals2 = {k: v for k, v in vals.items() if k[0] == 'l'}
    v2r, _ = _synth_vals('r', slow_set=slow_r2, seed=9)
    vals2.update(v2r)
    ref2, raw2 = {}, {}
    for h in ("l", "r"):
        rr, raw, _m = hand_ref(vals2, h, a)
        ref2.update(rr); raw2.update(raw)
    runs2 = {h: judge_quota(vals2, ref2, raw2, a, h) for h in ("l", "r")}
    excl = elim_mirror(runs2["l"]["cut"], runs2["r"]["cut"])
    only_l = {p for p, (x, y) in excl.items() if x and not y}
    only_r = {p for p, (x, y) in excl.items() if y and not x}
    both = {p for p, (x, y) in excl.items() if x and y}
    assert len(both) == 17 and len(only_l) == 1 and len(only_r) == 1 and len(excl) == 19, \
        (len(both), len(only_l), len(only_r), len(excl))
    assert all(p in runs2["l"]["cut"] or mirror_combo(p) in runs2["r"]["cut"] for p in excl)
    # ★ ④ 行动上限: 两手真慢集**镜像不相交** ⇒ 并集 36 对 > 28 ⇒ 只剔 28 对 (其余本轮不动)
    slow_r3 = {mirror_combo(c) for c in doubles_l[20:38]}
    vals3 = {k: v for k, v in vals.items() if k[0] == 'l'}
    v3r, _ = _synth_vals('r', slow_set=slow_r3, seed=11)
    vals3.update(v3r)
    ref3, raw3 = {}, {}
    for h in ("l", "r"):
        rr, raw, _m = hand_ref(vals3, h, a)
        ref3.update(rr); raw3.update(raw)
    runs3 = {h: judge_quota(vals3, ref3, raw3, a, h) for h in ("l", "r")}
    ex3 = elim_mirror(runs3["l"]["cut"], runs3["r"]["cut"])
    kp, dp = elim_cap_pairs(set(ex3), {p: _pair_score(runs3, p) for p in ex3}, a.max_pairs)
    assert len(ex3) == 36 and len(kp) == ELIM_MAX_PAIRS == 28 and len(dp) == 8, \
        (len(ex3), len(kp), len(dp))
    assert kp | dp == set(ex3)
    # ⑤ 保险线可调 —— **基准随保险线一起移动** (第 line 名就是基准):
    #    line=55 ⇒ 基准落在快组合上 (θ≈1) ⇒ 候选 24 = 6 快 + 18 真慢 ⇒ 真慢 18 个显著出局
    a2 = argparse.Namespace(**vars(a)); a2.line = 55
    r55 = judge_quota(vals, ref, ref_raw, a2, "l")
    assert len(r55["cand"]) == 24 and len(r55["cut"]) == 18 and len(r55["insig"]) == 6, \
        (len(r55["cand"]), len(r55["cut"]), len(r55["insig"]))
    #    line=70 ⇒ 基准自己就在真慢组里 (θ≈1.5) ⇒ 候选 (同样 ≈1.5) 再也超不过它 ⇒ 出局 0
    a4 = argparse.Namespace(**vars(a)); a4.line = 70
    r70 = judge_quota(vals, ref, ref_raw, a4, "l")
    assert len(r70["cand"]) == 9 and r70["cut"] == set() and len(r70["insig"]) == 9 \
        and r70["ref_combo"] == r70["info"]["boundary"][0], (len(r70["cand"]), sorted(r70["cut"]))
    a3 = argparse.Namespace(**vars(a)); a3.line = 200
    assert judge_quota(vals, ref, ref_raw, a3, "l")["cut"] == set()
    # ⑥ 数据不足: n_eff < 门槛 ⇒ 一个都不剔 (全不可排名) + 写表门禁不放行
    v4, _ = _synth_vals('l', n_per=4)
    ref4, raw4, _ = hand_ref(v4, 'l', a)
    r4 = judge_quota(v4, ref4, raw4, a, 'l')
    assert r4["cut"] == set() and r4["order"] == [] and len(r4["unrankable"]) == 79
    assert not elim_write_gate(0)[0] and elim_write_gate(57)[0] and elim_write_gate(63)[0]
    print(f"剔除口径端到端自测通过 (保险线 {ELIM_LINE}): 强证据 18/18 出局 (候选 {79 - ELIM_LINE} = "
          f"18 真慢 + {79 - ELIM_LINE - 18} 越线快组合不显著) · 保护集不动 · 名义保留 {ELIM_LINE} = "
          f"15 单键 + {ELIM_LINE - ELIM_PROTECT} 双键 + 1 三键 / **弱证据(×1.05) 名次到线但未显著 ⇒ "
          f"0 出局** / --no-sig 对照全量候选 / 镜像并集 (17 两侧 + 2 只手差) / **并集 36 对 ⇒ 上限 28** / "
          f"基准随保险线移动 (line 55 ⇒ 出 18; line 70 ⇒ 基准自身已慢 ⇒ 出 0) / 数据不足不判不剔 / 写表门禁")


if __name__ == "__main__":
    main()
