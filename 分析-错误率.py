#!/usr/bin/env python3
"""
分析-错误率.py — 击级错误率 P_err（R1-R4）建模与产物导出（v2: 分头 + 练习 + 另一击）

事件口径（**与当量侧解耦**: 错误侧用全部数据, 不切稳定期 —— 姊妹项目同决策）:
  · 机会 = **每一击一次**；错误后试次即中止 ⇒ 记到的是**首个错误**
    ⇒ 这是**首错风险**口径: P(错@1) 与 P(错@2 | 击1无错), 不是各击独立错误率（README §4.2）
  · 每击一行事件: (手, 击序, 角色, 组合, 键数, 几何 φ, 练习位, 另一击键数) → Y
  · 1 击试次只贡献 iso 角色的一次机会; 2 击试次贡献 S1 与 S3 两次机会
  · 错误行照旧参与（错误率建模就该用错误行）, 但**只用其首次错误的击序**（后续击未尝试）

模型 v2（2026-10-11 用户决策"按建议重建"）——**读取/运动分头**:
  · R1 = 读取型（照图转录的选码/读图错）与 R2-R4 = 运动型（失同步/提前击/缺键）分别建模;
    首错机制互斥 ⇒ **P_any = P_r1 + P_mot 精确成立**（不是近似）, 段当量用二者之和
  · 分头的意义: 协变量不同 —— R1 随练习下降（读图熟练）、运动型更多绑定几何/节奏
  · 模型族（每头各自选型; 5-fold 事件级 AUC, 0.01 噪声带内取**参数最少**者）:
      m0 常数 → m1 +段位(角色) → m2 +键数 → m3 +几何 φ → m4 +练习(试次全局位) → m5 +另一击键数
  · 预测网格: 练习位 = 1.0（**当前状态语义**, 与当量侧一致）; 另一击键数 = 该角色的经验占比
    （(组合,角色) 网格没有词对上下文, 取边际 —— 段当量的 +cost×P_err 是逐段期望）

产物: `数据/错误率表.txt`（hand/combo/role/p_err + p_r1/p_mot 诊断列; 组装层读 p_err）

⚠ 事件不足门禁: 单头错误事件 < EVENT_MIN 时该头只报计数与粗略模型, 并在表头标 provisional
  （避免用几十个事件去解释系数——错误的精度 ∝ 1/√事件数）
⚠ v2.35 分界（2026-10-11）: 非目标手输入禁用后, "跨手按错"不再产生 R1 —— 本表基于
  v2.35 之前的数据（R1 含跨手按错）; 之后重跑本脚本即自然切换到新口径

用法: python 分析-错误率.py [--hand l|r|both] [--selftest]
"""
import sys, math, argparse, time
from pathlib import Path
from collections import Counter, namedtuple
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from 并击公共 import (BASE, read_tsv, ROLES, LEFT_COMBOS, RIGHT_COMBOS,
                     KEY_POS)

DATA = BASE / "当量数据.tsv"
OUT_TXT = BASE / "数据" / "错误率表.txt"
EVENT_MIN = 100            # 单头事件不足门禁（低于此只报计数 + provisional）
SEED = 2024
MECH = {"R1": "键序错误(按错键)", "R2": "失同步(散布超限)", "R3": "提前击(未全放)", "R4": "缺键"}
# 机制性质（**决策依据, 2026-09-24**）:
#   读取型 = R1 按错键 —— 采集是"照图转录", 这类错误主要是**没读对键位组合**（读取/计划错）,
#            不代表真机使用的按键错误率（用户实测: 真机并击按键错误率低）
#   运动型 = R2 失同步 / R3 提前击 / R4 缺键 —— "没按成一击", 语义上才属于并击当量的错误成本
MECH_KIND = {"R1": "读取型", "R2": "运动型", "R3": "运动型", "R4": "运动型"}
HEADS = ("r1", "mot")      # 分头（互斥 ⇒ P_any = P_r1 + P_mot 精确）
HEAD_NAME = {"r1": "读取型 R1", "mot": "运动型 R2-R4", "any": "全体 R1-R4"}
LEVEL_NAMES = ("m0 常数", "m1 +段位", "m2 +键数", "m3 +几何", "m4 +练习", "m5 +另一击")

Ev = namedtuple("Ev", "h k role c phi kind pos other2")


def phi_combo(combo):
    """组合几何（与错误率相关的"别扭度"候选量; 键位重排后对未采组合仍可算）"""
    ps = [KEY_POS[c] for c in combo]
    rows = [r for r, _ in ps]
    cols = [c for _, c in ps]
    span = math.hypot(max(rows) - min(rows), max(cols) - min(cols))
    return [len(combo) - 1, max(rows) - min(rows), max(cols) - min(cols), span,
            float(len(set(cols)) != len(cols))]      # 同列(=同指)重复


def build_events(rows, hands):
    """→ [Ev]（首错风险口径: 错误行的首次错击记 kind, 其后不再记; 附练习位与另一击键数）"""
    ev = []
    n = max(1, len(rows) - 1)
    for i, r in enumerate(rows):
        code = r.get("code", "")
        parts = [p for p in code.split("|") if p]
        if not parts:
            continue
        bad = r.get("error") == "1"
        err_stroke, kind = 0, ""
        if bad:
            tag = r.get("err_type", "")
            mech = tag.split("@")[0] if "@" in tag else ""
            kind = {"R1": "r1"}.get(mech, "mot" if mech in MECH_KIND else "")
            if "@" in tag:
                try:
                    err_stroke = int(tag.split("@")[1])
                except ValueError:
                    err_stroke = 0
        pos = i / n
        for h in hands:
            side = set("qwertasdfgzxcvb" if h == "l" else "yuiophjkl;nm,./")
            keyns = ["".join(ch for ch in p if ch in side) for p in parts]
            for k, c in enumerate(keyns, start=1):
                if not c:
                    continue
                role = "iso" if len(parts) == 1 else ("S1" if k == 1 else "S3")
                if bad and err_stroke and k > err_stroke:
                    continue                          # 错误后试次中止, 该击未尝试
                other = (keyns[1] if k == 1 else keyns[0]) if len(parts) == 2 else ""
                ev.append(Ev(h, k, role, c, phi_combo(c),
                             kind if (bad and err_stroke == k) else "",
                             pos, float(len(other) >= 2)))
    return ev


def design(ev, level):
    """特征矩阵（level = 0 常数 / 1 +角色 / 2 +键数 / 3 +几何 / 4 +练习 / 5 +另一击）"""
    X = []
    for e in ev:
        f = [1.0]
        if level >= 1:
            f += [float(e.role == r) for r in ("S1", "S3")]      # iso 为基准
        if level >= 2:
            f += [e.phi[0]]
        if level >= 3:
            f += e.phi[1:]
        if level >= 4:
            f += [e.pos]                                          # 练习: 试次全局位 ∈ [0,1]
        if level >= 5:
            f += [e.other2]                                       # 另一击是双键 (S1/S3)
        X.append(f)
    return np.asarray(X, float)


def y_of(ev, head):
    """分头响应: r1/mot 互斥 ⇒ any = r1 + mot 精确; any = 旧口径（selftest 兼容）"""
    if head == "r1":
        return np.asarray([float(e.kind == "r1") for e in ev])
    if head == "mot":
        return np.asarray([float(e.kind == "mot") for e in ev])
    return np.asarray([float(e.kind != "") for e in ev])


def fit_logit(X, y, l2=1.0):
    """IRLS 逻辑回归（L2 正则; 事件稀疏时靠正则稳住）→ (w, 标准误)"""
    w = np.zeros(X.shape[1])
    for _ in range(60):
        eta = X @ w
        p = 1 / (1 + np.exp(-np.clip(eta, -30, 30)))
        Wd = np.clip(p * (1 - p), 1e-9, None)
        g = X.T @ (p - y) + l2 * w
        H = (X * Wd[:, None]).T @ X + l2 * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    eta = X @ w
    p = 1 / (1 + np.exp(-np.clip(eta, -30, 30)))
    Wd = np.clip(p * (1 - p), 1e-9, None)
    cov = np.linalg.inv((X * Wd[:, None]).T @ X + l2 * np.eye(X.shape[1]))
    return w, np.sqrt(np.diag(cov))


def auc(y, s):
    y, s = np.asarray(y), np.asarray(s)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())


def cv_auc(X, y, folds=5, seed=SEED):
    rs = np.random.RandomState(seed)
    idx = rs.permutation(len(y))
    scores = np.zeros(len(y))
    for f in range(folds):
        te = idx[f::folds]
        tr = np.setdiff1d(idx, te)
        w, _ = fit_logit(X[tr], y[tr])
        scores[te] = X[te] @ w
    return auc(y, scores)


def select_model(ev, head):
    """单头选型: 模型族 m0-m5 各自 5-fold AUC → 0.01 噪声带内取**参数最少**者（≥1 级）"""
    y = y_of(ev, head)
    fam = []
    for level in range(6):
        X = design(ev, level)
        w, se = fit_logit(X, y)
        ll = float((y * np.log(np.clip(1 / (1 + np.exp(-X @ w)), 1e-12, 1)) +
                    (1 - y) * np.log(np.clip(1 - 1 / (1 + np.exp(-X @ w)), 1e-12, 1))).sum())
        fam.append((LEVEL_NAMES[level], level, len(w), ll, 2 * len(w) - 2 * ll,
                    cv_auc(X, y), w, se))
    top = max(t[5] for t in fam[1:])
    best = min([t for t in fam[1:] if t[5] >= top - 0.01], key=lambda t: t[2])
    return fam, best


def predict_grid(best, combos, other_share, roles=ROLES, pos_now=1.0):
    """对 (组合, 角色) 网格预测该头概率。
    练习位 = pos_now=1.0（当前状态语义, 与当量侧一致）; 另一击键数 = 该角色经验占比
    （(组合,角色) 网格没有词对上下文, 取边际 —— P 对 other2 近似线性 ⇒ 占比加权 ≈ 边际期望）"""
    name, level, npar, ll, aic, a, w, se = best
    out = {}
    for c in combos:
        phi = phi_combo(c)
        for role in roles:
            f = [1.0]
            if level >= 1:
                f += [float(role == r) for r in ("S1", "S3")]
            if level >= 2:
                f += [phi[0]]
            if level >= 3:
                f += phi[1:]
            if level >= 4:
                f += [pos_now]
            if level >= 5:
                f += [other_share.get(role, 0.0)]
            out[(c, role)] = float(1 / (1 + math.exp(-float(np.dot(w, f)))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", choices=["l", "r", "both"], default="both")
    ap.add_argument("--heads", default="r1,mot",
                    help="分头组合: r1,mot(默认=全量 P_err) / mot(仅运动型, 剔除 R1 读取型) / "
                         "r1(仅读取型)。P_err = 各头之和（互斥 ⇒ 精确）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    rows = read_tsv(DATA)
    if not rows:
        print(f"无数据: {DATA} (尚未开始采集)")
        return
    hands = ("l", "r") if args.hand == "both" else (args.hand,)
    heads_run = tuple(x.strip() for x in args.heads.split(",") if x.strip())
    assert heads_run and all(h in ("r1", "mot") for h in heads_run), args.heads
    ev = build_events(rows, hands)
    n_err = sum(1 for e in ev if e.kind)
    print(f"═══ 击级错误率 v2（分头） ═══\n试次 {len(rows)} | 击级机会 {len(ev)} | 错误事件 {n_err} "
          f"({n_err/max(1,len(ev)):.2%})")

    mech = Counter()
    for r in rows:
        if r.get("error") == "1" and "@" in r.get("err_type", ""):
            mech[r["err_type"].split("@")[0]] += 1
    n_read = sum(v for k, v in mech.items() if MECH_KIND.get(k) == "读取型")
    n_mot = sum(v for k, v in mech.items() if MECH_KIND.get(k) == "运动型")
    print("机制分布: " + "  ".join(f"{k}({MECH_KIND.get(k,'?')}) {v}"
                                   for k, v in sorted(mech.items(), key=lambda x: -x[1])))
    print(f"  读取型(R1) {n_read} ({n_read/max(1,n_read+n_mot):.0%}) vs "
          f"运动型(R2-R4) {n_mot} ({n_mot/max(1,n_read+n_mot):.0%})"
          f"  ← 分头建模; P_any = P_r1 + P_mot（互斥, 精确）")
    print("  机制×击序: " + "  ".join(f"{t}:{c}" for t, c in
          sorted(Counter(r.get('err_type', '') for r in rows if r.get('error') == '1').items(),
                 key=lambda x: -x[1])[:6]))
    by_role = Counter(e.role for e in ev if e.kind)
    print("错误落点: " + "  ".join(f"{r} {by_role.get(r,0)}" for r in ROLES))

    # 另一击键数经验占比（网格预测的边际; 按角色）
    other_share = {}
    for role in ROLES:
        sub = [e for e in ev if e.role == role]
        other_share[role] = (sum(e.other2 for e in sub) / len(sub)) if sub else 0.0
    print("另一击双键占比（网格边际）: " +
          "  ".join(f"{r} {other_share[r]:.2f}" for r in ROLES))

    chosen, hdr_lines = {}, []
    for head in heads_run:
        y = y_of(ev, head)
        n_pos = int(y.sum())
        fam, best = select_model(ev, head)
        print(f"\n── {HEAD_NAME[head]} 头（事件 {n_pos}, base {n_pos/max(1,len(ev)):.4f}）──")
        for name, level, npar, ll, aic, a, w, se in fam:
            coef = " ".join(f"{v:+.2f}" for v in w[1:])[:66]
            mark = " ←取用" if (name, level) == (best[0], best[1]) else ""
            print(f"  {name:>10} 参数 {npar:>3}  AIC {aic:>8.1f}  5-fold AUC {a:.3f}  [{coef}]{mark}")
        chosen[head] = best
        prov = "（⚠ provisional: 事件 < 门禁 100, 系数不作解释）" if n_pos < EVENT_MIN else ""
        print(f"  → 取用 {best[0]}（AUC {best[5]:.3f}, {best[2]} 参数）{prov}")
        hdr_lines.append(f"# {HEAD_NAME[head]}头: {best[0]} (参数 {best[2]}), "
                         f"AUC {best[5]:.3f}, 事件 {n_pos}{prov}")

    # 网格: p_err = p_r1 + p_mot（互斥 ⇒ 精确）
    combos = list(LEFT_COMBOS) + list(RIGHT_COMBOS)
    grids = {h: predict_grid(chosen[h], combos, other_share) for h in heads_run}
    base_rate = n_err / max(1, len(ev))
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("# 并击击级错误率表 — 分析-错误率.py 自动生成（组装当量表.py 读取）\n")
        f.write("# 口径: 首错风险 P(错@k | 前 k−1 击无错), 机会 = 每击一次; 全部数据（不切稳定期）\n")
        f.write("# v2 分头: p_err = p_r1(读取型) + p_mot(运动型)（首错机制互斥 ⇒ 精确）; "
                "练习位=1.0(当前状态), 另一击键数=角色经验占比\n")
        f.write("# ⚠ v2.35 分界: 本表基于非目标手禁用**之前**的数据（R1 含跨手按错）\n")
        f.write(f"# 样本: 试次 {len(rows)} / 机会 {len(ev)} / 错误事件 {n_err} "
                f"(base rate {base_rate:.4f}); 机制 {dict(mech)}\n")
        f.write("\n".join(hdr_lines) + "\n")
        f.write(f"# 状态: {'可用' if min(int(y_of(ev, h).sum()) for h in heads_run) >= EVENT_MIN else 'provisional'}"
                f"; 生成于 {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write("hand\tcombo\trole\tp_err\t" + "\t".join(f"p_{h_}" for h_ in heads_run) + "\n")
        for (c, role) in sorted(grids[heads_run[0]], key=lambda x: (len(x[0]), x[0], x[1])):
            h = "l" if c in set(LEFT_COMBOS) else "r"
            p = sum(grids[h_][(c, role)] for h_ in heads_run)
            diag = "\t".join(f"{grids[h_][(c, role)]:.5f}" for h_ in heads_run)
            f.write(f"{h}\t{c}\t{role}\t{p:.5f}\t{diag}\n")
    print(f"\n→ 导出 {OUT_TXT.name}: {len(grids[heads_run[0]])} 行 (组合×角色, "
          f"p_err = {' + '.join('p_' + h_ for h_ in heads_run)})")
    for role in ROLES:
        ps = [sum(grids[h_][(c, role)] for h_ in heads_run) for c in combos]
        pr = ([grids["r1"][(c, role)] for c in combos] if "r1" in heads_run else ps)
        print(f"  {role}: p_err 中位 {np.median(ps):.4f} "
              f"[p10 {np.percentile(ps, 10):.4f}, p90 {np.percentile(ps, 90):.4f}]; "
              + (f"其中 R1 占 {np.median(pr)/max(1e-9, np.median(ps)):.0%}"
                 if "r1" in heads_run else "（仅运动型）"))
    for c in ("sdf", "jkl"):
        row = " / ".join(f"{role} {sum(grids[h_][(c, role)] for h_ in heads_run):.5f}"
                         for role in ROLES)
        print(f"  3 键 {c}: p_err = {row}")


def selftest():
    """合成事件: 段位/键数/几何/练习/另一击 全植入 + 分头互斥 → 检验检出、AUC、加法闭合"""
    rs = np.random.RandomState(7)
    combos = list(LEFT_COMBOS)
    ev = []
    for i in range(6000):
        c = combos[rs.randint(len(combos))]
        role = ROLES[rs.randint(3)]
        phi = phi_combo(c)
        pos = i / 5999
        other2 = float(rs.rand() < 0.6)
        # 植入: S3 效应 + 键数 + 几何 + 练习(后段更少错) + 另一击; 机制 = R1(70%)/运动(30%)
        eta = -3.2 + 1.2 * (role == "S3") + 0.8 * phi[0] + 0.5 * phi[3] - 1.2 * pos + 0.4 * other2
        p_any = 1 / (1 + math.exp(-eta))
        kind = ("r1" if rs.rand() < 0.7 else "mot") if rs.rand() < p_any else ""
        ev.append(Ev("l", 1 if role != "S3" else 2, role, c, phi, kind, pos, other2))
    n_err = sum(1 for e in ev if e.kind)
    n_r1 = sum(1 for e in ev if e.kind == "r1")
    print(f"合成事件 {len(ev)} / 错误 {n_err}（其中 R1 {n_r1}）")
    # any 头: 各级 AUC（练习/另一击应带来增量）
    y_any = y_of(ev, "any")
    aucs = [cv_auc(design(ev, lv), y_any) for lv in range(6)]
    print("any 头各级 AUC:", " ".join(f"m{k}={a:.3f}" for k, a in enumerate(aucs)))
    assert aucs[0] < 0.55, aucs                       # 常数模型: 无判别力
    assert aucs[3] > 0.70, aucs                       # 含几何 → 应有判别力
    assert aucs[4] > aucs[3] + 0.01, aucs             # 练习植入 → m4 应优于 m3
    assert aucs[5] >= aucs[4] - 0.005, aucs           # 另一击不应变差
    X, y = design(ev, 5), y_of(ev, "any")
    w, se = fit_logit(X, y)
    assert w[2] > 0.8, w                              # S3 系数应为正（植入 +1.2）
    assert w[8] < -0.8, w                             # 练习系数应为负（植入 −1.2; 列序 = 段位2+键数1+几何4）
    assert w[9] > 0.1, w                              # 另一击系数应为正（植入 +0.4）
    assert se[2] < 0.3, se                            # 事件足够 → SE 小
    # 分头: 互斥 ⇒ 网格 p_any ≈ p_r1 + p_mot（逐格闭合）
    fam_r1, best_r1 = select_model(ev, "r1")
    fam_mot, best_mot = select_model(ev, "mot")
    share = {r: 0.5 for r in ROLES}
    g_r1 = predict_grid(best_r1, combos[:5], share)
    g_mot = predict_grid(best_mot, combos[:5], share)
    g_any = predict_grid(select_model(ev, "any")[1], combos[:5], share)
    for k in g_r1:
        assert abs((g_r1[k] + g_mot[k]) - g_any[k]) < 0.01, (k, g_r1[k], g_mot[k], g_any[k])
    assert all(0 < p < 1 for p in g_r1.values())
    print(f"分头: r1 取 {best_r1[0]} (AUC {best_r1[5]:.3f}) / mot 取 {best_mot[0]} "
          f"(AUC {best_mot[5]:.3f}); p_r1+p_mot 与 any 逐格闭合 (<0.01) ✓")
    print("错误率自测通过: 常数无判别 / 特征化判别 / 练习与另一击有增量 / S3·练习系数符号正确 / "
          "分头加法闭合 / 网格预测在 (0,1)")


if __name__ == "__main__":
    main()
