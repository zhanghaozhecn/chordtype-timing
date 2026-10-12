#!/usr/bin/env python3
"""
分析-熟练度（只读诊断）—— 序号块稳定期方法（口径移植自姊妹项目串击 `better-keystroke-timing`, 2026-09-06 定）
背景: session = 进程生命周期, 不携带状态信息（练习持久不随坐姿/开关重置, 行数悬殊）
      → 按 trial 全局序号（文件序 = 时间序）分析熟练度, 优于按 session
边界方法 (确定性, 无随机): ok 行按序切等大块 → 每块指标中位 → 3 块滚动中位平滑
  → R = 末 5 块平滑值中位 → 自末向前最早连续满足 ≤R×1.10 的块起 = 稳定期起点
口径（v2.9 混采）:
  **分类型**跑边界（1 击类时间尺度不同）: 1 击 → occ = lu−fd; 2 击 → wc = lu2−fd1;
  少数类样本不足自成边界时按主类稳定起点同截归属（姊妹项目做法, 见 并击公共.stable_by_type）
  2 击类另跑三段 (S1/S2/S3) 各自边界 —— hold 与重定位的熟练曲线可能不同（诊断信息）
用法: python 分析-熟练度.py
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from 并击公共 import BASE, read_tsv, hand_segments, stable_start, stable_by_type

def report(title, indicators):
    print(f"[{title}]")
    for name, vals, note in indicators:
        if not vals:
            print(f"  {name}: 0 行 — {note}")
            continue
        _, msg = stable_start(vals)
        print(f"  {name} (n={len(vals)}, 中位 {np.median(vals):.0f}ms) {note}\n    {msg}")

def main():
    rows = read_tsv(BASE / "当量数据.tsv")
    if not rows:
        print(f"无数据: {BASE / '当量数据.tsv'} (尚未开始采集)")
    for hand, name in (('l', '左手'), ('r', '右手')):
        print(f"\n═══ {name} ═══")
        # 主口径: 分类型稳定期
        st = stable_by_type(rows, hand)
        for t in sorted(st):
            print(f"[{name}·{t}击] method={st[t]['method']} | {st[t]['msg']}")
        # 2 击类: 三段各自边界 (漂移诊断)
        keys = [hand_segments(r, hand) for r in rows if r["error"] == "0"]
        keys = [k for k in keys if k]
        if keys:
            report(f"{name}·2击 三段各自边界",
                   [(n, [k[n] for k in keys], note) for n, note in
                    (("S1", "词首占用"), ("S2", "换手间隙"), ("S3", "词尾占用"),
                     ("wc", "= S1+S2+S3 (该类型边界指标)"))])
    # 可选: 练习模式数据 (热身; 孤立角色）
    drill = read_tsv(BASE / "练习数据.tsv")
    occ = [float(r["lu"]) - float(r["fd"]) for r in drill
           if r["error"] == "0" and float(r["lu"]) > 0]
    if occ:
        report("练习数据 · occ = lu−fd (练习模式, 热身用)",
               [("occ", occ, "练习组合基线")])

if __name__ == "__main__":
    main()
