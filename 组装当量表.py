#!/usr/bin/env python3
"""
组装当量表.py — 用 当量表（occ/gap）组装标准产物（**纯击键时间, 无错误项**）

读:
  产物/当量表-并击-{l,r}.npz  occ 表（角色×组合）+ gap 表（组合×组合）+ version/meta（**按手分文件**）
                            （由 分析-当量模型.py --full 生成）
写:
  产物/段当量表-{l,r}.npz     version + cost_ms(恒 0) + occ_seg / gap_seg
  产物/总当量-并击-{l,r}.txt  1 击词 / 2 击词的期望耗时（ms 原值, 不归一化）

段当量口径（**2026-10-14 用户决策: 错误率**不再进当量**）**:
  occ_seg(组合, 角色) = occ(组合, 角色)        ← **就是时值, 无任何加项**
  gap_seg(c₁, c₂)     = gap(c₁, c₂)
  ⚠ **本条已**撤除**"过"错误项当量"**（`--cost N` / `occ_seg += N×P_err` / 敏感性扫描 /
    `段当量表-含错误-*.npz` / `总当量-并击-含错误-*.txt` 全部删除, 不再读取 `数据/错误率表.txt`）。
  **为什么撤除（用户 2026-10-14 原话）**: "错误时间在并击中**难以估计**, 且 **1 类错误中可能包含
    真实错误和读图错误**。所以错误率模型保留, 但是**以后不再将错误率加入当量**, 也不用错误率加入
    剔除分析。" ⇒ 成本常数 `ERR_COST_MS`(782.2) 本就是**移植自串击、非本机实测的指定值**,
    再乘一个"读取型/运动型混在一起"的 P_err, 得到的不是可报的量。
  · **错误率模型保留**（`分析-错误率.py` → `数据/错误率表.txt`）——但它现在是**独立参考**:
    既不进本脚本, 也不进 `分析-难度剔除.py`。
  · `cost_ms` 字段**保留恒 0**（产物 schema 兼容下游, 不再有非 0 取值）。
  · 历史读数（含错误项产物, 最后一次 cost 782.2 @2026-10-13 10:46）已删除; 复现路径见 memory
    （需要时按 `并击公共.ERR_COST_MS` + 当时的 组装 逻辑重写即可, 但**不作为现行口径**）。

词当量（README §4.1/§4.6; **v2.33 简化** 2026-10-04 用户决策）:
  单手表链 = occ_seg(c₁,S1) + gap_seg(c₁,c₂) + occ_seg(c₂,S3)
  双边词   = **max_h 手链**（2 击词不再单列闸门项 —— 全枚举 550 万真实词 Δ≡0, 见 compose_word）
  ⚠ 双边合成的残差仍**本协议不可实测验证**（both 已移除）: 不可测的是"手独立 + 预放置吸收度",
    不是闸门项（闸门项已被证明恒为 0）→ 报数时仍按下界方向注明

用法: python 组装当量表.py [--hand l|r] [--selftest]
"""
import sys, json, argparse, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from 并击公共 import BASE, LEFT_COMBOS, ROLES


# 产物**按手分文件**（2026-10-13 用户"产物表改成左右手分开"）
def model_npz(hand):
    """输入: 当量表（分析-当量模型.py --full 写）"""
    return BASE / "产物" / f"当量表-并击-{hand}.npz"


def out_npz(hand):
    return BASE / "产物" / f"段当量表-{hand}.npz"


def out_txt(hand):
    return BASE / "产物" / f"总当量-并击-{hand}.txt"


MODEL_NPZ = model_npz("l")          # 兼容旧引用
OUT_NPZ = out_npz("l")
OUT_TXT = out_txt("l")
ASSEMBLY_VERSION = 1
COST_MS = 0.0                       # **恒 0**: 错误项口径已撤除（见文件头）


def read_tables(path=None, hand="l"):
    path = model_npz(hand) if path is None else path
    """读 当量表 npz → (combos, occ, gap, meta, version)"""
    with np.load(path, allow_pickle=False) as z:
        return (list(z["combos"]), z["occ"], z["gap"],
                json.loads(str(z["meta"])), int(z["version"]))


def assemble(combos, occ, gap):
    """段当量表 = **时值本身**（无错误项; 见文件头 —— 错误率不进当量）"""
    return (np.array(occ, dtype=np.float64, copy=True),
            np.array(gap, dtype=np.float64, copy=True))


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
    ap.add_argument("--hand", choices=["l", "r"], default="l")
    ap.add_argument("--pairs", type=int, default=20000, help="2 击词抽样词对数（全空间 79²）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    mdl_path = model_npz(args.hand)
    if not mdl_path.exists():
        print(f"缺 {mdl_path.name} — 先跑 分析-当量模型.py --hand {args.hand} --full"
              f"（产物链: 模型 → 本脚本）")
        return
    combos, occ, gap, meta, ver = read_tables(mdl_path)
    occ_seg, gap_seg = assemble(combos, occ, gap)

    rng = np.random.RandomState(2024)
    pairs = [(combos[rng.randint(len(combos))], combos[rng.randint(len(combos))])
             for _ in range(args.pairs)]
    one, two = word_times(combos, occ_seg, gap_seg, pairs=pairs)
    q1, q2 = quant(one), quant(two)

    print(f"═══ 组装 {meta.get('hand')} 手当量表 ═══")
    print(f"输入: 当量表 version {ver}（模型 {meta.get('model')}, {meta.get('n_combos')} 组合）")
    print("错误项: **不参与**（纯击键时间 —— 2026-10-14 用户: 错误时间难以估计, "
          "且 R1 里混着真实错误与读图错误 ⇒ 错误率模型保留但不进当量、不进剔除）")
    print(f"\n1 击词（孤立占用, 纯击键时间）: n={q1['n']} med={q1['med']:.0f} "
          f"p25={q1['p25']:.0f} p75={q1['p75']:.0f} max={q1['max']:.0f} ms")
    print(f"2 击词（三段合成, 纯击键时间）: n={q2['n']} med={q2['med']:.0f} "
          f"p25={q2['p25']:.0f} p75={q2['p75']:.0f} max={q2['max']:.0f} ms")
    print(f"  ⚠ 双边合成残差不可实测（both 已移除: 手独立 + 预放置吸收度）→ 方案评估取**下界方向**（只可能低估）; 闸门项本身已证明恒为 0 (v2.33)")

    npz_path, txt_path = out_npz(args.hand), out_txt(args.hand)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    meta_out = dict(meta, cost_ms=COST_MS, assembly_version=ASSEMBLY_VERSION, hand=args.hand,
                    note="occ_seg/gap_seg = 纯击键时间（无错误项; 错误率不参与当量, 2026-10-14 口径）")
    np.savez(npz_path, version=np.int64(ASSEMBLY_VERSION), combos=np.array(combos),
             roles=np.array(ROLES), occ_seg=occ_seg, gap_seg=gap_seg,
             cost_ms=np.float64(COST_MS), meta=json.dumps(meta_out, ensure_ascii=False))
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("# 并击总当量（期望耗时原值, ms; 纯击键时间）— 组装当量表.py 生成\n")
        f.write(f"# 来源: {mdl_path.name} version {ver}（模型 {meta.get('model')}, "
                f"{args.hand} 手）\n")
        f.write("# 错误项口径: **不含错误项**（纯击键时间）—— 2026-10-14 用户: 错误时间在并击中"
                "难以估计, R1 含真实错误与读图错误 ⇒ 错误率模型保留, 但不进当量、不进剔除分析\n")
        f.write(f"# 生成于 {time.strftime('%Y-%m-%d %H:%M')}\n")
        f.write("kind\tn\tmin\tp25\tmed\tp75\tmax\tmean\n")
        for kind, q in (("1击词", q1), ("2击词", q2)):
            f.write(f"{kind}\t{q['n']}\t{q['min']:.1f}\t{q['p25']:.1f}\t{q['med']:.1f}\t"
                    f"{q['p75']:.1f}\t{q['max']:.1f}\t{q['mean']:.1f}\n")
        f.write("# 2击词(单手表) = occ(S1)+gap+occ(S3); 双边词 = max_h 手链 (v2.33: 闸门项恒 0)\n")
    print(f"\n产物: {npz_path.name}（version {ASSEMBLY_VERSION}, occ_seg {occ_seg.shape}, "
          f"gap_seg {gap_seg.shape}）+ {txt_path.name}")


def selftest():
    """产物链自测: 合成表 → 组装 → 检验①**恒等**（时值进、时值出, 无任何加项）
    ②版本/meta ③词当量合成 ④**不读错误率表**（错误率表文件不存在也必须跑得通）"""
    combos = list(LEFT_COMBOS)
    occ = np.full((len(ROLES), len(combos)), 100.0)
    gap = np.full((len(combos), len(combos)), 150.0)
    occ_seg, gap_seg = assemble(combos, occ, gap)
    assert np.array_equal(occ_seg, occ) and np.array_equal(gap_seg, gap)
    print("  ① 恒等: occ_seg ≡ occ / gap_seg ≡ gap（**无错误项加项**）✓")
    # 词当量 = 三段相加（单手表链）
    one, two = word_times(combos, occ_seg, gap_seg, pairs=[(combos[0], combos[1])])
    assert abs(one[0] - 100.0) < 1e-9 and abs(two[0] - (100 + 150 + 100)) < 1e-6, (one[0], two[0])
    print(f"  ② 词当量合成: 1击词 {one[0]:.1f}ms | 2击词 {two[0]:.1f}ms = occ_S1 + gap + occ_S3 ✓")
    # **不依赖错误率表**: 组装路径里没有任何读 P_err 的调用（按**代码对象**查引用, 不查注释文字）
    import inspect
    for fn in (assemble, main, word_times, read_tables, quant):
        names = set(fn.__code__.co_names)
        assert not (names & {"read_perr", "ERR_COST_MS", "PERR_TXT", "perr"}), \
            (fn.__name__, sorted(names & {"read_perr", "ERR_COST_MS", "PERR_TXT", "perr"}))
    assert "read_perr" not in globals() and "ERR_COST_MS" not in globals()
    assert "perr" not in inspect.getsource(assemble) and COST_MS == 0.0
    print("  ③ 无错误项接线: 组装路径（assemble/main/word_times/read_tables）不引用 "
          "P_err / ERR_COST_MS / read_perr（函数与常量均已删除）; cost_ms 恒 0 ✓")
    print("组装自测通过: 恒等（无错误项）/ 词当量合成 / 不读错误率表 / cost_ms 恒 0")


if __name__ == "__main__":
    main()
