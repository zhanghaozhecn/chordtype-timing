#!/usr/bin/env python3
"""
分析-数据检查（只读诊断，不打模型）
用途: 采集数据快速体检 —— M1 首批复核 / 协议校准依据 (README §4)
  - 试次数/错误率 + 错误类型分布 (记录列 err_type: R1 键序 / R2 失同步 / R3 提前击 / R4 缺键)
  - 词当量 wc = max_h(S1+S2+S3) + 三段分量 S1/S2/S3 (v2.6 口径, README §3.3)
  - 1 击行孤立 occ/spread (模型 A 基线 + 上文效应对照)
  - 击内散布 ld-fd (按手内键数分组, 校准 T_SYNC 依据)
  - 门控校验 fd2 >= lu1 (单手行: 本手释放后才有本手下一击)
注: 双手 (both) 采集与相关校验已于 2026-09-07 移除 (README §4.1)
用法: python 分析-数据检查.py [数据文件.tsv]
"""
import sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
from 并击公共 import BASE, LEFT_SET as LEFT, pct   # 手别/数据目录/分位 = 唯一来源 (勿本地再抄一份)

def split_parts(s):
    return ''.join(c for c in s if c in LEFT), ''.join(c for c in s if c not in LEFT)

def main(path):
    if not Path(path).exists():
        print(f"数据文件不存在: {path} (尚未开始正式采集)")
        return
    rows = []
    with open(path, encoding="utf-8") as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            r = line.rstrip("\n").split("\t")
            if len(r) == len(hdr):
                rows.append(dict(zip(hdr, r)))
    if not rows:
        print("无数据行")
        return
    num = lambda v: float(v)
    sessions = sorted({r["session"] for r in rows})
    print(f"试次: {len(rows)}  |  session: {', '.join(sessions)}")

    errs = [r for r in rows if r["error"] == "1"]
    print(f"错误: {len(errs)} ({100*len(errs)/len(rows):.1f}%)")
    # 错误类型: 直接用记录列 err_type (如 'R2@1' = 规则@出错的击序); 缺失则回退反推
    cnt = defaultdict(int)
    for r in errs:
        tag = r.get("err_type", "")
        if tag:
            cnt[tag] += 1
        else:
            cnt["(未记录)"] += 1
    for k, v in sorted(cnt.items()):
        rule = k.split("@")[0]
        note = {"R1": "键序错误(按错键)", "R2": "散布超限(失同步)",
                "R3": "提前击(未全放就按下一击)", "R4": "击不完整(缺键)"}.get(rule, "")
        print(f"  {k}: {v}" + (f"  {note}" if note else ""))
    # 机制性质（决策依据, 2026-09-24）: 读取型(R1, 照图转录时没读对组合) vs 运动型(R2-R4, 没按成一击)
    n_read = sum(v for k, v in cnt.items() if k.split("@")[0] == "R1")
    n_mot = sum(v for k, v in cnt.items() if k.split("@")[0] in ("R2", "R3", "R4"))
    if n_read or n_mot:
        print(f"  读取型(R1) {n_read} ({n_read/(n_read+n_mot):.0%}) vs "
              f"运动型(R2-R4) {n_mot} ({n_mot/(n_read+n_mot):.0%})"
              f"  ← 当量默认不含错误项, 且语义上只有运动型相关（README §3.5）")
    if errs and all(not r.get("err_type") for r in errs):
        print("  ⚠ 该文件无 err_type 列 (旧格式): 无法复原错误类型")

    ok = [r for r in rows if r["error"] == "0"]
    if not ok:
        return
    # 试次类型 (v2.9 混采): 1 = 孤立组合/一击词, 2 = 二字词
    one = [r for r in ok if len([p for p in r["code"].split("|") if p]) == 1]
    two = [r for r in ok if len([p for p in r["code"].split("|") if p]) == 2]
    print(f"试次类型: 1击 {len(one)} ({100*len(one)/max(1,len(ok)):.0f}%) / 2击 {len(two)}")
    A = lambda r, k, h: tuple(num(r[f"{h}{p}{k}"]) for p in ("fd", "ld", "fu", "lu"))

    def stroke_lu(r, k):
        lus = [A(r, k, h)[3] for h in "lr" if A(r, k, h)[3] > 0]
        return max(lus) if lus else 0.0

    def stroke_fd(r, k):
        fds = [A(r, k, h)[0] for h in "lr" if A(r, k, h)[0] > 0]
        return min(fds) if fds else 0.0

    # 门控校验 (仅 2 击行): 下一击首按必须在上一击全放之后 (R3 已拦截, ok 试次应无违反)
    gate_viol = [r for r in two if stroke_fd(r, 2) < stroke_lu(r, 1)]
    print(f"门控校验 fd2>=lu1: 违反 {len(gate_viol)} (应为 0)")

    # 1 击行: 孤立角色 occ / spread (模型 A 基线; 与 2 击行的 S1/S3 对照可量化上文效应)
    one_occ, one_spr = [], []
    for r in one:
        for h in "lr":
            fd, ld, _, lu = A(r, 1, h)
            if lu > 0:
                one_occ.append(lu - fd)
                one_spr.append(ld - fd)
    if one_occ:
        print(f"\n1 击行 (孤立角色): occ med={pct(one_occ,0.5):.0f} p90={pct(one_occ,0.9):.0f}ms | "
              f"spread med={pct(one_spr,0.5):.0f} p90={pct(one_spr,0.9):.0f}ms  (n={len(one_occ)})")

    # v2.6 三段口径按手统计 (README §3.3): S1 词首占用 / S2 换手间隙 / S3 词尾占用
    stats = defaultdict(list)          # 结构 → [wc = max_h(S1+S2+S3)]
    seg_stats = defaultdict(list)      # 段名 → 值
    spreads = defaultdict(list)
    holds = []
    for r in two:
        s1, s2 = r["code"].split("|")
        (l1, r1), (l2, r2c) = split_parts(s1), split_parts(s2)
        wcs = []
        for h, p1, p2 in (("l", l1, l2), ("r", r1, r2c)):
            if not p1 and not p2:
                continue
            fd1, ld1, fu1, lu1 = A(r, 1, h)
            fd2, ld2, fu2, lu2 = A(r, 2, h)
            if lu1 <= 0 or lu2 <= 0:
                continue
            seg_stats["S1 词首占用"].append(lu1 - fd1)
            seg_stats["S2 换手间隙"].append(fd2 - lu1)
            seg_stats["S3 词尾占用"].append(lu2 - fd2)
            if p1 and p2:
                wcs.append(lu2 - fd1)
        if wcs:
            stats[(len(l1), len(r1), len(l2), len(r2c))].append(max(wcs))
        for k, s in ((1, s1), (2, s2)):
            for h, part in (("l", l1 if k == 1 else l2), ("r", r1 if k == 1 else r2c)):
                if part:
                    fd, ld, fu, lu = A(r, k, h)
                    spreads[(h, len(part))].append(ld - fd)
                    holds.append((h, len(part), lu - ld))

    print("\n词当量 wc = max_h(S1+S2+S3) (ms) 按结构 (L1+R1 → L2+R2):")
    for key in sorted(stats, key=lambda k: -len(stats[k])):
        v = stats[key]
        print(f"  {key[0]}+{key[1]}→{key[2]}+{key[3]}  n={len(v):3d}  "
              f"med={pct(v,0.5):6.0f}  p25={pct(v,0.25):6.0f}  p75={pct(v,0.75):6.0f}")

    print("\n三段分量 (ms, v2.6):")
    for name in ("S1 词首占用", "S2 换手间隙", "S3 词尾占用"):
        v = seg_stats[name]
        if v:
            print(f"  {name}  n={len(v):3d}  med={pct(v,0.5):5.0f}  p25={pct(v,0.25):5.0f}  "
                  f"p75={pct(v,0.75):5.0f}")

    print("\n击内散布 ld-fd (ms) 按手内键数 (T_SYNC 校准依据, 上限 100):")
    for key in sorted(spreads):
        v = spreads[key]
        print(f"  {'左' if key[0]=='l' else '右'}手{key[1]}键  n={len(v):3d}  "
              f"med={pct(v,0.5):5.0f}  p90={pct(v,0.9):5.0f}  max={max(v):5.0f}")

    # 双手 (both) 相关校验已于 2026-09-07 随 both 采集移除 (README §4.1):
    #   起手异步 / 闸门抬高量的实测校验不再可行 —— 闸门感知合成 (§3.3) 由引擎语义
    #   (全放才输出) 必然导出, 属结构项而非经验校正; 其"被挡手是否在闸门后立即按键"
    #   的吸收度不可测, 合成对该情形取**下界**方向 (只可能低估) —— 记于 README §8。

    hv = [h for _, _, h in holds]
    print(f"\nhold 时长 lu-ld (ms): med={pct(hv,0.5):.0f}  p90={pct(hv,0.9):.0f}  max={max(hv):.0f}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else BASE / "当量数据.tsv"
    main(Path(path))
