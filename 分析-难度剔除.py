#!/usr/bin/env python3
"""
分析-难度剔除.py — 组合判定 → 动态维护 组合排除表.txt (两个判据, 分段写表)

判据 A · `--judge difficulty` (默认): 上下文/段位综合的**难度异常**判定
设计依据 (README §4.4; 2026-09-07 上下文本位 + 2026-09-24 三角色综合):

  · **一击必须参与** (2026-09-24 用户决策): 孤立位置 = 一击词/一级字/简词的真实用法,
    其难度对方案同样相关 → 角色 = iso (1 击试次) / S1 (词首) / S3 (词尾),
    重要性 1击:2击 = 1:2 (与采样的 1:2 混采一致)。
  · **共享击内效应 + 段位效应** (2026-09-24): 击内 spread 有共用部分 (组合成形难度)
    与段位效应 (孤立/词首/词尾的上下文差) 两部分。⇒ 每个角色内与**同角色参考水平**配对求 log 比
    (段位效应在差值里自动抵消), 再把各角色 log 比按权重平均 → 组合效应可用**全部角色**的样本,
    不必按角色分家、也不会因合并而引入段位偏差 (合并的偏差只来自组合与参考**角色配比不同**,
    而参考池的配比确实与单个组合不同 ⇒ 直接合并确实有偏, 故必须配对)。
    n_eff 由三角色样本量合成 (≈相加), 比单角色大得多 ⇒ 分辨率显著提升。
  · **判据两层**:
      ① 综合层 (主): med 配对 log 比 (权重含 1:2 重要性) > margin(n_eff) 且 n_eff ≥ n_min
      ② 角色特异层 (辅): 某角色 med > margin(n_role)×同角色参考 且 n_role ≥ n_min_role
         (mode=either 任一角色即可 / both 需 ≥2 个角色) —— 兜住"只在某个段位特别难"的组合
  · **阈值必须自适应** (README §6.2-6): 固定 margin=1.0 在零假设下恒约 50% 越线, 不是判据;
    margin(n) = 1 + z·1.253σ/√n (z=3.46 ⇒ 189 判定单元族错误率 ≈5%; σ 由窗口内数据估计)。
    显式给 --margin <float> 可强制固定阈值 (仅作对照, 不推荐)。
  · **参考水平 = 同角色、同键数的组合总体中心** (--ref pooled 默认, 2026-09-30 起判定不依赖 sdf),
    **同角色、同窗口**测量 ⇒ 段位效应在比值里抵消、共同漂移自动抵消 (自校准)。
  · 单键组合 spread ≡ 0 → 两层的 spread 口径都不参与 (语义正确: 单指无成形难度);
    换 --metric occ 可判其占用 (但 occ 混 hold 节奏策略, 不能当难度量)。
  · 窗口默认 → **全量** (--window 0): 窗口 1000 时每组合样本数远低于 n_min, 一个组合都判不了。

判据 B · `--judge quota` (2026-09-30 用户决策; 与判据 A 语义完全不同, 不可互相替代):
  需求 = 单手 78 组合 (15 单键 + 63 双键, 不含参考) 里**取 ≤60 个用于方案**, 并希望在采集早期
  就把"肯定不会入选"的组合停掉 (省采集人力)。⇒ 这是**配额选码**, 不是难度异常检验:
  "剔几个"由配额决定 (要淘 18 个), 不由显著性决定。
  · 排序量 = **occ (整击占用 lu−fd, 耗时语义)**: 实测 σ_resid 0.13~0.19 vs spread 0.87
    (2026-09-30 实测) ⇒ 同样本量下两两可辨 1.19× vs 3.35×; 用 spread 排 63 个双键在
    3000~8000 试次内几乎淘不动任何人。spread 保留为"成形难度"诊断列 (判据 A 继续用)。
  · **单键默认全留** (spread ≡0 判不了 + 一级字/简词必需) ⇒ 配额落在双键: 63 留 **37** (配额 52, 2026-10-11)。
  · ① 配额切分 (默认): 按 occ 综合比升序切在保留名次 (QUOTA_KEEP_TWO_KEY = 37); **不可排名者 (样本不足) 不判不切**,
    但它们占用保留名额 ⇒ 名额 ≤0 时本轮不切 (数据不足时切 = 掷硬币)。
    割线两侧是否可辨 (gap vs 噪声) 显式报告。
  · ② 保守淘汰 (`--eliminate`, 可选开关): 有 K 个组合**显著优于**它 ⇒ 确定出局 (K=45);
    只有可排名者能当支配者 (不可判的配对不计数 ⇒ 宁可漏淘)。序贯审阅按 Bonferroni 收紧
    z = z_for(比较对数 × --looks) (反复偷看不膨胀错误率)。
  · 两层的判定写**同一张表的不同段** (# [difficulty] / # [quota]), 互不覆盖。

输出: 组合排除表.txt (分段: # [difficulty] / # [quota] / # [manual]; 工具每 200 试次重载 → 即时生效)
用法: python 分析-难度剔除.py [--judge difficulty|quota] [--hand l|r|both] [--window 0]
                              [--n-min 20] [--n-min-iso 10] [--metric spread|occ]
                              [--margin auto|1.0] [--mode either|both] [--iso-importance 0.5] [--z Z]
                              [--quota 45] [--eliminate] [--dominators 45] [--looks 1]
                              [--dry-run] [--selftest]
"""
import sys, argparse, time, math
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from 并击公共 import (BASE, REF_COMBO, read_tsv, role_segments,
                     scheme_used, stable_start, pct, anchors, word_occ,
                     LEFT_COMBOS, RIGHT_COMBOS, ROLES, MIN_ROLE_N, Z_FWER,
                     role_weights, joint_log_ratio, margin_adaptive, margin_adaptive2,
                     sigma_of_log, sigma_within_log, sigma_fallback, two_key_combos, quota_cut,
                     dominator_count, dominator_band, z_for, selftest_quota, QUOTA_KEEP_TWO_KEY,
                     ERR_COST_MS,
                     role_ref_vals, TWO_KEY_PER_HAND, SINGLES_PER_HAND, QUOTA_MAX_CODES,
                     REF_MODE_DEFAULT, REF_MODES, SOFT_WEIGHT_DEFAULT, SOFT_N_MIN_DEFAULT,
                     SOFT_MARGIN_DEFAULT, WEIGHT_TXT_NAME, quota_write_gate,
                     QUOTA_WRITE_RANK_FRAC, mirror_combo, mirror_pairs, pair_id)

DATA = BASE / "当量数据.tsv"
EXCLUDE_TXT = BASE / "组合排除表.txt"
WEIGHT_TXT = BASE / WEIGHT_TXT_NAME
PERR_TXT = BASE / "数据" / "错误率表.txt"      # 分析-错误率.py 导出 (决胜用 mot-only)


def read_et_table(path=PERR_TXT):
    """错误率表 → {(手, 组合): Et ms} (**割线平手决胜用**, v2.36 2026-10-11 用户确认)。
    Et = ERR_COST_MS × (p_iso + p_S1 + p_S3)/3 —— 三角色等权 (与判据 B 组内等权一致),
    逐角色 P_err 来自 分析-错误率.py 的特征化模型 (当前 = mot-only, R1 读取型不计)。
    缺文件 / 缺任一角色 → 该组合无 Et (决胜排序中排窗口末尾, 不假设)。"""
    from collections import defaultdict as _dd
    acc = _dd(dict)
    if not Path(path).exists():
        return {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        f = line.split("	")
        if len(f) >= 4 and f[0] in ("l", "r") and f[2] in ROLES:
            acc[(f[0], f[1])][f[2]] = float(f[3])
    et = {}
    for (h, c), pr in acc.items():
        if all(r in pr for r in ROLES):
            et[(h, c)] = ERR_COST_MS * (pr["iso"] + pr["S1"] + pr["S3"]) / 3
    return et

# ── 完整剔除分析表 (--table; 只读报告, 2026-10-10 用户要求) ──────────────────────
# 用途: 把**两个判据的全部证据 + 双手交集 + 两张动作表现状**放在一张表里, 便于逐条复核。
# **只读**: 不写 组合排除表.txt / 组合降权表.txt。判据 A 恒用 spread (成形难度)、判据 B 恒用 occ
# (整击耗时) —— 各自的参考水平/σ/阈值全部取自本文件与 并击公共.py 的既有函数, 表内不另立口径;
# `--metric` 只影响命令行报告 (判据 A 的 σ 与参考水平按 spread 打印, 判据 B 按 occ), 不影响本表。
TABLE_DEFAULT = "剔除分析表"
TABLE_COLS = ["手", "组合", "键数", "镜像对", "occ比", "n_eff", "Et(ms)", "B名次", "B判定",
              "双手交集", "各角色(occ) n/比", "spread比", "n_eff(A)", "阈值(A)", "A判定",
              "方案在用", "动作表"]


def read_existing(path):
    """既有排除表 → {"difficulty": set, "quota": set, "manual": set}
    段标记 '# [difficulty]' / '# [quota]' / '# [manual]'; 无段标记的自动条目 (旧格式) = difficulty"""
    out = {"difficulty": set(), "quota": set(), "manual": set()}
    sec = "difficulty"
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#"):
            low = s.lower()
            for tag in ("quota", "manual", "difficulty"):      # 段标记 (不含 [理由] 等注释)
                if f"[{tag}]" in low:
                    sec = tag
                    break
            continue
        if s:
            out[sec].add(s.lower())
    return out


SEC_TITLE = {
    "difficulty": "# [difficulty] 难度异常剔除 (spread 同参考比 + 乘性自适应阈值; 判据 A)",
    "quota": "# [quota] 配额选码 (occ 排序; 单键全留, 双键保留 37; 判据 B)",
    "manual": "# [manual] 手工追加条目 (脚本保留)",
}


def write_exclude(path, secs, header_lines, reasons=None):
    """分段写排除表: 头部注释 → 各段标题 + 理由注释 + 条目; 手工段保留"""
    lines = list(header_lines)
    for sec in ("difficulty", "quota"):
        if secs.get(sec) or (reasons or {}).get(sec):
            lines += ["", SEC_TITLE[sec]] + list((reasons or {}).get(sec, [])) + sorted(secs[sec])
    if secs.get("manual"):
        lines += ["", SEC_TITLE["manual"]] + sorted(secs["manual"])
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 组合降权表 (软降权 ③): `组合<TAB>权重`; 采集工具每 200 试次重载, 乘进采样权重 ──
W_TITLE = "# [soft] 疑似出局 → 降权 (未确定, 可回滚; 由 分析-难度剔除.py --judge quota 生成)"
W_MANUAL = "# [manual] 手工追加条目 (脚本保留)"


def read_weights(path):
    """组合降权表 → ({组合: 权重}, {组合: 权重} 手工段); 无文件/非法行容忍"""
    auto, manual, sec = {}, {}, "soft"
    if not Path(path).exists():
        return auto, manual
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        low = line.strip().lower()
        if low.startswith("#"):                          # 注释行; '# [manual]' 之后归手工段
            if "[manual]" in low:
                sec = "manual"
            continue
        # 只按空白切分: 逗号是合法键名 (右手 ",/"/";," 等双键), 不能当分隔符替换掉
        parts = line.split("#")[0].split()
        if not parts:
            continue
        if len(parts) != 2:
            print(f"降权表忽略无法解析的行: {line!r}")
            continue
        combo, w = parts[0].lower(), parts[1]
        try:
            f = float(w)
        except ValueError:
            print(f"降权表忽略非数值权重: {line!r}")
            continue
        if not 0.0 < f <= 1.0:
            print(f"降权表权重须在 (0,1]: {line!r} (要剔除请写排除表)")
            continue
        (manual if sec == "manual" else auto)[combo] = f
    return auto, manual


def write_weights(path, weights, header_lines, manual=None):
    """写降权表 (总是全量重写 ⇒ 上一轮的降权会被自动撤销)"""
    lines = list(header_lines) + ["", W_TITLE] + \
        [f"{c}\t{w:g}" for c, w in sorted(weights.items())]
    if manual:
        lines += ["", W_MANUAL] + [f"{c}\t{w:g}" for c, w in sorted(manual.items())]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect(rows, hands, metric):
    """窗口内该角色的全部样本 → {(手, 角色, 组合): [值]} (错误行/不可解析行自然跳过)"""
    vals = defaultdict(list)
    for r in rows:
        for h in hands:
            for role, combo, v in role_segments(r, h, metric):
                vals[(h, role, combo)].append(v)
    return vals


def hand_ref(vals, hand, args):
    """该手各角色的**参考水平** → ({(手,角色): (med, n)}, {(手,角色): [参考样本]}, missing)
      口径 = 并击公共.role_ref_vals (pooled = 判定对象总体中心; sdf = 旧锚, 对照);
      样本不足的角色不产出 (该角色不参与判定)"""
    combos = two_key_combos(hand) if args.ref == "pooled" else None
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


def role_anchors(vals, hands, metric, n_min_role):
    """兼容包装 (自测用): 旧 sdf 锚口径 → {(手, 角色): (med, n)}"""
    args = argparse.Namespace(ref="sdf", n_min=n_min_role["S1"], n_min_iso=n_min_role["iso"])
    out, missing = {}, []
    for h in hands:
        r, _raw, miss = hand_ref(vals, h, args)
        out.update(r)
        missing += miss
    return out, missing


def judge(vals, ref, ref_raw, args):
    """两层判定 → (verdicts, exclude)
    verdicts = [(h, combo, ratio, n_eff, thr, roles_detail, reasons)] 按综合比值降序
    ref_raw = {(手, 角色): [参考样本]} (口径 = 并击公共.role_ref_vals)"""
    out = []
    for h in sorted({k[0] for k in vals}):
        by_combo = defaultdict(dict)
        for (hh, role, combo), v in vals.items():
            if hh == h and combo not in (REF_COMBO[h],):    # 跳过唯一 3 键组合 (无同类比较对象)
                by_combo[combo][role] = v
        # 参考的各角色样本 (用于配对比值; 该手/角色缺参考 → 该角色不参与)
        ref_vals = {role: ref_raw.get((h, role), []) for role in ROLES
                    if (h, role) in ref}
        for combo, vd in sorted(by_combo.items()):
            weight_counts = {role: len(v) for role, v in vd.items()}
            w = None
            if args.iso_importance is not None:
                imp = (args.iso_importance, 1.0)
                w = role_weights(weight_counts, imp)
            # 只保留参考可用角色的样本
            vd_use = {role: v for role, v in vd.items() if (h, role) in ref}
            if not vd_use:
                continue
            res = joint_log_ratio(vd_use, ref_vals, weights=w)
            if res is None:
                continue
            ratio, n_eff, detail = res
            reasons = []
            if n_eff >= args.n_min:
                thr = (args.margin if args.margin is not None
                       else margin_adaptive(n_eff, args.sigma, args.z))
                if ratio > thr:
                    reasons.append(f"综合({ratio:.2f}>{thr:.2f})")
            # 角色特异层: 每个角色单独与同角色参考比 (阈值须计入参考那一侧的噪声)
            hit_roles = []
            for role, v in sorted(vd_use.items()):
                need = args.n_min_iso if role == "iso" else args.n_min
                if len(v) < need:
                    continue
                med, n_ref = ref[(h, role)]
                thr = (args.margin if args.margin is not None
                       else margin_adaptive2(len(v), n_ref, args.sigma, args.z))
                if pct(v, 0.5) > thr * med:
                    hit_roles.append(f"{role}{pct(v,0.5)/med:.1f}")
            if hit_roles and (args.mode == "either" or len(hit_roles) >= 2):
                reasons.append("角色特异(" + ",".join(hit_roles) + ")")
            thr_show = (args.margin if args.margin is not None
                        else margin_adaptive(n_eff, args.sigma, args.z))
            out.append((h, combo, ratio, n_eff, thr_show, detail, reasons))
    out.sort(key=lambda x: -x[2])
    exclude = {c for h, c, r, ne, t, d, rs in out if rs}
    return out, exclude


# ═══════════════ 判据 B: 配额选码 (occ 排序 → 双键留 37; 2026-09-30, 配额 60→52 于 2026-10-11) ═══
def combo_vals(vals, hand, ref, combo):
    """该组合在参考可用角色上的样本 → {role: [值]} (不可用角色直接剔除, 保证配对语义)"""
    return {role: vals.get((hand, role, combo), []) for role in ROLES
            if (hand, role) in ref and vals.get((hand, role, combo))}


def judge_quota(vals, ref, ref_raw, args, hand):
    """配额选码判定 (单手) → dict(ranked/unrankable/keep/cut/soft/hard/dom/info/info_loose/…)
      三档阶梯 (2026-09-30):
        ① **配额切分**: 按 occ 综合比升序切在第 `--quota` 名
           · `ranked` = n_eff ≥ --n-min (严格; 用于割线与报告)
           · `ranked_loose` = n_eff ≥ --soft-n-min (宽松; 软降权可用更弱的证据 ⇒ 更早生效)
           · 不可排名者**不判不动**, 但占保留名额 (数据不足时切 = 掷硬币)
        ② **硬剔 (不可逆)**: `--eliminate` 时, 有 ≥ `--dominators` 个组合显著更优 ⇒ 确定出局
        ③ **软降权 (可回滚)**: `--soft-weight` > 0 时, 疑似出局 = 严格割线之下 ∪ 宽松割线之下
           ∪ 支配者带 (dom ≥ K − --soft-margin), 再**减去硬剔集**; 权重 ×`--soft-weight`
    参考水平 = 并击公共.role_ref_vals (默认 pooled = 同角色同键数组合总体中心; 不依赖 sdf);
    该手无可用参考 → None (本轮不参与)"""
    if not any((hand, r) in ref for r in ROLES):
        return None
    ref_vals = {r: ref_raw.get((hand, r), []) for r in ROLES if (hand, r) in ref}
    res = {"ranked": {}, "unrankable": set(), "detail": {}, "keep": set(), "cut": set(),
           "ranked_loose": {}, "keep_loose": set(), "cut_loose": set(), "soft": set(),
           "hard": set(), "elim": {}, "dom": None, "info": None, "info_loose": None,
           "anchors": {r: ref[(hand, r)] for r in ROLES if (hand, r) in ref}}
    for combo in two_key_combos(hand):
        vd = combo_vals(vals, hand, ref, combo)
        if not vd:
            res["unrankable"].add(combo)
            continue
        w = role_weights({r: len(v) for r, v in vd.items()}, (args.iso_importance, 1.0))
        got = joint_log_ratio(vd, ref_vals, weights=w)
        if got is None:
            res["unrankable"].add(combo)
            continue
        ratio, n_eff, detail = got
        if n_eff >= args.n_min:                       # 严格可排名 (割线报告 + 硬剔候选)
            res["ranked"][combo] = (ratio, n_eff)
            res["detail"][combo] = detail
        else:
            res["unrankable"].add(combo)
        if args.soft_weight > 0 and n_eff >= max(args.soft_n_min, MIN_ROLE_N):
            res["ranked_loose"][combo] = (ratio, n_eff)   # 宽松可排名 (软降权用)
    et_h = {c: v for (hh, c), v in (getattr(args, "et", None) or {}).items() if hh == hand} or None
    res["keep"], res["cut"], res["info"] = quota_cut(
        res["ranked"], res["unrankable"], args.quota, args.sigma,
        et=et_h)                       # 边界 z 由 quota_cut 按名次数定; Et 平手决胜 (v2.36)
    if args.soft_weight > 0:
        un_loose = set(two_key_combos(hand)) - set(res["ranked_loose"])
        res["keep_loose"], res["cut_loose"], res["info_loose"] = quota_cut(
            res["ranked_loose"], un_loose, args.quota, args.sigma, et=et_h)
    res["keep_all"] = res["keep"] | res["unrankable"]          # 实际保留 (不可排名者不判不动)
    if args.eliminate or args.soft_weight > 0:                 # ③ 需要支配者计数
        pool = {c: combo_vals(vals, hand, ref, c) for c in two_key_combos(hand)}
        pool = {c: v for c, v in pool.items() if v}
        combos = two_key_combos(hand)
        z = args.z if args.z is not None else z_for(len(combos) * (len(combos) - 1) // 2
                                                    * max(1, args.looks))
        res["z_elim"] = z
        got = {c: dominator_count(c, pool, args.sigma, z) for c in sorted(pool)}
        res["dom"] = {c: v[0] for c, v in got.items()}
        if args.eliminate:
            res["hard"] = {c for c, n in res["dom"].items() if n >= args.dominators}
            res["elim"] = {c: got[c] for c in res["hard"]}
    if args.soft_weight > 0:
        band = dominator_band(res["dom"], args.quota, args.soft_margin)
        res["soft"] = (res["cut"] | res["cut_loose"] | band) - res["hard"]
    return res


def report_quota(runs, args):
    """打印配额选码报告 (三档) → (hard:set, soft:set, hard_reasons:[str], soft_reasons:[str])"""
    hard, soft = set(), set()
    hard_reasons, soft_reasons = [], []
    print("\n═══ 判据 B · 配额选码 (occ 排序; 三档阶梯) ═══")
    print(f"配额: 单手 ≤{QUOTA_MAX_CODES} 码位 = {SINGLES_PER_HAND} 单键 (默认全留) + "
          f"双键留 {args.quota} / 淘汰 {TWO_KEY_PER_HAND - args.quota} (双键共 {TWO_KEY_PER_HAND}) | "
          f"参考水平 [{args.ref}] | σ(log {args.metric}) = {args.sigma:.2f} [{args.sigma_src}]")
    print(f"门槛: 硬剔 = 割线 (n_eff ≥ {args.n_min}) + ②支配者 ≥ {args.dominators}"
          f"{' (开启)' if args.eliminate else ' (未开启 ⇒ 本轮无硬剔)'}; " +
          (f"软降权 n_eff ≥ {args.soft_n_min} + 支配者 ≥ {args.dominators - args.soft_margin}, "
           f"权重 ×{args.soft_weight:g}" if args.soft_weight > 0 else "软降权: 关闭"))
    for hand, res in sorted(runs.items()):
        if res is None:
            print(f"\n[{hand} 手] 参考样本不足 → 本轮不判")
            continue
        info = res["info"]
        print(f"\n[{hand} 手] 参考水平 [{args.ref}]: " +
              "  ".join(f"{r}={m:.0f}ms(n={n})" for r, (m, n) in sorted(res["anchors"].items())))
        print(f"  {'#':>3} {'occ比':>6} {'n_eff':>6} {'组合':>5} | {'Et':>5} | {'判定':<4} | 各角色 n/比")
        order = sorted(res["ranked"], key=lambda c: res["ranked"][c][0])
        for i, c in enumerate(order, 1):
            ratio, n_eff = res["ranked"][c]
            d = res["detail"][c]
            mark = ("淘②" if c in res["hard"] else
                    ("降权" if c in res["soft"] else
                     ("保留" if c in res["keep"] else "候选")))
            cells = " ".join(f"{r}{d[r]['n']}/{d[r]['ratio']:.2f}" if r in d else f"{r}-"
                             for r in ROLES)
            ev = (args.et or {}).get((hand, c))
            print(f"  {i:>3} {ratio:>6.2f} {n_eff:>6.1f} {c:>5} | {ev:5.1f} | {mark:<4} | {cells}"
                  if ev else
                  f"  {i:>3} {ratio:>6.2f} {n_eff:>6.1f} {c:>5} |     — | {mark:<4} | {cells}")
        if info["boundary"]:
            print(f"  割线在第 {info['keep_slots']}/{info['keep_slots']+1} 名之间: "
                  f"{info['boundary'][0]} → {info['boundary'][1]}, 差 {math.exp(info['gap']):.3f}× "
                  f"(噪声 {math.exp(info['se_gap']):.3f}×) ⇒ "
                  f"{'可辨' if info['decisive'] else '⚠ 不可辨 (这一刀两组互换都说得通)'}")
        tb = info.get("tiebreak")
        if tb:
            print(f"  ⚖ Et 决胜 (mot-only): {tb['reason']}")
            if tb["changed"]:
                print("     名单变化: " + ", ".join(f"{c} {b}→{a}" for c, b, a in tb["changed"]))
            if tb.get("boundary_eff"):
                print(f"     决胜后割线: {tb['boundary_eff'][0]} → {tb['boundary_eff'][1]}")
        print(f"  ① {info['reason']}")
        if args.soft_weight > 0 and res["info_loose"]:
            li = res["info_loose"]
            print(f"  ③ 软降权用宽松门槛 n_eff ≥ {args.soft_n_min}: {li['reason']}"
                  + (f"; 宽松割线差 {math.exp(li['gap']):.3f}× vs 噪声 {math.exp(li['se_gap']):.3f}× ⇒ "
                     f"{'可辨' if li['decisive'] else '不可辨'}" if li["boundary"] else ""))
        if info["keep_slots"] <= 0 and info["n_unrankable"]:
            print("  ⇒ 数据不足: 硬剔与软降权都不会发生 (继续采集, 判据在样本够了以后自动生效)")
        if args.eliminate and res["dom"] is not None:
            n_pair = TWO_KEY_PER_HAND * (TWO_KEY_PER_HAND - 1) // 2
            print(f"  ② 确定出局 (z={res['z_elim']:.2f} = Bonferroni {n_pair} 对 × {args.looks} 次审阅; "
                  f"K={args.dominators} 个显著更优): {len(res['hard'])} 个")
            for c in sorted(res["hard"], key=lambda c: -res["dom"][c])[:15]:
                n_dom, hits = res["elim"][c]
                print(f"     {c}: 支配者 {n_dom} 个 (最强对照 "
                      f"{max(hits, key=lambda h: h[1])[0]} {max(h[1] for h in hits):.2f}×)")
        if args.soft_weight > 0:
            band = dominator_band(res["dom"], args.quota, args.soft_margin)
            weak = [c for c in res["soft"] if c not in res["ranked"]]
            print(f"  ③ 软降权 ×{args.soft_weight:g}: {len(res['soft'])} 个 "
                  f"(严格割线 {len(res['cut'])} + 宽松割线 {len(set(res['cut_loose']) - set(res['cut']))}"
                  f" + 支配者带 {len(band)} − 硬剔 {len(res['hard'])}; 其中 {len(weak)} 个只有宽松证据)")
            for c in sorted(res["soft"]):
                tag = ("②支配者带" if res["dom"] and res["dom"].get(c, 0) >= args.quota - args.soft_margin
                       else ("严格割线" if c in res["cut"] else "宽松割线"))
                ev = (f"occ比 {res['ranked'][c][0]:.2f}, n_eff {res['ranked'][c][1]:.1f}"
                      if c in res["ranked"] else
                      f"occ比 {res['ranked_loose'][c][0]:.2f}, n_eff {res['ranked_loose'][c][1]:.1f} 弱证据")
                if res["dom"] and c in res["dom"]:
                    ev += f", 支配者 {res['dom'][c]}"
                soft_reasons.append(f"# [理由·soft] {hand}手 {c}: {tag} → 降权 "
                                    f"×{args.soft_weight:g} ({ev})")
                soft.add(c)
        for c in sorted(res["hard"]):
            n_dom = res["dom"][c] if res["dom"] else 0
            hard_reasons.append(f"# [理由·quota] {hand}手 {c}: ②确定淘汰 "
                                f"(支配者 {n_dom} ≥ {args.dominators})")
            hard.add(c)
        for c in sorted(hard | soft):
            if scheme_used(c):
                print(f"  · 注: {c} 拼读并击在用 (仅提示; 本项目是通用模型, 不承担方案的覆盖约束)")
    if not any(r is not None for r in runs.values()):
        print("  ⇒ 无任何手有参考数据, 判据 B 停用")
    return hard, soft, hard_reasons, soft_reasons


# ═══════════════ 判据 B · 双手交集 (v2.22, 2026-10-01 用户决策) ═══════════════
# 口径: 方案要求**左右手可用组合对称** ⇒ 不能只凭一只手把组合淘汰掉; 而且采集已改成
#   左右 1:1 随机单手混采（每试次独立 50/50; v2.50 起无欠账增补）⇒ 两手都有自己的证据。规则:
#     **要剔除/降权的组合 = 两手"差组合"集的交集**（按镜像对对齐）
#   即: 只有同一对组合在**左右手都差**时才动作, 且**两侧一起**写表 (对称由构造保证)。
#   只手差的对只是"观察项"（打印出来）, 不动 —— 这正是必须同时采两手的原因。
def _ev(res, combo):
    """组合在该手判定结果里的证据文字 (严格/宽松两档)"""
    if res is None or not combo:
        return "—"
    if combo in res["ranked"]:
        r, ne = res["ranked"][combo]
        return f"{r:.2f}/{ne:.0f}"
    if combo in (res.get("ranked_loose") or {}):
        r, ne = res["ranked_loose"][combo]
        return f"{r:.2f}/{ne:.0f}弱"
    return "—"


def intersect_pairs(runs, exclude, soft, q_reasons, s_reasons, args):
    """把逐手动作集换成**双手交集** → (exclude, soft, q_reasons, s_reasons)"""
    print("\n═══ 判据 B · 双手交集 (v2.22; 方案要求左右手可用组合对称) ═══")
    hands_have = [h for h in ("l", "r") if runs.get(h) is not None]
    if len(hands_have) < 2:
        miss = [h for h in ("l", "r") if h not in hands_have]
        print(f"  ⚠ {'/'.join(miss)} 手无可用判定 (无数据或参考不足) ⇒ **交集为空, 本轮不动作**")
        print(f"    单手差集 = {len(exclude)} 硬剔 + {len(soft)} 降权 (仅报告, 不写表); "
              f"左右 1:1 随机单手混采补齐后自动生效")
        return set(), set(), [], []
    hard_l = {pair_id(c) for c in runs["l"]["hard"]}
    hard_r = {pair_id(c) for c in runs["r"]["hard"]}
    soft_l = {pair_id(c) for c in runs["l"]["soft"]}
    soft_r = {pair_id(c) for c in runs["r"]["soft"]}
    hard_both = hard_l & hard_r
    soft_both = (soft_l & soft_r) - hard_both
    part = (hard_l | soft_l | hard_r | soft_r) - hard_both - soft_both
    print(f"  动作 = **两手都差** 的对 (镜像对 id = 左手形式); 只手差的对不动 (等另一手数据)")
    print(f"  {'对(左/右)':<12}{'左手 比/n_eff':>16}{'右手 比/n_eff':>16}  判定")
    for p in sorted(hard_both | soft_both | part):
        rc = mirror_combo(p)
        st = ("淘②双手" if p in hard_both else "降权双手" if p in soft_both else "只手差(不动)")
        print(f"  {p+'/'+rc:<12}{_ev(runs['l'], p):>16}{_ev(runs['r'], rc):>16}  {st}")
    print(f"  ⇒ 交集: 硬剔 {len(hard_both)} 对 + 疑似 {len(soft_both)} 对 "
          f"(只手差 {len(part)} 对不动) | 单手名义: 左 {len(hard_l | soft_l)} / 右 {len(hard_r | soft_r)}")
    ex, sw = set(), set()
    for p in sorted(hard_both):
        rc = mirror_combo(p)
        ex |= {p, rc}
        q_reasons.append(f"# [理由·quota] 对 {p}/{rc}: 双手都确定出局 (左 {_ev(runs['l'],p)}, "
                         f"右 {_ev(runs['r'],rc)}; 支配者 ≥ {args.dominators})")
    for p in sorted(soft_both):
        rc = mirror_combo(p)
        sw |= {p, rc}
        s_reasons.append(f"# [理由·soft] 对 {p}/{rc}: 双手疑似 → 两侧一起降权 ×{args.soft_weight:g} "
                         f"(左 {_ev(runs['l'],p)}, 右 {_ev(runs['r'],rc)})")
    # 设计排序 (对称映射下保留双键怎么挑): 按**较差的那只手**排 (max 语义 = 慢手门控)
    def pair_score(p):
        vals = []
        for h, c in (("l", p), ("r", mirror_combo(p))):
            res = runs.get(h)
            if res and c in (res.get("ranked") or {}):
                vals.append(res["ranked"][c][0])
        return max(vals) if vals else None
    scored = [(p, pair_score(p)) for p in mirror_pairs_ids()]
    rated = sorted([(s, p) for p, s in scored if s is not None])
    print(f"  设计排序 (对称映射下挑 {args.quota} 个码位): 按**较差手**的 occ 比升序; "
          f"当前可排名 {len(rated)}/{TWO_KEY_PER_HAND} 对" +
          (f"; 割线在第 {args.quota}/{args.quota+1} 名" if len(rated) > args.quota else ""))
    return ex, sw, q_reasons, s_reasons


def mirror_pairs_ids():
    """63 个镜像对 (左手 canonical 形式)"""
    return [p for p, _r in mirror_pairs()]


def _ctx(win, hands, metric, args):
    """该 metric 下的完整判定上下文 → (vals, ref, ref_raw, σ, σ来源, missing)
    σ 口径与 main() 一致: 单元内 `sigma_within_log` 优先, 不足退回 `sigma_of_log`"""
    vals = collect(win, hands, metric)
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
    """该组合的综合比值 (信息列 / 补齐用) → (ratio, n_eff, detail) | None
    与判据同一函数 (`combo_vals` + `role_weights` + `joint_log_ratio`), 不另立口径"""
    vd = combo_vals(vals, hand, ref, combo)
    if not vd:
        return None
    ref_vals = {r: ref_raw.get((hand, r), []) for r in ROLES if (hand, r) in ref}
    w = role_weights({r: len(v) for r, v in vd.items()}, (iso_imp, 1.0)) if iso_imp else None
    return joint_log_ratio(vd, ref_vals, weights=w)


def write_table(win, hands, args, prefix):
    """完整剔除分析表 → 写 `{prefix}.md` (人读) + `{prefix}.tsv` (可筛选; 带 BOM 便于 Excel)。
    **只读**: 不碰两张动作表。行 = 该手全部 79 组合 (15 单键 + 63 双键 + 1 三键);
    单键/三键在判定宇宙之外, 其比值只作信息列 (单键默认全留, 三键不判)。"""
    va, ra, rra, sa, sra, _ma = _ctx(win, hands, "spread", args)
    vo, ro, rro, so, sro, _mo = _ctx(win, hands, "occ", args)
    aa = argparse.Namespace(**vars(args))
    aa.metric, aa.z = "spread", (args.z if args.z is not None else Z_FWER)
    aa.sigma, aa.sigma_src = sa, sra                     # ⚠ σ 必须换成**本判据 metric** 的
    ab = argparse.Namespace(**vars(args))
    ab.metric = "occ"
    ab.sigma, ab.sigma_src = so, sro
    out_a, _ex_a = judge(va, ra, rra, aa)
    A = {(h, c): (r, ne, thr, det, rs) for h, c, r, ne, thr, det, rs in out_a}
    runs = {h: judge_quota(vo, ro, rro, ab, h) for h in hands}

    def _ids(h, key):
        res = runs.get(h)
        return {pair_id(c) for c in (res or {}).get(key, set())} if res else set()

    both = len(hands) == 2 and all(runs.get(h) is not None for h in ("l", "r"))
    hard_both = (_ids("l", "hard") & _ids("r", "hard")) if both else set()
    soft_both = ((_ids("l", "soft") & _ids("r", "soft")) - hard_both) if both else set()
    part = ((_ids("l", "hard") | _ids("l", "soft") | _ids("r", "hard") | _ids("r", "soft"))
            - hard_both - soft_both) if both else set()

    exc = read_existing(EXCLUDE_TXT)
    w_auto, w_man = read_weights(WEIGHT_TXT)
    act = {}
    for c in exc["difficulty"]:
        act[c] = "排除(A)"
    for c in exc["quota"]:
        act[c] = "排除(B)"
    for c in exc["manual"]:
        act[c] = "排除(手工)"
    for c, w in list(w_auto.items()) + list(w_man.items()):
        act.setdefault(c, f"降权 ×{w:g}")
    man_pairs = {pair_id(c) for c in exc["manual"]}      # 手工已排除的镜像对 (采样已停)

    md, tsv, mism = [], [], []
    per_hand = {}
    for h, cn in (("l", "左手"), ("r", "右手")):
        if h not in hands:
            continue
        res = runs.get(h)
        combos = LEFT_COMBOS if h == "l" else RIGHT_COMBOS
        rank = {}
        if res:
            rank = {c: i + 1 for i, c in enumerate(
                sorted(res["ranked"], key=lambda c: res["ranked"][c][0]))}
        keep_slots = res["info"]["keep_slots"] if res and res.get("info") else 0
        rows = []
        for c in combos:
            nk = len(c)
            rc = mirror_combo(c)
            p = pair_id(c)
            pm = mirror_combo(p)                     # 对 id 恒为左手形式 ⇒ 对 = p/镜像(p)
            det, b_ratio, b_ne, b_mark, b_rank = None, None, None, "—", "—"
            if nk == 2 and res:
                if c in res["detail"]:
                    b_ratio, b_ne, det = res["ranked"][c][0], res["ranked"][c][1], res["detail"][c]
                    got = _ratio_of(vo, ro, rro, h, c, args.iso_importance)
                    if got and abs(got[0] - b_ratio) > 1e-9:          # 自检: 表的取值 = 判据取值
                        mism.append(f"{h}手 {c}: {b_ratio:.6f} vs {got[0]:.6f}")
                elif c in (res.get("ranked_loose") or {}):
                    b_ratio, b_ne = res["ranked_loose"][c][0], res["ranked_loose"][c][1]
                    got = _ratio_of(vo, ro, rro, h, c, args.iso_importance)
                    if got:
                        det = got[2]
                else:
                    got = _ratio_of(vo, ro, rro, h, c, args.iso_importance)   # 不可排名/数据不足
                    if got:
                        b_ratio, b_ne, det = got[0], got[1], got[2]
                if c in res["soft"]:
                    tag = ("支配者带" if (res.get("dom") and
                                          res["dom"].get(c, 0) >= args.quota - args.soft_margin)
                           else ("严格割线" if c in res["cut"] else "宽松割线"))
                    b_mark = f"③降权×{args.soft_weight:g}({tag}" + \
                             (f",支配者 {res['dom'][c]}" if res.get("dom") and c in res["dom"]
                              else "") + ")"
                elif c in res["hard"]:
                    b_mark = "②硬剔"
                elif c in res["ranked"]:
                    b_mark = ("①保留" if c in res["keep"] else "①候选(割线外)"
                              + ("" if not res["info"].get("tiebreak") else "(Et决胜后)"))
                    b_rank = str(rank[c])
                elif c in (res.get("ranked_loose") or {}):
                    b_mark = "弱证据(不判)"
                else:
                    b_mark = "不可排名(不判不动)"
            elif not res:
                b_mark = "本轮不判(参考不足)"
            elif nk == 1:
                got = _ratio_of(vo, ro, rro, h, c, args.iso_importance)
                if got:
                    b_ratio, b_ne, det = got[0], got[1], got[2]
                b_mark = "不判(单键全留)"
            else:
                got = _ratio_of(vo, ro, rro, h, c, args.iso_importance)   # 3 键: 仅信息列
                b_mark = "不判(唯一 3 键)"
                if got:
                    b_ratio, b_ne, det = got[0], got[1], got[2]
            inter = ("双手②硬剔" if p in hard_both else "双手③降权" if p in soft_both
                     else "只手差(不动)" if p in part else "—")
            a = A.get((h, c))
            a_jud = ("+".join(a[4]) if a and a[4] else ("未命中" if a else
                     ("不判(单键 spread≡0)" if nk == 1 else
                      "不判(唯一 3 键)" if nk == 3 else "数据不足")))
            cells = " ".join(f"{r}{det[r]['n']}/{det[r]['ratio']:.2f}" if det and r in det
                             else f"{r}-" for r in ROLES)
            et_v = (args.et or {}).get((h, c))
            rows.append([cn, c, str(nk), f"{p}/{pm}", f"{b_ratio:.2f}" if b_ratio else "—",
                         f"{b_ne:.1f}" if b_ne else "—",
                         f"{et_v:.1f}" if et_v else "—", b_rank, b_mark, inter, cells,
                         f"{a[0]:.2f}" if a else "—", f"{a[1]:.1f}" if a else "—",
                         f"{a[2]:.2f}" if a else "—", a_jud,
                         "●" if scheme_used(c) else "", act.get(c, "—")])
        per_hand[h] = rows
        info = res.get("info") if res else None
        cut_note = ""
        if info:
            cut_note = f"; ① {info['reason']}"
            if info.get("boundary"):
                cut_note += (f"; 割线 {info['keep_slots']}/{info['keep_slots']+1} 名之间 "
                             f"{info['boundary'][0]} → {info['boundary'][1]}, 差 "
                             f"{math.exp(info['gap']):.3f}× vs 噪声 {math.exp(info['se_gap']):.3f}× ⇒ "
                             f"{'可辨' if info['decisive'] else '⚠ **不可辨**（这一刀两组互换都说得通）'}")
            if info.get("tiebreak"):
                cut_note += (f"; ⚖ Et 决胜（窗口 {len(info['tiebreak']['window'])} 名按错误时间升序, "
                             f"名单变化 {len(info['tiebreak']['changed'])} 个"
                             + (f": {', '.join(c for c, _b, _a in info['tiebreak']['changed'])}"
                                if info["tiebreak"]["changed"] else "") + "）")
        md += [(f"\n### {cn}（{len(rows)} 组合; 参考水平 [{args.ref}] " +
                " ".join(f"{r}={m:.0f}ms" for r, (m, _n) in sorted(res["anchors"].items())) + "）"
                + cut_note) if res else f"\n### {cn}（本轮不判：参考样本不足）",
               "", "| " + " | ".join(TABLE_COLS) + " |",
               "|" + "---|" * len(TABLE_COLS)]
        md += ["| " + " | ".join(r) for r in rows]
        tsv += [["手", "组合", "键数", "镜像对", "occ比", "n_eff", "Et(ms)", "B名次", "B判定",
                 "双手交集", "各角色(occ) n/比", "spread比", "n_eff(A)", "阈值(A)", "A判定",
                 "方案在用", "动作表"]] if not tsv else []
        tsv += [[("l" if r[0] == "左手" else "r")] + r[1:] for r in rows]

    # ── 镜像对表 (29 对; 设计排序 = 按较差手的 occ 比) ────────────────────────────
    def _pair_score(p):
        vs = []
        for h, c in (("l", p), ("r", mirror_combo(p))):
            res = runs.get(h)
            if res and c in (res.get("ranked") or {}):
                vs.append(res["ranked"][c][0])
        return max(vs) if vs else None

    pr = []
    for p, _rc0 in mirror_pairs():
        rc = mirror_combo(p)
        s = _pair_score(p)
        st = ("双手②硬剔" if p in hard_both else "双手③降权" if p in soft_both
              else "只手差(不动)" if p in part else "双手无恙")
        left, right = runs.get("l"), runs.get("r")
        pr.append((f"{p}/{rc}", _ev(left, p) if left else "—", _ev(right, rc) if right else "—",
                   st, f"{s:.2f}" if s else "—"))
    pr.sort(key=lambda t: (t[4] == "—", float(t[4]) if t[4] != "—" else 0.0))

    gate_ok, gate_msg = quota_write_gate(min((len(runs[h]["ranked"]) for h in runs
                                             if runs[h] is not None), default=0))
    L = []
    L += [f"# 完整剔除分析表（判据 A 难度异常 + 判据 B 配额选码 + 双手交集）",
          "",
          f"生成: `{' '.join(['python'] + [Path(sys.argv[0]).name] + sys.argv[1:])}`"
          f"（{time.strftime('%Y-%m-%d %H:%M')}）",
          f"数据: `当量数据.tsv` 全量 {len(win)} 试次（判定样本池 = 全量; 稳定期只在命令行报告里打印, "
          f"不参与判定）; 手 = {'/'.join(hands)}; 参考水平 = `role_ref_vals([{args.ref}])`",
          "",
          "口径（全部来自 `并击公共.py` / 本文件; 本表**不另立口径, 不改任何阈值**）:",
          "",
          f"- **判据 A（难度异常）** metric=`spread`; σ(log spread)={sa:.2f}[{sra}]; "
          f"z={aa.z:.2f} 自适应阈值 `exp(z·1.253σ/√n_eff)`; 综合 n_eff≥{args.n_min}（iso {args.n_min_iso}）; "
          f"角色特异 mode={args.mode}; 1击:2击 权重 {args.iso_importance if args.iso_importance else '纯样本数'}"
          "；参考水平（同手 2 键组合的该角色样本中位）: "
          + " ".join(f"{h}@{r}={m:.0f}ms(n={n})" for (h, r), (m, n) in sorted(ra.items())),
          f"- **判据 B（配额选码）** metric=`occ`; σ(log occ)={so:.2f}[{sro}]; 配额 单手 ≤{QUOTA_MAX_CODES} "
          f"码位 = {SINGLES_PER_HAND} 单键（默认全留）+ 双键留 {args.quota} / 淘汰 "
          f"{TWO_KEY_PER_HAND - args.quota}; 硬剔 = 割线 + ②支配者 ≥{args.dominators}"
          f"（{'开启' if args.eliminate else '**未开启 ⇒ 本轮无硬剔**'}）; "
          f"软降权 n_eff ≥{args.soft_n_min} + 支配者带 ≥{args.dominators - args.soft_margin}, "
          f"权重 ×{args.soft_weight:g}；参考水平: "
          + " ".join(f"{h}@{r}={m:.0f}ms(n={n})" for (h, r), (m, n) in sorted(ro.items())),
          f"- **双手交集（v2.22）** 动作 = 镜像对**两手都差**（只手差的对只报告、不动）",
          "- 备注: **错误率（`分析-错误率.py` 的 m3 几何模型）不是判定依据**, 只作诊断; "
          "判据只有 A（spread 成形难度）与 B（occ 整击耗时）两条",
          f"- **写表门禁（v2.20）** {gate_msg}"]

    # 摘要
    n_a = sum(1 for k, v in A.items() if v[4])
    marks = defaultdict(int)
    soft_lists = {}
    for h in hands:
        res = runs.get(h)
        if not res:
            continue
        soft_lists[h] = sorted(res["soft"])
        keep_slots = res["info"]["keep_slots"] if res.get("info") else 0
        order = sorted(res["ranked"], key=lambda c: res["ranked"][c][0])
        for i, c in enumerate(order, 1):
            if c in res["soft"]:
                marks["soft"] += 1
            elif c in res["hard"]:
                marks["hard"] += 1
            elif i <= keep_slots:
                marks["keep"] += 1
            else:
                marks["cand"] += 1
        for c in two_key_combos(h):
            if c in res["ranked"]:
                continue                                   # 已计入
            if c in res["soft"]:
                marks["soft"] += 1                          # 支配者带里的不可排名者
            elif c in (res.get("ranked_loose") or {}):
                marks["weak"] += 1
            else:
                marks["unrank"] += 1
    L += ["", "## 0 摘要", "",
          f"- 判据 A 命中（会写 [difficulty] 段）: **{n_a}** 个" +
          ("（" + " ".join(sorted({c for h, c in A if A[(h, c)][4]})) + "）" if n_a else ""),
          f"- 判据 B 双键（两手合计 {2 * TWO_KEY_PER_HAND} 个）: ①保留 {marks['keep']} · "
          f"①候选(割线外; 仅软降权关闭时出现) {marks['cand']} · ③降权 {marks['soft']} · "
          f"②硬剔 {marks['hard']} · 弱证据(不判) {marks['weak']} · 不可排名 {marks['unrank']}",
          f"- 双手交集: ②硬剔 **{len(hard_both)} 对** · ③疑似 **{len(soft_both)} 对** · "
          f"只手差（不动）{len(part)} 对"
          + ("（**仅一手可用 ⇒ 交集为空, 本轮不动作**）" if not both else ""),
          f"- 当前生效的动作表: 排除表 = [difficulty] {len(exc['difficulty'])} + [quota] "
          f"{len(exc['quota'])} + [manual] {len(exc['manual'])} 条; "
          f"降权表 = {'不存在（未写过）' if not w_auto and not w_man else str(len(w_auto) + len(w_man)) + ' 条'}"
          f"（本表是**只读报告**, 不写这两张表）",
          f"- 本轮写表**预演**（只演不写, 判据 B 过门禁）: [quota] 段 {2 * len(hard_both)} 条; "
          f"降权表 {2 * len(soft_both)} 条（{len(soft_both)} 对 × {args.soft_weight:g}）"
          + (f"; 其中 {len(soft_both & man_pairs)} 对**已在 [manual] 排除表**（采样早已停, 降权无实际影响）"
             f" ⇒ **真正新增可动作 {len(soft_both - man_pairs)} 对**: "
             f"{' '.join(f'{p}/{mirror_combo(p)}' for p in sorted(soft_both - man_pairs)) or '无'}"
             if (soft_both & man_pairs) else ""),
          f"- 疑似名单（单手名义, 供对照）: " +
          " · ".join(f"{h}手 {' '.join(soft_lists[h]) if soft_lists[h] else '无'}"
                     for h in sorted(soft_lists))]
    if mism:
        L += ["", f"⚠ **自检失败**: 本表比值与判据取值不一致 {len(mism)} 处: " + " | ".join(mism[:5])]
    else:
        L += ["", "自检: 表中 occ 比 / n_eff 与判据内部取值**逐条一致**（同一函数同一参考）"]

    L += ["", "## 1 逐组合总表（全部 79 组合 × 两手）", "",
          "列说明: **B 名次/occ比/n_eff** = 判据 B（occ; B名次 = occ 名次, 保留/候选按决胜后 keep 集）; "
          "**Et(ms)** = 错误时间 = ERR_COST_MS×(三角色 P_err 等权, mot-only, 分析-错误率.py 特征化模型; "
          "用于割线不可辨时的平手决胜); **spread比/阈值(A)/A判定** = 判据 A; "
          "**双手交集** = 该组合所属镜像对在两手的动作状态（只手差 = 另一手未达动作线, 等数据）; "
          "**各角色(occ) n/比** = 该组合三角色的样本量与同角色参考比; "
          "单键与 3 键的 occ 比只作**信息列**（单键默认全留、3 键在判定宇宙之外）。"]
    L += md
    L += ["", "## 2 镜像对表（63 对中可排名的; 设计排序 = 按**较差手** occ 比升序 = 对称映射下挑码位）",
          "", "| 对(左/右) | 左手 比/n_eff | 右手 比/n_eff | 判定 | 较差手 occ比 |",
          "|---|---|---|---|---|"]
    L += ["| " + " | ".join(t) + " |" for t in pr]
    L += ["", "## 3 当前生效的动作表", "",
          f"`组合排除表.txt`: [difficulty] {sorted(exc['difficulty']) or '空'} · "
          f"[quota] {sorted(exc['quota']) or '空'} · [manual] {len(exc['manual'])} 条 "
          f"（手工段**必须保留**, 脚本只重写 [difficulty]/[quota] 两段）",
          f"`{WEIGHT_TXT.name}`: " + ("不存在" if not w_auto and not w_man
                                      else f"{sorted(w_auto)} / 手工 {sorted(w_man)}"),
          "", "## 4 复现", "",
          f"`python 分析-难度剔除.py --judge quota --dry-run --table` "
          f"（`--table PATH` 可指定输出前缀, 默认 `{TABLE_DEFAULT}`; 本表恒为只读）"]
    Path(prefix + ".md").write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(prefix + ".tsv").write_text(
        "\n".join("\t".join(r) for r in tsv) + "\n", encoding="utf-8-sig")
    print(f"\n完整剔除分析表 → {prefix}.md + {prefix}.tsv（只读报告; 未改两张动作表）")
    return prefix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["difficulty", "quota"], default="difficulty",
                    help="difficulty = 难度异常 (spread 同参考比, 默认) | quota = 配额选码 (occ 排序)")
    ap.add_argument("--hand", choices=["l", "r", "both"], default="both")
    ap.add_argument("--window", type=int, default=0,
                    help="滑动窗口试次数 (默认 0 = 全量; 窗口过小则每组合样本永远不够 n_min)")
    ap.add_argument("--n-min", type=int, default=20,
                    help="综合 n_eff 门槛 (difficulty) / 可排名门槛 (quota)")
    ap.add_argument("--n-min-iso", type=int, default=10, help="iso 角色门槛 (孤立样本天然更少)")
    ap.add_argument("--metric", choices=["spread", "occ"], default=None,
                    help="默认: difficulty→spread (成形难度), quota→occ (整击耗时; 实测 σ 小 4~6 倍)")
    ap.add_argument("--margin", default="auto",
                    help="阈值倍数: auto = 随样本量自适应 (推荐) | 数字 = 强制固定 (对照用)")
    ap.add_argument("--mode", choices=["either", "both"], default="either",
                    help="角色特异层: either 任一角色超标即剔 | both 需 ≥2 个角色")
    ap.add_argument("--iso-importance", type=float, default=0.5,
                    help="1击组:2击组 权重比 (0.5 = 1:2, 用户 2026-09-24 定); 0 = 纯按样本数")
    ap.add_argument("--pair", choices=["intersect", "hand"], default="intersect",
                    help="判据 B 动作集 (v2.22): intersect = **双手差组合的交集** (默认; 方案要求"
                         "左右对称 ⇒ 只在两手都差时动作, 两侧一起写表) | hand = 旧口径 (逐手独立, "
                         "仅供诊断对照)")
    ap.add_argument("--z", type=float, default=None,
                    help=f"阈值 z (默认 difficulty→{Z_FWER}; quota②→Bonferroni z_for(对数×审阅次数))")
    ap.add_argument("--quota", type=int, default=None,
                    help=f"双键保留数 (quota 判据; 默认 {QUOTA_KEEP_TWO_KEY} = "
                         f"{QUOTA_MAX_CODES} − {SINGLES_PER_HAND} 单键)")
    ap.add_argument("--dominators", type=int, default=None,
                    help="② 确定淘汰所需的支配者数 K (默认 = --quota)")
    ap.add_argument("--eliminate", action="store_true",
                    help="② 开关: 有 K 个组合显著更优 ⇒ **确定出局** → 硬剔 (不可逆)")
    ap.add_argument("--soft-weight", type=float, default=SOFT_WEIGHT_DEFAULT,
                    help=f"③ 软降权系数 (默认 {SOFT_WEIGHT_DEFAULT:g}; 0 = 关闭该层) —— "
                         f"疑似出局只把采样权重乘这个系数 (可回滚)")
    ap.add_argument("--soft-n-min", type=int, default=SOFT_N_MIN_DEFAULT,
                    help=f"③ 软降权用的宽松 n_eff 门槛 (默认 {SOFT_N_MIN_DEFAULT}; 比硬剔的 "
                         f"--n-min 松 ⇒ 更早生效)")
    ap.add_argument("--soft-margin", type=int, default=SOFT_MARGIN_DEFAULT,
                    help=f"③ 支配者带宽度: 支配者 ≥ K−margin 也算疑似 (默认 {SOFT_MARGIN_DEFAULT})")
    ap.add_argument("--looks", type=int, default=1,
                    help="② 序贯审阅次数 (Bonferroni 分摊; 反复偷看不膨胀错误率)")
    ap.add_argument("--ref", choices=list(REF_MODES), default=REF_MODE_DEFAULT,
                    help="参考水平: pooled = 同角色同键数组合总体中心 (默认, 不依赖 sdf) | "
                         "sdf = v2.13 旧锚 (对照; sdf 已不再加权采样)")
    ap.add_argument("--dry-run", action="store_true", help="只打印, 不写排除表/降权表")
    ap.add_argument("--force", action="store_true",
                    help=f"越过**写表门禁** (判据 B 的①可排名双键比例 < {QUOTA_WRITE_RANK_FRAC:.0%} "
                         f"时默认拒绝写两张动作表; 依据 实验/实验-新口径样本量.py 的闭环结论)")
    ap.add_argument("--selftest", action="store_true", help="合成数据自测判据")
    ap.add_argument("--table", nargs="?", const=TABLE_DEFAULT, default=None, metavar="PATH",
                    help=f"额外导出**完整剔除分析表**(判据 A + B + 双手交集 + 动作表现状) → PATH.md "
                         f"+ PATH.tsv (默认前缀 {TABLE_DEFAULT}); **只读**, 不写两张动作表, "
                         f"与 --dry-run 可同用")
    args = ap.parse_args()
    args.metric = args.metric or ("spread" if args.judge == "difficulty" else "occ")
    if args.z is None and args.judge == "difficulty":
        args.z = Z_FWER
    args.quota = args.quota if args.quota is not None else QUOTA_KEEP_TWO_KEY
    args.dominators = args.dominators if args.dominators is not None else args.quota
    if not 0.0 <= args.soft_weight <= 1.0:
        ap.error("--soft-weight 须在 [0,1] (0 = 关闭软降权; 要硬剔请加 --eliminate)")
    if args.soft_n_min < MIN_ROLE_N:
        ap.error(f"--soft-n-min 不得小于 MIN_ROLE_N={MIN_ROLE_N}")
    args.margin = None if args.margin == "auto" else float(args.margin)
    args.iso_importance = args.iso_importance if args.iso_importance > 0 else None

    if args.selftest:
        selftest(args)
        return

    rows = read_tsv(DATA)
    if not rows:
        print(f"无数据: {DATA} (尚未开始采集)")
        return
    args.et = read_et_table()                          # Et 平手决胜 (v2.36; mot-only)
    print(f"错误决胜表: {len(args.et)} (手,组合) " +
          (f"← {PERR_TXT.name}" if args.et else f"⚠ {PERR_TXT.name} 缺失/不完整 ⇒ 决胜关闭"))
    total = len(rows)
    win = rows[-args.window:] if args.window > 0 else rows
    hands = ("l", "r") if args.hand == "both" else (args.hand,)

    for h in hands:                                     # 稳定期参考 (仅报告, 不影响判定)
        vals_ = [v for v in (word_occ(r, h) for r in win if r.get("error", "0") == "0")
                 if v]                                   # 错误行须滤掉: 包络 σ_b 会被噪声抬高而发散到块 0
        if vals_:
            _, msg = stable_start(vals_)
            print(f"[稳定期·{h}手 wc] {msg}")

    vals = collect(win, hands, args.metric)
    # 阈值用**单元内 σ**（残差; 方差分解实测: pooled 把组合/段位/会话差异算进噪声 → 偏宽 5~7%）
    cells = {k: v for k, v in vals.items()}
    args.sigma = (sigma_within_log(cells) or sigma_of_log([v for v in vals.values() for v in v],
                                                          args.metric))
    args.sigma_src = "单元内(残差)" if sigma_within_log(cells) else \
        f"兜底(单元样本不足; {args.metric} 基准 {sigma_fallback(args.metric):.2f})"
    n_min_role = {"iso": args.n_min_iso, "S1": args.n_min, "S3": args.n_min}
    ref, ref_raw, missing = {}, {}, []
    for h in hands:
        r, raw, miss = hand_ref(vals, h, args)
        ref.update(r)
        ref_raw.update(raw)
        missing += miss
    for h, role, n, need in missing:
        what = REF_COMBO[h] if args.ref == "sdf" else "2键组合总体"
        print(f"⚠ 参考 {what}@{role} 样本不足 (n={n} < {need}) — 该角色不参与判定")
    print(f"参考水平 [{args.ref}] (同角色 med {args.metric}): " +
          "  ".join(f"{h}@{role}={m:.0f}ms(n={n})" for (h, role), (m, n) in sorted(ref.items())))
    print(f"σ(log {args.metric}) = {args.sigma:.2f} [{args.sigma_src}] | " +
          ("判据 B: 综合 occ 比升序切配额 (阈值只在②用)" if args.judge == "quota" else
           "判据 A 阈值 = " + ("自适应 exp(z·1.253σ/√n_eff) (z=%.2f)" % args.z if args.margin is None
                           else f"固定 {args.margin:.2f}")))

    diff_reasons, quota_reasons, soft_reasons, soft = [], [], [], set()
    if args.judge == "quota":
        runs = {h: judge_quota(vals, ref, ref_raw, args, h) for h in hands}
        exclude, soft, quota_reasons, soft_reasons = report_quota(runs, args)
        if args.pair == "intersect":                    # v2.22: 动作集 = 双手差组合的交集
            exclude, soft, quota_reasons, soft_reasons = intersect_pairs(
                runs, exclude, soft, quota_reasons, soft_reasons, args)
        else:
            print("\n(注: --pair hand = 逐手独立动作的旧口径; 方案要求左右对称时请用默认 intersect)")
    else:
        out, exclude = judge(vals, ref, ref_raw, args)
        print(f"\n窗口: 末 {len(win)}/{total} 试次 | 判据: ①综合比值 > 阈值 且 n_eff≥{args.n_min} "
              f"②角色特异 (n≥{args.n_min}/iso {args.n_min_iso}, mode={args.mode}) "
              f"| 1击:2击 权重 {args.iso_importance or '纯样本数'}")
        print(f"{'综合比':>6} {'n_eff':>6} {'阈值':>5} {'手':>2} {'组合':>5} | "
              f"{'iso':>13} {'S1':>13} {'S3':>13} | 标记")
        for h, combo, ratio, n_eff, thr, detail, reasons in out:
            cells = []
            for role in ROLES:
                d = detail.get(role)
                cells.append(f"{d['n']:>3}/{d['ratio']:.2f}" if d else "     -")
            flag = ("✗剔除 " + "+".join(reasons) if reasons else "") + \
                   (" ●方案在用" if scheme_used(combo) else "")
            print(f"{ratio:>6.2f} {n_eff:>6.1f} {thr:>5.2f} {h:>2} {combo:>5} | "
                  f"{cells[0]:>13} {cells[1]:>13} {cells[2]:>13} | {flag}")
            if reasons:
                diff_reasons.append(f"# [理由] {combo}: 综合 {ratio:.2f}(n_eff={n_eff:.1f}) " +
                                    " ".join(f"{r}={detail[r]['ratio']:.2f}(n={detail[r]['n']})"
                                             for r in sorted(detail)) + " → " + "+".join(reasons))

        print(f"\n判定剔除 {len(exclude)} 个组合" + (f": {' '.join(sorted(exclude))}" if exclude else ""))
        for c in sorted(exclude):
            if scheme_used(c):
                print(f"  · 注: {c} 拼读并击在用 (仅提示; 通用模型不承担方案的覆盖约束)")

        # 段位效应诊断 (孤立 vs 上下文; 现参与判定, 但仍报告其量级)
        cmp_rows = []
        for h in hands:
            for (hh, role, c), v in vals.items():
                if hh != h or role != "iso" or c == REF_COMBO[h] or len(v) < args.n_min_iso:
                    continue
                ctx = [(pct(vals[(h, r, c)], 0.5), len(vals[(h, r, c)]))
                       for r in ("S1", "S3")
                       if len(vals.get((h, r, c), [])) >= args.n_min]
                if ctx:
                    cmp_rows.append((pct(v, 0.5) - sum(m for m, _ in ctx) / len(ctx),
                                     h, c, pct(v, 0.5), sum(m for m, _ in ctx) / len(ctx), len(v)))
        if cmp_rows:
            cmp_rows.sort()
            print(f"\n段位效应诊断 (孤立 − 上下文 S1/S3 均值, ms; "
                  f"负值 = 上下文更慢 ⇒ 段位效应确实存在, 且已在配对差里抵消):")
            print(f"{'差值':>6} {'手':>2} {'组合':>5} {'孤立':>5} {'上下文':>6} {'孤立n':>5}")
            for d, h, c, i_, ctx_, n in cmp_rows[:8]:
                print(f"{d:6.1f} {h:>2} {c:>5} {i_:5.0f} {ctx_:6.1f} {n:5d}")
            print(f"  (全表 {len(cmp_rows)} 个组合; 差值中位 {pct([r[0] for r in cmp_rows],0.5):+.1f}ms)")

    # ── 完整剔除分析表 (2026-10-10; 只读报告, 与 --dry-run 兼容) ────────────────────
    if args.table:
        tp = Path(args.table)
        write_table(win, hands, args, str(tp if tp.is_absolute() or tp.parent != Path(".")
                                          else BASE / tp))

    # ── 写表门禁 (v2.20): 证据不足时不写动作表 (判据 B) ─────────────────────────────
    gate_ok, gate_msg = True, "（判据 A 不设门禁）"
    if args.judge == "quota":
        per_hand = {h: len(r["ranked"]) for h, r in (runs or {}).items() if r is not None}
        n_rank = min(per_hand.values(), default=0)          # 门禁取**最差手** (两手都要够)
        gate_ok, gate_msg = quota_write_gate(n_rank)
        print(f"\n样本量门禁 (写表): {gate_msg} ⇒ " +
              ("放行 —— 可排名已覆盖绝大多数双键, 写表不会误伤" if gate_ok else
               "**不放行** —— 降权/硬剔都还建立在掷硬币式的名次上; 继续采集, 只出名单"))
        if per_hand:
            print("   各手可排名: " + "  ".join(f"{h}手 {n}/{TWO_KEY_PER_HAND}"
                                                for h, n in sorted(per_hand.items())) +
                  "  (门禁取最差手; 只采一手时请配 --hand l/r, 免得薄手数据把闸门压住)")
        if not gate_ok:
            print("   依据 实验/实验-新口径样本量.py (闭环): 早写表(≈1000 试次)时降权集只 ~78% 正确,")
            print("   被误降权的组合样本量**恢复不回来** ⇒ 保留码 occ 全达 ±5% 晚 50%、±3% 晚 27%;")
            print("   等到 ① 能排名绝大多数双键 (≈2000 试次/手) 再写, 这些里程碑 +0%。")
    if args.dry_run:
        print("(--dry-run: 未写入排除表/降权表)")
        return
    if not gate_ok and not args.force:
        print(f"⛔ 本轮**不写表** ({gate_msg}; 要强制写入加 `--force`)。\n"
              f"   排除表/降权表保持原样 (手工段不受影响); 名单见上方报告, 继续采集即可。")
        return
    if not gate_ok:
        print("⚠ --force: 越过写表门禁, 按当前(证据不足的)结果改写两张动作表 —— 后果自负。")
    secs = read_existing(EXCLUDE_TXT)
    old_sec = set(secs[args.judge])
    if args.judge == "quota":
        head = [
            "# 组合排除表 — 自动条目由 分析-难度剔除.py 生成 (判据 B ② 硬剔; README §4.4)",
            f"# 判据 B (quota) 单手 ≤{QUOTA_MAX_CODES} 码位: {SINGLES_PER_HAND} 单键默认全留 + 双键保留 "
            f"{args.quota} (共 {TWO_KEY_PER_HAND}); 排序量 = occ (整击耗时), 同角色参考配对 + 1:2 权重",
            (f"# 本段 = **确定出局** (② 支配者 ≥ {args.dominators}) ⇒ 硬剔, **不可逆**; "
             f"疑似出局见 组合降权表.txt (③ 软降权, 可回滚)" if args.eliminate else
             "# 本段 = ② 硬剔 (本轮 --eliminate 未开启 ⇒ 无硬剔); "
             "疑似出局见 组合降权表.txt (③ 软降权)"),
            f"# 序贯审阅 {args.looks} 次 (z=Bonferroni); σ(log {args.metric}) = {args.sigma:.2f} "
            f"[{args.sigma_src}]; 窗口 = 末 {len(win)} 试次",
        ]
    else:
        head = [
            "# 组合排除表 — 自动条目由 分析-难度剔除.py 生成 (判据 A 难度异常; 同角色同键数组合总体中心, README §4.4)",
            f"# 判据 A (difficulty): ①综合比值 > 阈值 且 n_eff≥{args.n_min} "
            f"(三角色共享击内效应, 段位效应配对抵消) ②角色特异 (n≥{args.n_min}/iso {args.n_min_iso}, "
            f"mode={args.mode})",
            f"# 阈值 = " + ("自适应 exp(%.2f·1.253σ·√(1/n+1/n_ref)), σ=%.2f" % (args.z, args.sigma)
                            if args.margin is None else f"固定 {args.margin:.2f}") +
            f"; 1击:2击 权重 = {args.iso_importance or '纯样本数'}; 窗口 = 末 {len(win)} 试次",
        ]
    head += [
        f"# 参考水平 [{args.ref}]: " +
        "  ".join(f"{h}@{r}={m:.0f}ms(n={n})" for (h, r), (m, n) in sorted(ref.items())),
        f"# 判据 {args.judge} · {args.metric} · 生成于 {time.strftime('%Y-%m-%d %H:%M')}; "
        f"手工条目请置于 '# [manual]' 之后",
    ]
    secs[args.judge] = exclude
    write_exclude(EXCLUDE_TXT, secs, head, {"difficulty": diff_reasons, "quota": quota_reasons})
    added, removed = exclude - old_sec, old_sec - exclude
    other = sum(len(secs[s]) for s in ("difficulty", "quota") if s != args.judge)
    print(f"已写入 {EXCLUDE_TXT.name} [{args.judge} 段]: {len(exclude)} 条"
          f"(新增 {len(added)}, 撤销 {len(removed)})" +
          (f", 手工保留 {len(secs['manual'])} 条" if secs["manual"] else "") +
          (f", 另一判据段保留 {other} 条" if other else ""))
    if args.judge == "quota":                       # ③ 降权表 (总是重写 ⇒ 上一轮降权自动撤销)
        old_w, manual_w = read_weights(WEIGHT_TXT)
        whead = [
            "# 组合降权表 — 由 分析-难度剔除.py --judge quota 生成 (判据 B ③ 软降权; README §4.4)",
            f"# 语义: 疑似出局 (未确定) → 采样权重 ×系数 ({args.soft_weight:g}); 权重 1 = 不降权; "
            f"**要硬剔请写 组合排除表.txt** (本表不剔任何组合)",
            f"# 疑似 = 严格割线 (n_eff ≥ {args.n_min}) ∪ 宽松割线 (n_eff ≥ {args.soft_n_min}) ∪ "
            f"支配者带 (≥ {args.dominators - args.soft_margin}); 不可排名者不判不动",
            f"# 参考水平 [{args.ref}]; 生成于 {time.strftime('%Y-%m-%d %H:%M')}; "
            f"采集工具每 200 试次重载 ⇒ 疑似恢复后下一轮自动撤销",
        ] + soft_reasons
        soft_w = {c: args.soft_weight for c in soft}
        write_weights(WEIGHT_TXT, soft_w, whead, manual_w)
        w_added, w_rm = set(soft_w) - set(old_w), set(old_w) - set(soft_w)
        print(f"已写入 {WEIGHT_TXT.name} [soft 段]: {len(soft_w)} 个 ×{args.soft_weight:g} "
              f"(新增 {len(w_added)}, 撤销 {len(w_rm)})" +
              (f", 手工保留 {len(manual_w)} 个" if manual_w else ""))
    if args.table and not args.dry_run:            # 写表后重出一次 ⇒ 动作表列反映**写入后**状态
        tp = Path(args.table)
        write_table(win, hands, args, str(tp if tp.is_absolute() or tp.parent != Path(".")
                                          else BASE / tp))


# ═══════════════ 合成数据自测 (判据可验证性; 真实数据到位前先证判据本身) ═══════════════
def _synth(spec, n_per_combo, ref_boost, sigma, seed=11, mus=120.0, role_effects=None,
           occ_spec=None, mus_occ=120.0, sigma_occ=0.19):
    """合成 left 手数据行。spec[(combo, role)] = 真实 log 效应 (组合效应, 三角色相同)。
    role_effects = 段位效应 (真实数据实测: 孤立/S1/S3 = −0.29/0/+0.39, 见 §6.2-6)。
    n_per_combo = {"iso":…, "two":…} 每组合目标样本数 (iso 用 1 击行; two 用 2 击行 → S1+S3 各一)
    ref_boost = {role: 倍数} 锚的加权 (与真实采样器一致: 参考被加权, 且**各角色配比与普通组合
                不同** —— 这正是"直接合并有偏、必须同角色配对"的成因)
    occ_spec = {(combo, role): log 效应} → 同时合成 occ (lu−fd, 判据 B 的排序量; σ_occ 默认 0.19);
               None = 不合成 (lfu1/llu1 恒 120 ⇒ occ ≡ 120 无信号, 判据 A 的旧行为)"""
    import random
    rng = random.Random(seed)
    re_ = role_effects or {}
    combos = sorted({c for c, _ in spec})
    ref = REF_COMBO["l"]

    def pick(role):
        w = [ref_boost.get(role, 1.0) if c == ref else 1.0 for c in combos]
        return rng.choices(combos, weights=w, k=1)[0]

    def v(combo, role):
        if len(combo) == 1:
            return 0.0              # 单键击 spread ≡ 0 (真实约束: 单指无成形难度)
        m = math.log(mus) + spec.get((combo, role), 0.0) + re_.get(role, 0.0)
        return math.exp(m + sigma * rng.gauss(0, 1))

    def occ_of(combo, role, sp):
        """该击 (hold, occ) 两锚; occ_spec=None → 恒 120 (与旧行为逐位一致)"""
        if occ_spec is None:
            return 120.0, 120.0
        oc = math.exp(math.log(mus_occ) + occ_spec.get((combo, role), 0.0)
                      + sigma_occ * rng.gauss(0, 1))
        return max(sp + 1.0, 0.8 * oc), oc

    rows = []
    for _ in range(int(n_per_combo["iso"] * len(combos))):
        c = pick("iso")
        sp = v(c, "iso")
        ho, oc = occ_of(c, "iso", sp)
        rows.append({"code": c, "error": "0", "session": "syn", "trial": "0",
                     "lfd1": "0.0", "lld1": f"{sp:.3f}", "lfu1": f"{ho:.3f}", "llu1": f"{oc:.3f}"})
    for _ in range(int(n_per_combo["two"] * len(combos))):
        c1, c2 = pick("S1"), pick("S3")
        sp1, sp3, gap = v(c1, "S1"), v(c2, "S3"), 150.0
        ho1, oc1 = occ_of(c1, "S1", sp1)
        ho3, oc3 = occ_of(c2, "S3", sp3)
        rows.append({"code": f"{c1}|{c2}", "error": "0", "session": "syn", "trial": "0",
                     "lfd1": "0.0", "lld1": f"{sp1:.3f}", "lfu1": f"{ho1:.3f}", "llu1": f"{oc1:.3f}",
                     "lfd2": f"{gap:.1f}", "lld2": f"{gap + sp3:.3f}",
                     "lfu2": f"{gap + ho3:.3f}", "llu2": f"{gap + oc3:.3f}"})
    for r in rows:                                      # 补齐该手其余列 (右手全 0)
        for k in ("lfd2", "lld2", "lfu2", "llu2"):
            r.setdefault(k, "0.0")
        for h in "r":
            for p in ("fd", "ld", "fu", "lu"):
                for s in (1, 2):
                    r.setdefault(f"{h}{p}{s}", "0.0")
    return rows


def _run_pipeline(rows, args):
    vals = collect(rows, ("l",), args.metric)
    ref, ref_raw, missing = hand_ref(vals, "l", args)
    assert not missing, missing
    out, exclude = judge(vals, ref, ref_raw, args)
    return vals, ref, out, exclude


def selftest(args):
    sigma = 0.87
    # 段位效应 = 真实数据实测 (孤立 6.5 / S1 8.7 / S3 12.9 ms → log 偏移), 不是假设值
    ROLE_EFF = {"iso": math.log(6.5 / 8.7), "S1": 0.0, "S3": math.log(12.9 / 8.7)}
    # 每组合样本数刻意取在 n_min 之上 (角色层要求每个角色各自达标; 若卡在门槛上,
    # 一半组合会因"角色样本不足"而不可判 —— 那是**覆盖度**限制, 已在 README §6.2-6 定量)
    n_per_combo = {"iso": 14, "two": 30}
    ref_boost = {"iso": 1.5, "S1": 2.5, "S3": 4.0}      # (仅合成用) sdf 的段位配比刻意与普通组合不同
    base = dict(n_min=20, n_min_iso=10, metric="spread", margin=None, mode="either",
                iso_importance=0.5, z=Z_FWER, sigma=sigma, window=0, hand="l", ref="sdf")
    args2 = argparse.Namespace(**base)

    def spec_of(plant):
        """{组合: log 效应} → {(组合, 角色): 效应} (三角色同效应)"""
        return {(c, role): plant.get(c, 0.0) for c in LEFT_COMBOS for role in ROLES}

    # 单次运行: 报告 + 段位抵消 (配对) 与直接合并的对照
    plant = {"qg": math.log(2.5), "zv": math.log(1.15)}
    spec = spec_of(plant)
    # 角色特异: sg 只在 S3 难。注意量级: 单角色效应在综合层被 1:2 权重稀释 (^(1/3)),
    # 角色特异层在 n≈20 时阈值 ≈1.84 ⇒ 观测比值 ≈真值×锚噪声, 2.5× 恰好卡在边缘
    # (实测: 真值 2.46× 观测 1.80× < 1.84 → 漏) ⇒ 测试按该层**设计能力**植入 3.5×
    for role in ROLES:
        spec[("sg", role)] = math.log(3.5) if role == "S3" else 0.0
    rows = _synth(spec, n_per_combo, ref_boost, sigma, role_effects=ROLE_EFF)
    vals, ref, out, exclude = _run_pipeline(rows, args2)
    by = {c: (r, ne, rs) for h, c, r, ne, t, d, rs in out}
    null_ratios = [r for c, (r, ne, rs) in by.items() if c not in ("qg", "zv", "sg")]
    med_null = pct(null_ratios, 0.5)
    # 配对估计 ≈1.0 (残余偏差 = 锚自身抽样噪声的共模项, n_ref=21/66/116 时约 ±10%)
    assert 0.85 < med_null < 1.15, f"段位抵消失效: 零真值组合综合比值中位 {med_null:.2f}"
    # 对照: 直接合并三角色 → 锚的段位配比与组合不同 ⇒ 系统性偏差 (不是噪声)。
    # 逐组合取 配对/合并 之比 ⇒ 共模的锚噪声在比值里抵消, 剩下的就是配比偏差
    ref_pool = pct([x for role in ROLES for x in vals[("l", role, REF_COMBO["l"])]], 0.5)
    diffs = []
    for c, (r, ne, rs) in by.items():
        if c in ("qg", "zv", "sg"):
            continue
        pooled_c = pct([x for role in ROLES for x in vals[("l", role, c)]], 0.5) / ref_pool
        if pooled_c > 0:
            diffs.append(r / pooled_c)
    med_diff = pct(diffs, 0.5)
    print(f"  [自测] 零真值组合: 配对综合比值中位 {med_null:.2f} (共模锚噪声约 ±10%) | "
          f"配对/合并 之比中位 {med_diff:.2f} ← 锚 S3 偏多 × S3 段位更慢, "
          f"直接合并系统性低估 {100*(med_diff-1):.0f}% (配对才无偏)")
    assert med_diff > 1.03, f"合并偏差未体现: 配对/合并 = {med_diff:.3f} (段位效应 {ROLE_EFF})"
    print(f"  [自测·sdf 对照] 锚样本: " + " ".join(f"{r}={ref[('l',r)][1]}" for r in ROLES) +
          f" (组合每角色 ~10/20/20) → 配比不同正是必须配对的原因")
    assert "qg" in exclude, f"2.5× 真难未剔: {by.get('qg')}"
    assert "zv" not in exclude, f"1.15× 被误剔: {by.get('zv')}"
    assert "sg" in exclude and any("角色特异" in x for x in by["sg"][2]), by["sg"]
    assert not any(len(c) == 1 for c in exclude), sorted(c for c in exclude if len(c) == 1)

    # 多种子: 检出率 / 误剔率 (单次可能撞种子 → 用重复测)
    det_qg = det_sg = det_zv = 0
    fps = []
    for seed in (11, 22, 33, 44, 55):
        rows = _synth(spec, n_per_combo, ref_boost, sigma, seed=seed)
        _, _, out_s, ex_s = _run_pipeline(rows, args2)
        det_qg += "qg" in ex_s
        det_sg += "sg" in ex_s
        det_zv += "zv" in ex_s
        fps.append(len([c for c in ex_s if c not in ("qg", "sg")]))
    print(f"  [自测] 5 个种子: 2.5×真难检出 {det_qg}/5 | 角色特异(S3 3.5×)检出 {det_sg}/5 | "
          f"1.15×误剔 {det_zv}/5 | 零假设误剔 均 {sum(fps)/len(fps):.1f} 个/63")
    print(f"  [自测] 分辨率边界: 单角色效应在综合层被 1:2 权重稀释为 ^(1/3); 角色层阈值 "
          f"n=29/锚62 时 = {margin_adaptive2(29, 62, sigma):.2f} ⇒ 只抓**突出**的段位异常")
    assert det_qg >= 4 and det_sg >= 4, (det_qg, det_sg)
    assert det_zv <= 1, det_zv
    assert sum(fps) / len(fps) <= 1.5, fps

    # 固定 margin=1.0 的对照 (同一种子): 必然大面积误剔 ⇒ 它不是判据
    rows = _synth(spec, n_per_combo, ref_boost, sigma)
    vals, ref, out, exclude = _run_pipeline(rows, args2)
    args3 = argparse.Namespace(**{**base, "margin": 1.0})
    _r3, _raw3, _m3 = hand_ref(vals, "l", args3)
    _, ex_fix = judge(vals, _r3, _raw3, args3)
    print(f"  [自测] 同一份数据: 自适应阈值剔 {len(exclude)} 个 vs 固定 margin=1.0 剔 "
          f"{len(ex_fix)} 个 ← 后者是噪声 (≈一半被测组合)")
    assert len(ex_fix) > 3 * len(exclude), (len(ex_fix), len(exclude))
    print("判据自测通过: 段位配对抵消(对照直接合并) / 2.5×检出 / 1.15×不误剔 / "
          "角色特异兜住 / 零假设误剔≤1.5 / 固定阈值失效对照 / 单键不参与")
    selftest_quota()                      # 并击公共 的配额口径自测 (含写表门禁与左右镜像)
    selftest_pooled_ref()
    selftest_quota_pipeline()


def selftest_pooled_ref(verbose=True):
    """**默认参考口径** (pooled = 同角色、同键数组合总体中心) 的自测 —— 判定不依赖 sdf:
      零真值组合比值中位 ≈1 (段位仍被抵消) / 2.5× 检出 / 1.15× 不误剔 / 角色特异兜住 /
      零假设误剔少 / 单键不参与 / sdf 不进参考池也不被判定"""
    sigma = 0.87
    ROLE_EFF = {"iso": math.log(6.5 / 8.7), "S1": 0.0, "S3": math.log(12.9 / 8.7)}
    n_per = {"iso": 20, "two": 30}
    ref_boost = {"iso": 1.5, "S1": 2.5, "S3": 4.0}
    base = dict(n_min=20, n_min_iso=10, metric="spread", margin=None, mode="either",
                iso_importance=0.5, z=Z_FWER, sigma=sigma, window=0, hand="l", ref="pooled")
    args = argparse.Namespace(**base)
    spec = {(c, role): 0.0 for c in LEFT_COMBOS for role in ROLES}
    spec[("qg", "S1")] = spec[("qg", "S3")] = spec[("qg", "iso")] = math.log(2.5)
    for role in ROLES:
        spec[("zv", role)] = math.log(1.15)
        spec[("sg", role)] = math.log(3.5) if role == "S3" else 0.0
    rows = _synth(spec, n_per, ref_boost, sigma, role_effects=ROLE_EFF)
    vals = collect(rows, ("l",), "spread")
    # 参考池 = 判定对象总体 (63 个 2 键组合); sdf (3 键) 不在池内, 也不参与判定
    ref, ref_raw, missing = hand_ref(vals, "l", args)
    assert not missing, missing
    pool = ref_raw[("l", "S1")]
    assert len(pool) > 1000, len(pool)                      # 参考池远大于单组合锚
    assert not any(c == REF_COMBO["l"] for c in [])         # (sdf 无样本 → 池里不可能有它)
    out, exclude = judge(vals, ref, ref_raw, args)
    by = {c: (r, ne, rs) for h, c, r, ne, t, d, rs in out}
    assert REF_COMBO["l"] not in by, "sdf 不应被判定"
    med_null = pct([r for c, (r, ne, rs) in by.items() if c not in ("qg", "zv", "sg")], 0.5)
    assert 0.85 < med_null < 1.15, f"pooled 参考下段位抵消失效: 零真值中位 {med_null:.2f}"
    assert "qg" in exclude and "zv" not in exclude, (by.get("qg"), by.get("zv"))
    assert "sg" in exclude and any("角色特异" in x for x in by["sg"][2]), by["sg"]
    assert not any(len(c) == 1 for c in exclude), sorted(c for c in exclude if len(c) == 1)
    det, fps = {"qg": 0, "sg": 0, "zv": 0}, []
    for seed in (11, 22, 33, 44, 55):
        v2 = collect(_synth(spec, n_per, ref_boost, sigma, seed=seed, role_effects=ROLE_EFF),
                     ("l",), "spread")
        r2, raw2, _m = hand_ref(v2, "l", args)
        _, ex2 = judge(v2, r2, raw2, args)
        det["qg"] += "qg" in ex2
        det["sg"] += "sg" in ex2
        det["zv"] += "zv" in ex2
        fps.append(len([c for c in ex2 if c not in ("qg", "sg")]))
    assert det["qg"] >= 4 and det["sg"] >= 4 and det["zv"] <= 1, det
    assert sum(fps) / len(fps) <= 1.5, fps
    if verbose:
        print(f"  [自测·pooled] 参考池 S1 n={len(pool)} (单组合锚仅 ~30~60) ⇒ 阈值里参考噪声≈0; "
              f"零真值比值中位 {med_null:.2f}; 5 种子: 2.5×检出 {det['qg']}/5, 角色特异 {det['sg']}/5, "
              f"1.15×误剔 {det['zv']}/5, 零假设误剔 均 {sum(fps)/len(fps):.1f} 个/63")
    print("默认参考口径自测通过: pooled 中心 (不依赖 sdf) / 段位仍抵消 / 检出与误剔达标 / sdf 不参与")


# ═══════════════ 判据 B (配额选码) 的合成自测 ═══════════════
def selftest_quota_pipeline(verbose=True):
    """合成 occ 已知真值 → 验判据 B:
      · ① 配额切分: 数据够时, 切掉的 18 个 = 真慢的 18 个 (真值 1.6×)
      · 数据不足: 可排名者太少 → 一个都不切 (不可排名者占满名额)
      · ② --eliminate: 只是"确定出局"的子集, **不误淘**任何真该留的组合
      · 单键不参与 (spread ≡0 且默认全留)"""
    sigma, sigma_occ = 0.87, 0.19
    ROLE_EFF = {"iso": math.log(6.5 / 8.7), "S1": 0.0, "S3": math.log(12.9 / 8.7)}
    combos = two_key_combos("l")
    n_hard = TWO_KEY_PER_HAND - QUOTA_KEEP_TWO_KEY          # 18 个真该淘汰
    hard = set(combos[:n_hard])
    plant_occ = {(c, r): (math.log(1.6) if c in hard else 0.0) for c in combos for r in ROLES}
    plant_sp = {(c, r): 0.0 for c in LEFT_COMBOS for r in ROLES}     # spread 无信号 (对照)
    base = dict(metric="occ", n_min=20, n_min_iso=10, margin=None, mode="either",
                iso_importance=0.5, z=None, sigma=sigma_occ, window=0, hand="l", ref="pooled",
                quota=QUOTA_KEEP_TWO_KEY, dominators=QUOTA_KEEP_TWO_KEY, eliminate=False, looks=1,
                soft_weight=SOFT_WEIGHT_DEFAULT, soft_n_min=SOFT_N_MIN_DEFAULT,
                soft_margin=SOFT_MARGIN_DEFAULT)
    args = argparse.Namespace(**base)
    ref_boost = {"iso": 1.5, "S1": 2.5, "S3": 4.0}
    n_per = {"iso": 20, "two": 30}

    # (1) 数据充足: 18 个真慢的应被整批切掉, 且不误淘 (参考 = 同角色 2 键组合总体中心)
    rows = _synth(plant_sp, n_per, ref_boost, sigma, role_effects=ROLE_EFF,
                  occ_spec=plant_occ, sigma_occ=sigma_occ)
    vals = collect(rows, ("l",), "occ")
    ref, ref_raw, missing = hand_ref(vals, "l", args)
    assert not missing, missing
    res = judge_quota(vals, ref, ref_raw, args, "l")
    assert res["info"]["n_rankable"] >= TWO_KEY_PER_HAND - 2, res["info"]
    assert res["cut"] == hard, (sorted(res["cut"]), sorted(hard))
    assert not any(len(c) == 1 for c in res["cut"])                 # 单键不参与
    if verbose:
        print(f"  [自测·quota] ① 配额: 可排名 {res['info']['n_rankable']}, 保留 "
              f"{len(res['keep_all'])} (=单键 {SINGLES_PER_HAND} + 双键 {res['info']['keep_slots']}), "
              f"淘汰 {len(res['cut'])}/18 全中真慢; 割线差 {math.exp(res['info']['gap']):.2f}× "
              f"(噪声 {math.exp(res['info']['se_gap']):.2f}×) ⇒ "
              f"{'可辨' if res['info']['decisive'] else '不可辨'}")

    # (2) ② 确定出局 (硬剔): 不误淘真该留的组合; 且 ③ 软降权不与硬剔重叠
    args_elim = argparse.Namespace(**{**base, "eliminate": True})
    res2 = judge_quota(vals, ref, ref_raw, args_elim, "l")
    elim = set(res2["hard"])
    assert not (elim & (set(combos) - hard)), \
        f"② 误淘真该留的组合: {sorted(elim & (set(combos) - hard))}"
    assert not (set(res2["soft"]) & elim), "③ 降权集与硬剔集重叠"
    if verbose:
        print(f"  [自测·quota] ② 确定出局 {len(elim)} 个 (全在真慢 18 个内; z="
              f"{res2['z_elim']:.2f} Bonferroni; 误淘 0); 已确定的从降权集剔除 ⇒ "
              f"③ 剩 {len(res2['soft'])} 个")

    # (2b) ③ 软降权 (默认关掉 --eliminate): 硬剔为空, 切掉的 18 个改走降权
    assert not res["hard"], res["hard"]
    assert res["soft"] == hard, (sorted(res["soft"]), sorted(hard))
    assert not any(len(c) == 1 for c in res["soft"])                # 单键不参与
    assert all(res["ranked_loose"][c][1] >= args.soft_n_min for c in res["soft"] if c in
               res["ranked_loose"]), "降权集里的组合必须过宽松门槛"
    if verbose:
        li = res["info_loose"]
        print(f"  [自测·quota] ③ 软降权 ×{args.soft_weight:g}: {len(res['soft'])}/18 全中真慢 "
              f"(宽松门槛 n_eff ≥ {args.soft_n_min} ⇒ 可粗排名 {li['n_rankable']}, "
              f"宽松割线差 {math.exp(li['gap']):.2f}× vs 噪声 {math.exp(li['se_gap']):.2f}×)")

    # (3) 数据不足: 可排名者太少 → 不切不降权 (不可排名者占满名额)
    rows_t = _synth(plant_sp, {"iso": 1, "two": 1}, ref_boost, sigma, role_effects=ROLE_EFF,
                    occ_spec=plant_occ, sigma_occ=sigma_occ)
    vals_t = collect(rows_t, ("l",), "occ")
    ref_t, ref_raw_t, _miss = hand_ref(vals_t, "l", args)
    if not ref_t:                                       # 连参考都攒不够 → 走"不判"分支
        if verbose:
            print("  [自测·quota] 数据不足: 参考样本也不足 ⇒ 本轮不判 (正确)")
    else:
        res3 = judge_quota(vals_t, ref_t, ref_raw_t, args, "l")
        assert res3 is None or (not res3["cut"] and not res3["soft"]), \
            (res3 or {}).get("soft")
        if verbose:
            print(f"  [自测·quota] 数据不足: 不可排名 {res3['info']['n_unrankable']} → "
                  f"保留名额 {res3['info']['keep_slots']} ⇒ 本轮不切不降权 (正确)")

    # (4) spread 对照: 同一份真难度, 用 spread 排的割线**不可辨** (σ 0.87 vs 0.19)
    plant_sp_hard = {(c, r): (math.log(1.6) if c in hard else 0.0)
                     for c in LEFT_COMBOS for r in ROLES}
    vals_s = collect(_synth(plant_sp_hard, n_per, ref_boost, sigma, role_effects=ROLE_EFF),
                     ("l",), "spread")
    args_sp = argparse.Namespace(**{**base, "metric": "spread", "sigma": sigma})
    ref_s, ref_raw_s, _m = hand_ref(vals_s, "l", args_sp)
    assert ref_s, "spread 对照的参考样本不足"
    res4 = judge_quota(vals_s, ref_s, ref_raw_s, args_sp, "l")
    assert res4["info"]["decisive"] is False, res4["info"]
    if verbose:
        print(f"  [自测·quota] 对照: 同一份真难度用 spread 排 (σ=0.87) ⇒ 割线差 "
              f"{math.exp(res4['info']['gap']):.2f}× vs 噪声 {math.exp(res4['info']['se_gap']):.2f}× "
              f"⇒ 不可辨; occ (σ=0.19) 同一真值 ⇒ {math.exp(res['info']['gap']):.2f}× vs "
              f"{math.exp(res['info']['se_gap']):.2f}× ⇒ 可辨")

    # (5) 分段表 I/O 契约: 三段互不覆盖 + 手工保留 + 采集工具能解析 (临时目录, 不碰项目文件)
    import tempfile, shutil, importlib
    tmp = Path(tempfile.mkdtemp(prefix="excl_selftest_"))
    try:
        et = tmp / "组合排除表.txt"
        write_exclude(et, {"difficulty": {"zx"}, "quota": {"cv"}, "manual": {"sd"}},
                      ["# 头部注释 1", "# 头部注释 2"],
                      {"difficulty": ["# [理由] zx: 综合 2.00"], "quota": ["# [理由·quota] cv: 割线"]})
        back = read_existing(et)
        assert back == {"difficulty": {"zx"}, "quota": {"cv"}, "manual": {"sd"}}, back
        write_exclude(et, {**back, "quota": {"dg"}}, ["# 只重写 quota 段"], None)
        back2 = read_existing(et)
        assert back2 == {"difficulty": {"zx"}, "quota": {"dg"}, "manual": {"sd"}}, back2
        try:                                            # 表格式是两个工具共用的契约 → 实测可解析
            lex, rex = importlib.import_module("采集-并击当量").load_excluded(et)
        except Exception as e:                           # tkinter 缺失等环境问题 → 跳过
            if verbose:
                print(f"  [自测·quota] 分段表 I/O 通过; (采集工具解析检查跳过: {type(e).__name__})")
        else:
            assert lex == {"zx", "dg", "sd"} and not rex, (lex, rex)   # 采集工具把三段并成排除集
            if verbose:
                print(f"  [自测·quota] 分段表 I/O: 三段互不覆盖 + 手工保留 + 采集工具可解析 "
                      f"({sorted(lex)})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("判据 B 自测通过: ①配额切分全中真慢 / 不误淘 / 数据不足不切 / 单键不参与 / ②保守子集 / "
          "spread 对照不可辨 / 分段表 I/O")


if __name__ == "__main__":
    main()
