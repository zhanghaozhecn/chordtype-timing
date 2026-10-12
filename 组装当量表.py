#!/usr/bin/env python3
"""
组装当量表.py — 用 当量表（occ/gap）组装标准产物（**默认纯击键时间**）

读:
  产物/当量表-并击.npz       occ 表（角色×组合）+ gap 表（组合×组合）+ version/meta
                            （由 分析-当量模型.py --full 生成）
  数据/错误率表.txt          每 (组合, 角色) 的 P_err（由 分析-错误率.py 生成; **仅诊断**）
  并击公共.ERR_COST_MS       错误成本常数 782.2ms（**指定值, 非本机实测**）
写:
  产物/段当量表.npz          version + err_cost_ms + occ_seg / gap_seg
  产物/总当量-并击.txt       1 击词 / 2 击词的期望耗时（ms 原值, 不归一化）

段当量口径（**2026-09-24 用户决策: 默认纯击键时间, 不含错误项**）:
  occ_seg(组合, 角色) = occ(组合, 角色)        ← 默认;  gap_seg(c₁, c₂) = gap(c₁, c₂)
  `--cost 782.2` 可打开旧口径（occ_seg += cost × P_err）。
  **为什么默认关**: 采集本质是"照图转录"任务, 实测 88% 的错误是 **R1 按错键**
  （读取/计划错, 且 30/34 落在**第二击**——第二块键位图要在击间间隙里读, 工作记忆负荷最大）;
  运动型错误（R2 失同步 / R3 提前击 / R4 缺键, = "没按成一击"）只占 12%。
  真机使用并击时按键错误率低（用户 2026-09-24 实测判断）⇒ 转录任务测得的 P_err
  不代表真机错误率 → 错误项暂不计入当量, 保留为可选项与诊断。
  ⚠ 若打开错误项: 错误机会是**每击一次**（2 击词 = 2 次, 落在 S1/S3 两个 occ 段）;
    gap 段是纯移动时间、无独立错误机会（次击错误已计在 S3）, 计在 gap 上会三重计数。
  ⚠ 真机错误率要连续文本录入才测得到（与词间中断同源, README §8）。

词当量（README §3.3/§3.6; **v2.33 简化** 2026-10-04 用户决策）:
  单手表链 = occ_seg(c₁,S1) + gap_seg(c₁,c₂) + occ_seg(c₂,S3)
  双边词   = **max_h 手链**（2 击词不再单列闸门项 —— 全枚举 550 万真实词 Δ≡0, 见 compose_word）
  ⚠ 双边合成的残差仍**本协议不可实测验证**（both 已移除）: 不可测的是"手独立 + 预放置吸收度",
    不是闸门项（闸门项已被证明恒为 0）→ 报数时仍按下界方向注明

用法: python 组装当量表.py [--cost 0] [--hand l] [--selftest]
      --cost 0（默认）= 纯击键时间 → 写 段当量表.npz / 总当量-并击.txt（生产产物）
      --cost N>0 = **含错误项** 段当量 = 时值 + N×P_err → 写**独立文件**
        段当量表-含错误.npz / 总当量-并击-含错误.txt（v2 2026-10-11: 不再覆盖生产产物,
        旧的"跑完 --cost 须不带 --cost 复原"步骠除外）; 同时打印敏感性扫描
        {0, 400, 782.2, 1000, 2000}（铁律 5: 错误成本是指定常数, 报数必须带区间）
"""
import sys, json, argparse, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from 并击公共 import BASE, LEFT_COMBOS, ROLES, ERR_COST_MS

MODEL_NPZ = BASE / "产物" / "当量表-并击.npz"
PERR_TXT = BASE / "数据" / "错误率表.txt"
OUT_NPZ = BASE / "产物" / "段当量表.npz"
OUT_TXT = BASE / "产物" / "总当量-并击.txt"
OUT_NPZ_ERR = BASE / "产物" / "段当量表-含错误.npz"     # --cost N>0 写这里（不覆盖生产产物）
OUT_TXT_ERR = BASE / "产物" / "总当量-并击-含错误.txt"
ASSEMBLY_VERSION = 1


def read_perr(path=PERR_TXT):
    """→ {(手, 组合, 角色): P_err} + 表头注释行（原样带进产物, 便于追溯模型/样本/状态）"""
    if not Path(path).exists():
        return {}, []
    hdr, out = [], {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            hdr.append(line)
            continue
        f = line.split("\t")
        if len(f) >= 4 and f[0] in ("l", "r"):    # v2 错误率表: 第 5/6 列 = p_r1/p_mot（诊断, 不读）
            out[(f[0], f[1], f[2])] = float(f[3])
    return out, hdr


def read_tables(path=MODEL_NPZ):
    """读 当量表 npz → (combos, occ, gap, meta, version)"""
    with np.load(path, allow_pickle=False) as z:
        return (list(z["combos"]), z["occ"], z["gap"],
                json.loads(str(z["meta"])), int(z["version"]))


def assemble(combos, occ, gap, perr, hand, cost):
    """段当量 = 时值 + cost×P_err（角色化）; P_err 缺失 → 0 并置标志"""
    ci = {c: i for i, c in enumerate(combos)}
    occ_seg = np.array(occ, dtype=np.float64, copy=True)
    missing = 0
    for ri, role in enumerate(ROLES):
        for j, c in enumerate(combos):
            p = perr.get((hand, c, role))
            if p is None:
                missing += 1
                p = 0.0
            occ_seg[ri, j] += cost * p
    # gap 侧: **不加错误项** —— 错误机会按"每击一次", 已由 S1/S3 两个 occ 段承载（见文件头）
    return occ_seg, np.array(gap, dtype=np.float64, copy=True), missing


def word_times(combos, occ_seg, gap_seg, pairs=None):
    """代表性词当量: 1 击词（孤立占用）与 2 击词（三段合成）的分布; 用于 txt 产物"""
    ci = {c: i for i, c in enumerate(combos)}
    one = [float(occ_seg[ROLES.index("iso"), i]) for i in range(len(combos))]
    two = []
    pairs = pairs or [(a, b) for a in combos for b in combos]
    for a, b in pairs:
        ia, ib = ci.get(a), ci.get(b)
        if ia is None or ib is None:
            continue
        two.append(float(occ_seg[ROLES.index("S1"), ia] + gap_seg[ia, ib]
                         + occ_seg[ROLES.index("S3"), ib]))
    return one, two


def quant(v):
    v = sorted(v)
    def q(p):
        return v[min(len(v) - 1, int(p * len(v)))] if v else float("nan")
    return dict(n=len(v), min=q(0), p25=q(0.25), med=q(0.5), p75=q(0.75), max=q(1 - 1e-9),
                mean=float(np.mean(v)) if v else float("nan"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost", type=float, default=0.0,
                    help="错误成本 ms: **默认 0 = 纯击键时间**（2026-09-24 口径, 见文件头）; "
                         f"填 {ERR_COST_MS} 打开旧口径 / 400·1000·2000 做扫描")
    ap.add_argument("--hand", choices=["l", "r"], default="l")
    ap.add_argument("--pairs", type=int, default=20000, help="2 击词抽样词对数（全空间 79²）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not MODEL_NPZ.exists():
        print(f"缺 {MODEL_NPZ.name} — 先跑 分析-当量模型.py --full（产物链: 模型 → 本脚本）")
        return
    combos, occ, gap, meta, ver = read_tables()
    perr, perr_hdr = read_perr()
    if not perr:
        print(f"⚠ 缺 {PERR_TXT.name} — 错误项按 0 处理（先跑 分析-错误率.py）")
    occ_seg, gap_seg, missing = assemble(combos, occ, gap, perr, args.hand, args.cost)

    rng = np.random.RandomState(2024)
    pairs = [(combos[rng.randint(len(combos))], combos[rng.randint(len(combos))])
             for _ in range(args.pairs)]
    one, two = word_times(combos, occ_seg, gap_seg, pairs=pairs)
    q1, q2 = quant(one), quant(two)

    # 敏感性扫描（铁律 5: 错误成本是指定常数 ⇒ 报含错误项版本必须带区间; 端点 0 = 纯时值）
    if args.cost > 0:
        print("")
        print("── 错误成本敏感性扫描（1击词/2击词 中位, ms）──")
        for cv in (0.0, 400.0, ERR_COST_MS, 1000.0, 2000.0):
            os_, gs_, _m = assemble(combos, occ, gap, perr, args.hand, cv)
            o1, t2 = word_times(combos, os_, gs_, pairs=pairs)
            qq1, qq2 = quant(o1), quant(t2)
            mark = " ←本档" if abs(cv - args.cost) < 1e-9 else ""
            print(f"  cost {cv:6.1f}: 1击词 {qq1['med']:6.1f} / 2击词 {qq2['med']:6.1f}"
                  f"   (mean {qq1['mean']:6.1f} / {qq2['mean']:6.1f}){mark}")

    print(f"═══ 组装 {meta.get('hand')} 手当量表 ═══")
    print(f"输入: 当量表 version {ver}（模型 {meta.get('model')}, {meta.get('n_combos')} 组合）"
          f" + 错误率表 {len(perr)} 行" + (f"（{len(perr_hdr)} 行注释）" if perr_hdr else ""))
    print(f"错误项: " + ("**关闭**（纯击键时间, 2026-09-24 口径 — 转录任务的 P_err 不代表真机）"
          if args.cost == 0 else f"打开, 错误成本 {args.cost:.1f}ms"
          + ("（指定常数, 非本机实测）" if args.cost == ERR_COST_MS else "")))
    if missing:
        print(f"⚠ P_err 缺失 {missing} 个 (组合,角色) → 该格错误项取 0")
    tag = "纯击键时间" if args.cost == 0 else "含错误项"
    print(f"\n1 击词（孤立占用，{tag}）: n={q1['n']} med={q1['med']:.0f} "
          f"p25={q1['p25']:.0f} p75={q1['p75']:.0f} max={q1['max']:.0f} ms")
    print(f"2 击词（三段合成，{tag}）: n={q2['n']} med={q2['med']:.0f} "
          f"p25={q2['p25']:.0f} p75={q2['p75']:.0f} max={q2['max']:.0f} ms")
    print(f"  ⚠ 双边合成残差不可实测（both 已移除: 手独立 + 预放置吸收度）→ 方案评估取**下界方向**（只可能低估）; 闸门项本身已证明恒为 0 (v2.33)")

    # 写产物（cost=0 → 生产产物; cost>0 → 含错误项独立文件, 不覆盖生产产物）
    out_npz = OUT_NPZ if args.cost == 0 else OUT_NPZ_ERR
    out_txt = OUT_TXT if args.cost == 0 else OUT_TXT_ERR
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    meta_out = dict(meta, cost_ms=args.cost, assembly_version=ASSEMBLY_VERSION,
                    perr_rows=len(perr), hand=args.hand,
                    note=("occ_seg/gap_seg = 纯击键时间（不含错误项）"
                          if args.cost == 0 else
                          "occ_seg = 时值 + cost×P_err（首错风险口径）; gap_seg 纯时值"))
    np.savez(out_npz, version=np.int64(ASSEMBLY_VERSION), combos=np.array(combos),
             roles=np.array(ROLES), occ_seg=occ_seg, gap_seg=gap_seg,
             cost_ms=np.float64(args.cost), meta=json.dumps(meta_out, ensure_ascii=False))
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(f"# 并击总当量（期望耗时原值, ms; {tag}）— 组装当量表.py 生成\n")
        f.write(f"# 来源: 当量表-并击.npz version {ver}（模型 {meta.get('model')}）"
                f" + 错误率表 {len(perr)} 行（诊断） + 错误项 {'关闭' if args.cost == 0 else f'{args.cost:.1f}ms'}\n")
        f.write("# 错误成本口径: " + ("**不含错误项**（纯击键时间 —— 转录错误以 R1 读取型为主, "
                "不代表真机; 2026-09-24 决策, README §3.5）\n" if args.cost == 0 else
                f"含错误项 cost={args.cost:.1f}ms"
                + ("（指定常数, 非本机实测）" if args.cost == ERR_COST_MS else "") + "\n"))
        for l in perr_hdr[:3]:
            f.write(f"# P_err 表头: {l.lstrip('# ')}\n")
        f.write(f"# 生成于 {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write("kind\tn\tmin\tp25\tmed\tp75\tmax\tmean\n")
        for kind, q in (("1击词", q1), ("2击词", q2)):
            f.write(f"{kind}\t{q['n']}\t{q['min']:.1f}\t{q['p25']:.1f}\t{q['med']:.1f}\t"
                    f"{q['p75']:.1f}\t{q['max']:.1f}\t{q['mean']:.1f}\n")
        f.write("# 2击词(单手表) = occ(S1)+gap+occ(S3); 双边词 = max_h 手链 (v2.33: 闸门项恒 0)\n")
    print(f"\n产物: {out_npz.name}（version {ASSEMBLY_VERSION}, occ_seg {occ_seg.shape}, "
          f"gap_seg {gap_seg.shape}）+ {out_txt.name}"
          + ("（含错误项 → 独立文件, 生产产物未动）" if args.cost > 0 else ""))


def selftest():
    """产物链自测: 合成表 → 组装 → 检验①时值+错误项可加性 ②版本/meta ③词当量合成"""
    combos = list(LEFT_COMBOS)
    occ = np.full((len(ROLES), len(combos)), 100.0)
    gap = np.full((len(combos), len(combos)), 150.0)
    perr = {}
    for c in combos:
        for role in ROLES:
            perr[("l", c, role)] = 0.01 if role != "S3" else 0.05
    cost = 800.0
    occ_seg, gap_seg, missing = assemble(combos, occ, gap, perr, "l", cost)
    assert missing == 0
    assert abs(occ_seg[ROLES.index("S1"), 0] - (100 + cost * 0.01)) < 1e-9
    assert abs(occ_seg[ROLES.index("S3"), 0] - (100 + cost * 0.05)) < 1e-9
    one, two = word_times(combos, occ_seg, gap_seg, pairs=[(combos[0], combos[1])])
    want = (100 + cost * 0.01) + 150 + (100 + cost * 0.05)   # gap 不带错误项
    assert abs(two[0] - want) < 1e-6, (two[0], want)
    print(f"  合成表: 1击词 {one[0]:.1f}ms | 2击词 {two[0]:.1f}ms "
          f"(= occ_S1 + gap + occ_S3, 三段各含错误项) ✓")
    # 缺 P_err → 错误项取 0 并计数
    occ_seg2, _, miss2 = assemble(combos, occ, gap, {}, "l", cost)
    assert miss2 == len(ROLES) * len(combos)
    assert abs(occ_seg2[0, 0] - 100.0) < 1e-9
    print(f"  P_err 全缺: 错误项 0, 计数 {miss2} ✓")
    # cost=0 → 等于时值（敏感性扫描的端点应与纯时值一致）
    occ_seg3, gap_seg3, _ = assemble(combos, occ, gap, perr, "l", 0.0)
    assert np.allclose(occ_seg3, occ) and np.allclose(gap_seg3, gap)
    print("  --cost 0: 退化为纯时值（敏感性扫描端点自洽）✓")
    print("组装自测通过: 时值+错误项可加 / P_err 缺失兜底 / cost=0 端点 / 词当量合成")


if __name__ == "__main__":
    main()
