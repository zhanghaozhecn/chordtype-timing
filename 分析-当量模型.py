#!/usr/bin/env python3
"""
分析-当量模型.py — 并击当量建模与评估（M2 主脚本；评估口径逐条继承 击键测速）

数据口径:
  · 只用**稳定期**数据（分类型序号块边界，`并击公共.stable_by_type`；数据不足则不过滤并告警）
  · 只用 ok 行（错误行不参与训练——README §3.3）
  · **段级 MAD 单侧上围栏剔除**（`并击公共.mad_filter`，按 (角色, 键内键数) 分桶；
    异常只可能偏大）
  · **trial 级划分**：随机流只作用于**试次**（一行=一个试次），段级划分禁用
    （同试次的段共享上下文，段级划分 = 泄漏）；分类型各自 RandomState(2024) 80/20

模型（双模型 + 闸门合成，README §5）:
  · 模型 A: occ 表 —— 预测 occ_h(组合, 角色) = lu−fd（成形占用）。
    **可加结构** (v2, 2026-10-03 用户决策): log occ = 击内本征 base(组合) + 段位效应 offset(角色)
    —— 1 击(iso) 与 2 击(S1/S3) 共享同一组合基数, 段位只差一个近似常数的上下文偏移
    （实测 2026-10-03: iso→S1/S3 慢 11~18ms 两手同号; 组合内段位差 SD ≈ 单元内噪声;
    v1 按角色分家时 51-98/23x 个 (组合,角色) 键样本 <5, 共享后 0/79 ⇒ 直接解"先验主导"瓶颈）。
    实现 = onehot ridge 先验 + 键级中位向先验收缩（与 gap 侧"几何 φ ridge + 收缩"同构;
    键级修正只吸收交互残差, 稀角色自动借用其它角色的样本）
  · 模型 B: gap 表 —— 预测 gap_h(c₁→c₂) = fd₂−lu₁（本征换手间隙；闸门只在合成时施加）
  · 估计器 `shrunk`（默认，小样本稳健）: 键级中位 + 向**结构先验收缩** n/(n+m)（经验贝叶斯）
    —— occ 侧先验 = 可加模型（base+段位）, gap 侧先验 = 几何 φ ridge
  · 估计器 `embed`（数据够时用）: 组合嵌入 + 几何 φ + MLP，固定种子 0..2 全体平均
    （**不做 best-of 选优** —— 选优用验证集才有意义，固定种子平均无选优抽签噪声）
  · 合成（闸门感知，README §4.1）:
      单手表链 = occ(c₁) + gap(c₁→c₂) + occ(c₂)
      双边词 = **max_h 手链**（v2.33 简化: 闸门项已证恒惰性, 2 击词无需计算第二项 —— 
               `实验/实验-分段max合成.py` 全枚举 550 万词 Δ≡0; 守卫条件见 compose_word）

评估（四宫格 + 结构消融，勿改口径）:
  · 段级: occ / gap 的 MAE、R²（留出段）
  · trial 级: 1 击词 occ、2 击词 wc
  · **报 MAE 处一律带 mean 与 nMAE**（2026-10-13 用户「以后报告结果时同时报告 nMAE」;
    nMAE = MAE / mean(实测), **同集同分母**, 唯一实现 `并击公共.nmae`）——
    ⚠ 只读作"误差占该单元平均耗时的比例", 误差含固定底 ⇒ 水平变快时 nMAE 机械上升, **不判模型好坏**
  · 结构消融（M2 必做）: 三段分解合成 vs 直接用键对表预测 wc
  · 所有指标在**留出试次**上算；打印**划分版本**（稳定期规模/测试集/种子）以便追溯
  · torch 单线程 + manual_seed；模型随数据确定性可复现

用法: python 分析-当量模型.py [--hand l|r] [--model shrunk|embed] [--epochs 200]
                              [--full] [--selftest]
      --full: 全数据重训并导出 产物/当量表-并击-{l,r}.npz（**按手分文件**; version 戳；M3 组装层读）
"""
import sys, json, time, argparse, math
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from 并击公共 import (BASE, read_tsv, hand_segments, iso_segment, combo_of,
                     ROLES, pct, stable_by_type, stable_rows, hand_of,
                     mad_filter, LEFT_COMBOS, RIGHT_COMBOS, KEY_POS, mirror_combo,
                     slot_keys, col_pair, row_pair, nmae)

DATA = BASE / "当量数据.tsv"


def out_npz(hand):
    """产物路径 —— **按手分文件**（2026-10-13 用户"产物表改成左右手分开"）
    ⇒ `产物/当量表-并击-l.npz` / `-r.npz`（各自整份 occ+gap 表, meta.hand 标手别）"""
    return BASE / "产物" / f"当量表-并击-{hand}.npz"


OUT_NPZ = out_npz("l")      # 兼容旧引用（= 左手路径）
TEST_FRAC = 0.20
SEED = 2024                 # 固定随机流（划分与初始化；勿改，改了数字不可比）
SHRINK_M = 3.0              # 收缩强度 m: est = (n·键级中位 + m·全局中位)/(n+m)
N_SEEDS = 3                 # 嵌入模型固定种子数（全体平均，无选优）
MIN_SEG_PER_KEY = 5         # 段级样本少于此的键只靠收缩（并告警数据不足）
MODEL_VERSION = 10          # v10: **occ 先验换结构/几何形状**（onehot(组合) → 列形态类别 15 ⊕
                            #   连续几何 3, 见 `occ_struct_feat`; 2026-10-13 用户「进行改进」）。
                            #   依据: 组合级留出（= **未见组合行**, 键位重排评估场景）
                            #   列形态类别 + 连续几何 **两手 24/24 更优 −2.7…−3.2ms**, 而
                            #   **见过组合行打平**（−0.17/+0.04 ns）⇒ 生产报数看不见, 收益全在
                            #   "没采到的组合"上; 同日三族对比（README §5.8）给第 5 个独立旁证
                            #   （XGB(指对+行对+角色) ≈ 线性结构先验, 而 XGB(只身份) ≈ 生产 ⇒
                            #   增益来自**先验形状**而非学习器）。参数数 94 → 33。
                            #   v9 冻结路径: `ShrunkModel(occ_prior="combo")`
                            # v9: φ 增**食指列位 2 维**（两侧序数: 食内 +1 / 食指不参与 0 / 食外 −1;
                            #   8→10 维; 组合级留出 24 轮**两手+两行集都过** l −0.54 [−0.68,−0.39] /
                            #   r −0.22 [−0.29,−0.16]; 同日对照否掉二元/三态/转移9格/连续列质心/
                            #   手指构成/换行交互 ⇒ 必须三档序数; 用户拍板; 依据 memory ④b）;
                            # v8: φ 删列维 |Δ列|/Δ列（系数≈0+几何实验 CI 跨 0, 门禁删后中性偏正;
                            #   同日否决旋转角绝对值; 10→8 维; 用户拍板）;
                            # v7: φ 删「首末同键」（约定代理惰性, 门禁微正, 用户拍板; 11→10 维;
                            #   同日否决: 键重叠细分3格/同指4维 —— 实验-重叠细分与同指.py）;
                            # v6: φ 负载维改**列数对 4 格 onehot** 取代 n1'/n2' (9→11 维;
                            #   Part I/J 消融+bootstrap + 2026-10-11 快照复核两手通过, 用户拍板);
                            # v5: φ 删 2 个惰性特征 (dist/Δn', 11→9 维);
                            # v4: 值围栏 (段时值 MAD 上围栏, 任一段超限弃整行, 对齐姐妹项目);
                            # v3: φ 增负载维 n1'/n2' (3键计2); v2: occ 可加结构; v1: 角色分家

# ── 几何 φ（gap 模型的输入；并击的"重定位"由这些量刻画，README §5 模型 B）──
def _centroid(combo):
    ps = [KEY_POS[c] for c in combo]
    return sum(r for r, _ in ps) / len(ps), sum(c for _, c in ps) / len(ps)

def _load_n(combo):
    """负载 n' (3键计2, 2026-10-03 实证): sdf/lkj 的 gap/occ ≈ 2键"""
    return 2.0 if len(combo) == 3 else float(len(combo))

def _slot_cols(combo):
    """组合各键的**槽位列**（左 col c ↦ 槽 c; 右 col c ↦ 槽 9−c）⇒ 左右手语义相同、镜像一致"""
    right = hand_of(combo) == "r"
    return [9 - KEY_POS[ch][1] if right else KEY_POS[ch][1] for ch in combo]

def _idx_pos(combo):
    """**食指位序数**（v9 新增）: 食内(槽 4) +1 / 食指不参与 0 / 食外(槽 3) −1
    取值唯一: 合法组合里槽 3 与槽 4 不会同现（同指键区约束）—— `selftest` 逐组合断言"""
    cols = set(_slot_cols(combo))
    if 4 in cols:
        return 1.0
    if 3 in cols:
        return -1.0
    return 0.0

def phi_gap_v5(c1, c2):
    """**冻结的 φ v5**（9 维, MODEL_VERSION 5 的生产口径, 2026-10-03~10-11）:
    跨度变化 / 行位移 / 列位移 / 同键重复 / 首末同键 / 负载 n1'·n2' (3键计2) / 常数。
    保留只为复现历史快照与实验对照（实验-gap特征消融.py 的 base8 与此逐位一致）;
    生产已换 φ v6（见 phi_gap）—— 负载由 max 主导、(1,2)≠(2,1), 两条线性列表达不了。"""
    (r1, c1x), (r2, c2x) = _centroid(c1), _centroid(c2)
    dr, dc = r2 - r1, c2x - c1x
    same_key = float(bool(set(c1) & set(c2)))
    first, last = c1[-1], c2[0]                      # canonical 键盘序 (仅用于"首末同键"判定)
    return [abs(dr), abs(dc), dr, dc, same_key, float(first == last),
            _load_n(c1), _load_n(c2), 1.0]

def phi_gap_v6(c1, c2):
    """**冻结的 φ v6**（11 维, MODEL_VERSION 6 的生产口径, 2026-10-11）:
    跨度变化 / 行位移 / 列位移 / 同键重复 / 首末同键 / **列数对 4 格 onehot** / 常数。
    列数对取代 n1'/n2' 的依据: 负载由 max 主导、(1,2)≠(2,1) 不可加（(1,2)=172 vs (2,1)=147）,
    Part J 配对 bootstrap 门禁 l −1.10 / r −0.77 均 11/12, 5252 快照复核
    l −0.70 [−1.13,−0.30] / r −0.24 [−0.40,−0.08]（实验-v6v5对比复核.py）。
    保留只为复现历史快照与实验对照; 生产已换 φ v7 = v6 − 首末同键。"""
    (r1, c1x), (r2, c2x) = _centroid(c1), _centroid(c2)
    dr, dc = r2 - r1, c2x - c1x
    same_key = float(bool(set(c1) & set(c2)))
    first, last = c1[-1], c2[0]                      # canonical 键盘序 (仅用于"首末同键"判定)
    n1, n2 = _load_n(c1), _load_n(c2)
    return [abs(dr), abs(dc), dr, dc, same_key, float(first == last),
            float(n1 == 1 and n2 == 1), float(n1 == 1 and n2 == 2),
            float(n1 == 2 and n2 == 1), float(n1 == 2 and n2 == 2), 1.0]

def phi_gap_v7(c1, c2):
    """**冻结的 φ v7**（10 维, MODEL_VERSION 7 的生产口径, 2026-10-11）:
    v6 − 首末同键。保留只为复现历史快照与实验对照; 生产已换 φ v8 = v7 − 列维。"""
    (r1, c1x), (r2, c2x) = _centroid(c1), _centroid(c2)
    dr, dc = r2 - r1, c2x - c1x
    same_key = float(bool(set(c1) & set(c2)))
    n1, n2 = _load_n(c1), _load_n(c2)
    return [abs(dr), abs(dc), dr, dc, same_key,
            float(n1 == 1 and n2 == 1), float(n1 == 1 and n2 == 2),
            float(n1 == 2 and n2 == 1), float(n1 == 2 and n2 == 2), 1.0]

def phi_gap_v8(c1, c2):
    """**冻结的 φ v8**（8 维, MODEL_VERSION 8 的生产口径, 2026-10-11）:
    **|Δ行| / Δ行 / 键重叠(二元) / 列数对 4 格 onehot** / 常数 = φ v7 − |Δ列| − Δ列。
    删列维依据: ① 系数 ≈0（l −0.9%/+0.9%, r −2.5%/+1.2%; 实验-gap特征系数表.py）;
    ② 实验-几何变化量与gap关系.py: 控制负载+两侧水平几何后**列向位移无净效应**（CI 全跨 0）;
    ③ 实验-删列维与旋转角绝对值.py 门禁: l −0.09 [−0.18,−0.01] / r −0.09 [−0.19,+0.01]
    —— 删后中性偏正, 无副作用。
    **同日已测不采用**: 旋转角绝对值（两侧|rot| 门禁 l +0.03 ns / r −0.20 [−0.40,+0.02] CI 含 0;
    Δrot/Δ|rot| 两手全 ns）—— 与 Part I/J「旋转/行质心 = 内插基」结论一致, 不进口径。
    列数对 4 格 / 键重叠的依据见 phi_gap_v6/v5 注释与 Part I/J。**值围栏的 gap 桶仍按 n1'×n2'**
    （build_samples 本地计算, 不经本函数）。保留只为复现历史快照与实验对照; 生产已换 φ v9。"""
    (r1, c1x), (r2, c2x) = _centroid(c1), _centroid(c2)
    dr, dc = r2 - r1, c2x - c1x
    same_key = float(bool(set(c1) & set(c2)))
    n1, n2 = _load_n(c1), _load_n(c2)
    return [abs(dr), dr, same_key,
            float(n1 == 1 and n2 == 1), float(n1 == 1 and n2 == 2),
            float(n1 == 2 and n2 == 1), float(n1 == 2 and n2 == 2), 1.0]

def phi_gap(c1, c2):
    """手内位移 + **食指列位** (10 维, **φ v9**, MODEL_VERSION 9, 2026-10-12 用户拍板):
    φ v8 的 8 维 + **[食指位(c₁), 食指位(c₂)]**（食内 +1 / 食指不参与 0 / 食外 −1, 槽位序）。
    几何前提 = 每个**非食指手指只对应一列** ⇒ 组合空间里"手要横向挪"只剩食指在槽位 3/4 之间的
    选择; 而 v8 删掉的 `Δ列` 是**质心**列差（主要反映"用了哪些手指", 不是手挪没挪）。
    依据（memory ④b; `实验/实验-指列转移与几何先验.py --part form`, 组合级留出 16/63 × 4 种子 ×
    6 抽 = 24 轮, 未见组合行 / 见过组合行 分报, 配对 bootstrap）: 本形式**两手两行集都过**
    —— l **−0.54 [−0.68,−0.39]** / r **−0.22 [−0.29,−0.16]**（见过行 −0.79 / −0.17）。
    **同日对照（都加在 φ v8 上, 24 轮）**: 三态指示 4 维 −0.45/−0.12（略弱）· 二元"是否用食内列"
    **只过左手**（r −0.02 不可辨）· 转移 9 格 −0.27/−0.01（维度稀释）· 连续列质心水平量
    r **+0.14 更差** · 手指构成（含小/无/中）两手更差 · ×|Δ行| 交互零增量
    ⇒ **必须三档序数, 不能压成二元、不能连续化**。系数 l +0.033/+0.042 · r +0.026/+0.028
    （两手同号, 每单位 ≈ +3%: **食指待在内列 ⇒ 该侧间隙偏长**）。
    ⚠ **trial 单元测不出**（−0.29 [−1.10,+0.59] / −0.11 [−0.62,+0.34]）⇒ 收益集中在**未见/稀组合**;
    ⚠ 与 occ 侧方向**相反**（occ 的连续几何读数是"离小指越远越快" ⇒ 食内偏快, 这里食内偏慢）——
    两段的几何不可共用一个"难度刻度"。"""
    return list(phi_gap_v8(c1, c2)) + [_idx_pos(c1), _idx_pos(c2)]

PHI_DIM = len(phi_gap("a", "b"))


# ── occ 结构先验的特征（**MODEL_VERSION 10**; 2026-10-13 用户「进行改进」）──
# 动机（三族对比 + 几何先验实验, 见 README §5.8 / §5.2-61）: 生产 occ 先验 = **onehot(组合)**
# ⇒ 未见组合（键位重排出的新组合、新方案评估场景）整块哑变量**全 0**, 退化成"全局中位 × 段位因子";
# 换**结构/几何**形状后, 未见组合仍能从"同列形态 / 同行 / 邻近几何"的组合借力。
# 实测（组合级留出 = 未见组合行）: 列形态类别 + 连续几何 一条 **两手 24/24 更优 −2.7…−3.2ms**,
# 而**见过组合行打平**（−0.17/+0.04 ns）⇒ 生产报数看不见, 收益全在"没采到的组合"上兑现。
# 槽位序口径与 并击公共 的 9×7 分类件同源（`slot_keys` 单一来源）: 左 col c ↦ 槽 c, 右 col c ↦ 槽 9−c。
OCC_SHAPES = tuple(sorted({tuple(cc for _, cc in slot_keys(c))
                           for c in LEFT_COMBOS + RIGHT_COMBOS}))   # 15 格 = 单键 5 + 双键 9 + 3键 1
OCC_SHAPE_I = {v: k for k, v in enumerate(OCC_SHAPES)}
OCC_PRIOR_KINDS = ("struct", "combo")     # struct = v10 结构/几何（默认）; combo = v9 onehot(组合) 冻结口径


def _slot_rows(combo):
    return tuple(r for r, _ in slot_keys(combo))


def occ_rot(combo):
    """旋转角 = 槽位序 后键行 − 前键行 ∈ {−1, 0, +1}（合法组合不跨两行）"""
    rs = _slot_rows(combo)
    return float(rs[-1] - rs[0])


def occ_row_centroid(combo):
    """行质心 = 键行均值（0=上 … 2=下）"""
    rs = _slot_rows(combo)
    return sum(rs) / len(rs)


def occ_struct_feat(combo, role):
    """occ 结构先验的输入 = onehot(列形态 15) ⊕ [旋转角, 行质心, |旋转角|] ⊕ onehot(角色)
    （角色在**末位**，与设计阵 `[1.0] + occ_struct_feat(...)` 配套; 列形态必须留在**类别域**
    —— 纯连续几何的"见过组合行"显著更差 +0.16/+0.07, 见 README §5.2-61 与 2026-10-12 ③）"""
    v = [0.0] * (len(OCC_SHAPES) + 3)
    v[OCC_SHAPE_I[tuple(c for _, c in slot_keys(combo))]] = 1.0
    o = len(OCC_SHAPES)
    rot = occ_rot(combo)
    v[o], v[o + 1], v[o + 2] = rot, occ_row_centroid(combo), abs(rot)
    return v + [1.0 if r == role else 0.0 for r in ROLES]


# ═══════════════════════ 数据准备 ═══════════════════════
def build_samples(rows, hand, use_stable=True, mad_k=3.0):
    """→ dict(occ=[(行序,role,组合,占用)], gap=[(行序,c1,c2,间隔)], wc=[(行序,c1,c2,词占用)],
             stable=…, n_ok=…, dropped=…)

    目标量恒为**占用类**: occ = lu−fd / gap = fd₂−lu₁ / wc = lu₂−fd₁。
    质量围栏用**spread**（击内按下散布 = 成形质量）: 散布超限说明该击失同步, 其占用也不可信
    → **整行剔除**（段与试次必须一致, 否则同一试次的段会跨侧）。
    **值围栏 (v4)**: 段时值本身再各做 MAD 单侧上围栏（occ 桶 = 角色×键数, gap 桶 = n1'×n2'）,
    任一段超限同样弃整行 —— 对齐姐妹项目 mad_filter_segments 的"段齐全"语义;
    拦的是散布正常的注意力断档型超长间隙。
    段位角色: 1 击行 → iso; 2 击行 → S1(首击) / S3(词尾)。"""
    ok = [r for r in rows if r.get("error") == "0"]
    stable_msg = "未启用（数据不足，全量）"
    if use_stable and ok:
        n0 = len(ok)
        info = stable_by_type(ok, hand)
        keep, parts = set(), []
        for t, v in sorted(info.items()):
            if not isinstance(v, dict):
                continue
            keep.update(v.get("stable") or [])
            parts.append(f"{t}击 界 {v.get('cut_row') if v.get('cut_row') is not None else '—'}"
                         f"[{v.get('method')}]")
        if keep:
            # **按类型各自截取**（2026-10-12 用户决策）: 旧口径取 min(各类型界) ⇒ 任一类找不到
            # 平台就把**整手**拖成全量池（实测 l 手 2 击界崩到块 1 时, 1 击与 occ 侧本来干净的
            # 界一起作废, 段-occ/gap/1击/2击 全线读的是练习史平均）。
            ok = [r for i, r in enumerate(ok) if i in keep]
            stable_msg = ("分类型稳定期**各自截取**: " + " · ".join(parts)
                          + f"（剩 {len(ok)}/{n0}）")
        else:
            stable_msg = "未启用（分类型边界均未定: " + " · ".join(parts) + "）"
    segs, rows_data = [], {}
    for i, r in enumerate(ok):
        parts = [p for p in r["code"].split("|") if p]
        cs = [combo_of(p, hand) for p in parts]        # canonical 槽位序 (唯一口径; 旧写法容错)
        if len(parts) == 1:                                   # 1 击行 → 孤立角色
            s = iso_segment(r, hand)
            if not s:
                continue
            fd, ld, _, lu = _anchors4(r, 1, hand)
            segs.append((i, "iso", s["combo"], len(s["combo"]), float(s["spread"])))
            rows_data[i] = {"occ": [("iso", s["combo"], float(s["occ"]))], "gap": [], "wc": []}
            continue
        if len(cs) < 2 or not cs[0] or not cs[1]:
            continue
        seg = hand_segments(r, hand)
        if not seg:
            continue
        segs.append((i, "S1", seg["combo1"], len(seg["combo1"]), float(seg["spread1"])))
        segs.append((i, "S3", seg["combo2"], len(seg["combo2"]), float(seg["spread3"])))
        rows_data[i] = {"occ": [("S1", seg["combo1"], float(seg["S1"])),
                                ("S3", seg["combo2"], float(seg["S3"]))],
                        "gap": [(cs[0], cs[1], float(seg["S2"]))],
                        "wc": [(cs[0], cs[1], float(seg["wc"]))]}
    _keep, drop, fences = mad_filter(segs, mad_k)             # 单侧上围栏（桶 = 角色×键数）
    bad = {s[0] for s in drop}
    # 值围栏 (v4, 2026-10-03 用户决策, 对齐姐妹项目 mad_filter_segments 的"段齐全"语义):
    # 段**时值本身**也做 MAD 单侧上围栏 —— 注意力断档型超长间隙 (spread 正常, 漏过散布围栏)
    # 只能靠这层拦。occ 桶 = (角色, 键数); gap 桶 = (n1', n2') 3键计2 (与 φ 同口径);
    # 任一段超限 → 弃整行 (试次内段共享上下文)。实测再弃 ~2% (姐妹项目文献 5-10% 内),
    # 两手 gap MAE 随之对齐 (l 39.2→23.9 / r 24.9→21.0, 左手"MAE 偏大"实为上尾密度差)。
    occ_cells, gap_cells = defaultdict(list), defaultdict(list)
    for i, d in rows_data.items():
        if i in bad:
            continue                                          # 围栏只算散布干净行
        for role, c, v in d["occ"]:
            occ_cells[(role, len(c))].append((i, v))
        for a, b, v in d["gap"]:
            n1 = 2 if len(a) == 3 else len(a)
            n2 = 2 if len(b) == 3 else len(b)
            gap_cells[(n1, n2)].append((i, v))
    for cells in (occ_cells, gap_cells):
        for key, pairs in cells.items():
            vals = [v for _, v in pairs]
            med = pct(vals, 0.5)
            mad = pct(sorted(abs(v - med) for v in vals), 0.5)
            sigma = 1.4826 * mad if mad > 0 else 1.0          # MAD=0 兜底 (姐妹项目同款)
            f = med + mad_k * sigma
            fences[f"值:{key}"] = f
            bad |= {i for i, v in pairs if v >= f}
    occ, gap, wc = [], [], []
    for i, d in rows_data.items():
        if i in bad:
            continue
        for role, c, v in d["occ"]:
            occ.append((i, role, c, v))
        for a, b, v in d["gap"]:
            gap.append((i, a, b, v))
        for a, b, v in d["wc"]:
            wc.append((i, a, b, v))
    return {"occ": occ, "gap": gap, "wc": wc, "stable": stable_msg, "n_ok": len(ok),
            "dropped": len(bad), "n_rows_raw": len(rows_data), "fences": fences, "n_seg": len(segs)}


def _anchors4(r, stroke, hand):
    return tuple(float(r[f"{hand}{p}{stroke}"]) for p in ("fd", "ld", "fu", "lu"))


def split_by_trial(samples, frac=TEST_FRAC, seed=SEED):
    """**trial 级**划分: 随机流只作用于试次序号; 同试次的全部段同侧 (禁止段级划分)"""
    rows_1 = sorted({i for i, role, _, _ in samples["occ"] if role == "iso"})
    rows_2 = sorted({i for i, role, _, _ in samples["occ"] if role in ("S1", "S3")})
    rs = np.random.RandomState(seed)
    test = set()
    for idx in (rows_2, rows_1):                      # 顺序固定: 先 2 击后 1 击 (同姊妹项目)
        perm = rs.permutation(len(idx))
        n_test = int(round(len(idx) * frac))
        test |= {idx[p] for p in perm[:n_test]}
    tr, te = {}, {}
    for key in ("occ", "gap", "wc"):
        tr[key] = [s for s in samples[key] if s[0] not in test]
        te[key] = [s for s in samples[key] if s[0] in test]
    return tr, te, {"n_test_rows": len(test), "n_train_rows": len(set(
        i for key in ("occ", "gap", "wc") for i, *_ in samples[key]) - test), "seed": seed}


# ═══════════════════════ 估计器 ═══════════════════════
class ShrunkModel:
    """键级中位 + **收缩到结构先验**（经验贝叶斯; 小样本稳健, 无需 torch）
    occ 侧先验 = **可加模型** (v2, 2026-10-03 用户决策): log occ(组合,角色) = 击内本征 base(组合)
    + 段位效应 offset(角色) —— 1 击(iso) 与 2 击(S1/S3) 共享组合基数, onehot ridge 拟合。
    依据 (2026-10-03 实测): iso→S1/S3 段位偏移 +11~18ms 两手同号; 组合内段位差 SD (12-16ms)
    ≈ 单元内噪声 (σ_within 13-15ms) ⇒ 一阶可加; 键级中位对先验的偏离只吸收交互残差。
    **occ 先验的形状（v10, 2026-10-13 用户「进行改进」）**: `occ_prior="struct"` = 列形态类别 +
    连续几何（见 `occ_struct_feat`）, 取代 v9 的 onehot(组合) —— 依据是**未见组合行**（键位重排
    评估场景）−2.7…−3.2ms 而见过组合行打平; `occ_prior="combo"` = v9 冻结口径, 只在复现历史读数时用。
    gap 侧特别关键: 键对空间 79² 极稀（900 试次也几乎无重叠键对）, 纯键对中位等于没有
    → 先对 φ 拟合 ridge 得"几何外推预测", 键对样本再向其收缩（README §5 模型 B 的几何路线）"""
    name = "shrunk"

    def __init__(self, lam=1.0, occ_prior=OCC_PRIOR_KINDS[0]):
        assert occ_prior in OCC_PRIOR_KINDS, f"occ_prior 只能是 {OCC_PRIOR_KINDS}"
        self.lam, self.occ_prior = lam, occ_prior
        self.n_par = 0

    def _ridge(self, X, y):
        """岭回归（含截距列）→ w; y 为 log 尺度"""
        X = np.asarray(X, float)
        A = X.T @ X + self.lam * np.eye(X.shape[1])
        return np.linalg.solve(A, X.T @ np.asarray(y, float))

    def _phi_pred(self, c1, c2):
        phi = phi_gap(c1, c2)
        return float(math.exp(float(np.dot(self.w_gap, [1.0] + phi))))

    def fit(self, occ, gap):
        self.g_occ = pct([v for *_, v in occ], 0.5) if occ else 100.0
        self.g_gap = pct([v for *_, v in gap], 0.5) if gap else 150.0
        self.occ_by = defaultdict(list)
        for _, role, c, v in occ:
            self.occ_by[(c, role)].append(v)
        self.gap_by = defaultdict(list)
        for _, c1, c2, v in gap:
            self.gap_by[(c1, c2)].append(v)
        # 几何先验: log(gap) ~ φ（含键数等静态量）; 样本不足时退化为全局中位
        if len(gap) >= PHI_DIM + 2:
            X = [[1.0] + phi_gap(a, b) for _, a, b, _ in gap]
            self.w_gap = self._ridge(X, [math.log(max(v, 1e-3)) for *_, v in gap])
        else:
            self.w_gap = np.array([math.log(self.g_gap)] + [0.0] * PHI_DIM)
        # occ 可加先验: log(occ) ~ 1 + <先验块> + onehot(角色) —— 组合基数跨角色共享;
        # 稀角色借其它角色的样本。样本不足时退化为全局中位。
        # 先验块 = **occ_prior="struct"（v10）列形态类别 ⊕ 连续几何** / "combo"（v9）onehot(组合)。
        # ⚠ 未见组合: struct 仍能借"同列形态/同行/邻近几何"的组合; combo 整块全 0 ⇒ 退化成
        #   全局中位×段位因子。`occ_combos` 保留为"训练集见过的组合"（H._npar 等仍读它）。
        self.occ_combos = sorted({c for _, _, c, _ in occ})
        self.occ_roles = ROLES
        self.occ_blocks = (len(OCC_SHAPES) + 3 if self.occ_prior == "struct"
                           else len(self.occ_combos))
        self.n_par = (1 + self.occ_blocks + len(self.occ_roles)) + (1 + PHI_DIM)
        if len(occ) >= len(self.occ_roles) + 2:
            X = [[1.0] + self._occ_feat(c, r) for _, r, c, _ in occ]
            self.w_occ = self._ridge(X, [math.log(max(v, 1e-3)) for *_, v in occ])
        else:
            self.w_occ = None
        return self

    def _occ_feat(self, combo, role):
        """先验块（角色 onehot 在末位, 由本函数一并给出 ⇒ 设计阵 = [1.0] + 本函数）"""
        if self.occ_prior == "struct":
            return occ_struct_feat(combo, role)
        return ([1.0 if combo == c else 0.0 for c in self.occ_combos]
                + [1.0 if r == role else 0.0 for r in self.occ_roles])

    def _shrink(self, vals, prior):
        if not vals:
            return prior
        n = len(vals)
        return (n * pct(vals, 0.5) + SHRINK_M * prior) / (n + SHRINK_M)

    def _occ_prior(self, combo, role):
        """可加先验 exp(w·x); w_occ=None (样本不足) → 全局中位"""
        if self.w_occ is None:
            return self.g_occ
        return math.exp(float(np.dot(self.w_occ, [1.0] + self._occ_feat(combo, role))))

    def occ(self, combo, role):
        return self._shrink(self.occ_by.get((combo, role), []), self._occ_prior(combo, role))

    def gap(self, c1, c2):
        return self._shrink(self.gap_by.get((c1, c2), []), self._phi_pred(c1, c2))


class EmbedModel:
    """组合嵌入 + 几何 φ + MLP —— **残差形态**: 只学"相对几何先验的对数残差",
    预测 = 先验 × exp(网络输出)。这样起点即先验（初始化近零）, 小样本下不会比先验更差,
    大样本时再超越它（直接学绝对值在小数据上会输给先验——合成自测实测过）。
    torch 单线程 + 固定种子 0..N-1 全体平均; **不做 best-of 选优**（无选优抽签噪声）"""
    name = "embed"

    def __init__(self, combos, epochs=200, seeds=N_SEEDS, prior=None):
        self.combos = list(combos)
        self.cidx = {c: k for k, c in enumerate(self.combos)}
        self.epochs, self.seeds = epochs, seeds
        self.prior = prior if prior is not None else ShrunkModel()
        self.net_occ, self.net_gap = [], []

    def _tensors(self, occ, gap):
        import torch
        def oi(role):
            return ["iso", "S1", "S3"].index(role)
        Xo = torch.tensor([[self.cidx.get(c, 0), oi(role)] for _, role, c, _ in occ], dtype=torch.long)
        yo = torch.tensor([math.log(max(v, 1e-3)) - math.log(max(self.prior.occ(c, role), 1e-3))
                           for _, role, c, v in occ], dtype=torch.float32)   # 相对先验的残差
        Xg_i = torch.tensor([[self.cidx.get(a, 0), self.cidx.get(b, 0)] for _, a, b, _ in gap],
                            dtype=torch.long)
        Xg_p = torch.tensor([phi_gap(a, b) for _, a, b, _ in gap], dtype=torch.float32)
        yg = torch.tensor([math.log(max(v, 1e-3)) - math.log(max(self.prior.gap(a, b), 1e-3))
                           for _, a, b, v in gap], dtype=torch.float32)      # 相对先验的残差
        return Xo, yo, Xg_i, Xg_p, yg

    def fit(self, occ, gap, val=None):
        import torch
        torch.set_num_threads(1)
        Xo, yo, Xg_i, Xg_p, yg = self._tensors(occ, gap)
        for s in range(self.seeds):               # 种子只在这里设, 训练函数内不再重置
            self.net_occ.append(self._train_occ(Xo, yo, s))
            self.net_gap.append(self._train_gap(Xg_i, Xg_p, yg, s))
        return self

    def _train_occ(self, X, y, seed=0):
        import torch
        torch.manual_seed(seed)
        m = torch.nn.Sequential(torch.nn.Embedding(len(self.combos), 8),
                                torch.nn.Linear(8 + 3, 32), torch.nn.ReLU(),
                                torch.nn.Linear(32, 1))
        opt = torch.optim.Adam(m.parameters(), lr=0.01)
        embs = torch.nn.functional.one_hot(X[:, 1], 3).float()
        for _ in range(self.epochs):
            opt.zero_grad()
            h = m[2](m[1](torch.cat([m[0](X[:, 0]), embs], 1)))
            pred = m[3](h).squeeze(1)
            loss = ((pred - y) ** 2).mean()
            loss.backward()
            opt.step()
        return m

    def _train_gap(self, Xi, Xp, y, seed=0):
        import torch
        torch.manual_seed(seed)
        m = torch.nn.Sequential(torch.nn.Linear(8 + 8 + PHI_DIM, 32), torch.nn.ReLU(),
                                torch.nn.Linear(32, 1))
        emb = torch.nn.Embedding(len(self.combos), 8)
        opt = torch.optim.Adam(list(m.parameters()) + list(emb.parameters()), lr=0.01)
        for _ in range(self.epochs):
            opt.zero_grad()
            e = torch.cat([emb(Xi[:, 0]), emb(Xi[:, 1]), Xp], 1)
            pred = m(e).squeeze(1)
            loss = ((pred - y) ** 2).mean()
            loss.backward()
            opt.step()
        return m, emb

    def occ(self, combo, role):
        import torch
        k = self.cidx.get(combo)
        if k is None:
            return self.g_occ
        role_i = ["iso", "S1", "S3"].index(role)
        with torch.no_grad():
            vals = []
            for m in self.net_occ:
                e = torch.nn.functional.one_hot(torch.tensor([role_i]), 3).float()
                h = m[2](m[1](torch.cat([m[0](torch.tensor([k])), e], 1)))
                vals.append(float(m[3](h)))
        return self.prior.occ(combo, role) * math.exp(sum(vals) / len(vals))

    def gap(self, c1, c2):
        import torch
        a, b = self.cidx.get(c1), self.cidx.get(c2)
        if a is None or b is None:
            return self.g_gap
        xi = torch.tensor([[a, b]], dtype=torch.long)
        xp = torch.tensor([phi_gap(c1, c2)], dtype=torch.float32)
        with torch.no_grad():
            vals = []
            for m, emb in self.net_gap:
                vals.append(float(m(torch.cat([emb(xi[:, 0]), emb(xi[:, 1]), xp], 1))))
        return self.prior.gap(c1, c2) * math.exp(sum(vals) / len(vals))


# ═══════════════════════ 合成与评估 ═══════════════════════
def compose_single_hand(model, c1, c2):
    """单手表链 = occ(c₁@S1) + gap + occ(c₂@S3)（本机数据即单手, 故这条可直接验证）"""
    return model.occ(c1, "S1") + model.gap(c1, c2) + model.occ(c2, "S3")


def compose_word(mdls, strokes):
    """双边词当量 —— **按手取表**（左右手组合字符串不同, 单一表查不到对侧 ⇒ M3 必须传两表）
    mdls = {"l": 左表, "r": 右表}; strokes = [(左组合, 右组合), …]（空串 = 该手此击不参与）

    **2 击词 (v2.33 简化, 2026-10-04 用户决策)**: 词当量 = **max_h ( S1_h + gap_h + S3_h )**
    —— "逐段取最大再合成"与"整体取最大"在实测表上**恒等**, 闸门项无需计算。
    依据 (`实验/实验-分段max合成.py`): 闸门阻塞项 G = max_h S1_h + max_h S3_h 恒被本征间隙吸收 ——
    真实词组合全枚举 **550 万词 Δ = max(0, G − max_h chain_h)
    恒为 0** (二字词 5,035,536 个 0 命中, 最险词余量 48.7ms; 三级字最紧 16.4ms;
    bootstrap 重采样重训 60 轮 0 翻转)。闭式: Δ = max(0, min(S1_A − S1_B − gap_B, S3_B − S3_A − gap_A)),
    A/B = S1/S3 支配手 —— 为正要跨过**另一只手的本征间隙** (跨手段差 ~50-70ms < 间隙 ~63-170ms)。
    ⚠ **守卫**: 上式为 0 是**数据结论**: 若表变化使其可为正 (3 键组合进方案 / 某手系统性更慢 /
    某格 gap 变小), 重跑 `实验/实验-分段max合成.py --part 3`, 出现 Δ>0 即须恢复闸门项。

    n ≥ 3 击: 角色词汇只有 iso/S1/S3 (**中段角色未测**), 逐击 max-plus 传播的口径因此未定 ⇒
    当前直接拒绝（避免给出貌似合理的错值; README §4.1 推广条 + §6.2 开放问题）。"""
    if len(strokes) >= 3:
        raise NotImplementedError(
            "n≥3 击词口径未定: 中段击的角色偏移未测 (只有 iso/S1/S3 三角色) — 需先定中段口径")
    chains = {}
    for h in "lr":
        cs = [c for c in ((a if h == "l" else b) for a, b in strokes) if c]
        if not cs:
            chains[h] = 0.0
        elif len(cs) == 1:
            # 只参与一击的手: 角色由**它参与的那一击在词中的位置**决定 (首击 S1 / 末击 S3)
            first = bool(strokes[0][0] if h == "l" else strokes[0][1])
            chains[h] = mdls[h].occ(cs[0], "iso" if len(strokes) == 1 else ("S1" if first else "S3"))
        else:
            chains[h] = (mdls[h].occ(cs[0], "S1") + mdls[h].gap(cs[0], cs[1])
                         + mdls[h].occ(cs[1], "S3"))
    return max(chains.values())


def metrics(y, p):
    """单元误差三件套 + 偏差/R²。**mean / MAE / nMAE 同集同分母**（`并击公共.nmae` 唯一实现;
    2026-10-13 用户「以后报告结果时同时报告 nMAE」⇒ 报 MAE 处一律带 mean 与 nMAE）。
    ⚠ nMAE 只读作"误差占该单元平均耗时的比例",**不可用来判模型有没有变好**（误差含固定底,
    水平变快时 nMAE 机械上升 —— 姊妹项目 README §5.1 实测）。"""
    y, p = np.asarray(y, float), np.asarray(p, float)
    if len(y) == 0:
        return dict(n=0, mean=float("nan"), mae=float("nan"), nmae=float("nan"),
                    bias=float("nan"), r2=float("nan"))
    mae = float(np.abs(y - p).mean())
    bias = float((p - y).mean())
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(((y - p) ** 2).sum()) / sst if sst > 0 else float("nan")
    return dict(n=len(y), mean=float(y.mean()), mae=mae, nmae=nmae(y, p), bias=bias, r2=r2)


def evaluate(model, tr, te):
    """四宫格 + 结构消融；全部在**留出试次**上算；基线 = 训练侧全局中位（各单元用自己的量）"""
    out = {}
    base = {"occ": pct([v for *_, v in tr["occ"]], 0.5) if tr["occ"] else 100.0,
            "gap": pct([v for *_, v in tr["gap"]], 0.5) if tr["gap"] else 150.0,
            "wc": pct([v for *_, v in tr["wc"]], 0.5) if tr["wc"] else 400.0}
    # ① 段级 occ ② 段级 gap
    out["occ_seg"] = metrics([v for *_, v in te["occ"]],
                             [model.occ(c, role) for _, role, c, _ in te["occ"]])
    out["gap_seg"] = metrics([v for *_, v in te["gap"]],
                             [model.gap(a, b) for _, a, b, _ in te["gap"]])
    # ③ trial 级 1 击词（孤立占用） ④ trial 级 2 击词（三段合成）
    one = [(c, v) for _, role, c, v in te["occ"] if role == "iso"]
    out["one_trial"] = metrics([v for _, v in one], [model.occ(c, "iso") for c, _ in one])
    out["two_trial"] = metrics([v for *_, v in te["wc"]],
                               [compose_single_hand(model, a, b) for _, a, b, _ in te["wc"]])
    # 基线（同单元同量）
    out["base_occ"] = metrics([v for *_, v in te["occ"]], [base["occ"]] * len(te["occ"]))
    out["base_gap"] = metrics([v for *_, v in te["gap"]], [base["gap"]] * len(te["gap"]))
    out["base_one"] = metrics([v for _, v in one], [base["occ"]] * len(one))
    out["base_wc"] = metrics([v for *_, v in te["wc"]], [base["wc"]] * len(te["wc"]))
    # 结构消融: 三段分解 vs **直接用键对表预测 wc**（同数据、同划分；键对表同样收缩到中位）
    class _Direct:
        def __init__(self, tr, base_wc):
            self.b = defaultdict(list)
            for _, a, b, v in tr["wc"]:
                self.b[(a, b)].append(v)
            self.g = base_wc
        def predict(self, a, b):
            v = self.b.get((a, b), [])
            return (len(v) * pct(v, 0.5) + SHRINK_M * self.g) / (len(v) + SHRINK_M) if v else self.g
    direct = _Direct(tr, base["wc"])
    out["wc_direct"] = metrics([v for *_, v in te["wc"]],
                               [direct.predict(a, b) for _, a, b, _ in te["wc"]])
    return out


def report(hand, model, split_msg, out, samples):
    print(f"\n═══ {hand}手 · 模型 {model.name} ═══")
    print(f"数据: ok 试次 {samples['n_ok']} | {samples['stable']} | "
          f"围栏(散布+值)剔除整行 {samples['dropped']}/{samples['n_rows_raw']} 行 "
          f"({100*samples['dropped']/max(1,samples['n_rows_raw']):.0f}%)")
    print(f"划分版本: 训练试次 {split_msg['n_train_rows']} / 留出试次 {split_msg['n_test_rows']} "
          f"({TEST_FRAC:.0%}), 种子 {split_msg['seed']} — **trial 级**（段级划分禁用）")
    print(f"留出段数: occ {out['occ_seg']['n']} / gap {out['gap_seg']['n']} / "
          f"1击词 {out['one_trial']['n']} / 2击词 {out['two_trial']['n']}")
    print(f"\n{'单元':>10} {'n':>5} {'mean':>7} {'MAE':>7} {'nMAE':>7} {'偏差':>7} {'R²':>7}   "
          f"基线 MAE / 相对改善")
    for k, bk, label in (("occ_seg", "base_occ", "段-occ"), ("gap_seg", "base_gap", "段-gap"),
                         ("one_trial", "base_one", "试次-1击"), ("two_trial", "base_wc", "试次-2击")):
        m, b = out[k], out[bk]
        gain = (1 - m["mae"] / b["mae"]) * 100 if b["mae"] else float("nan")
        print(f"{label:>10} {m['n']:>5} {m['mean']:>7.1f} {m['mae']:>7.1f} "
              f"{m['nmae']*100:>6.2f}% {m['bias']:>+7.1f} {m['r2']:>7.3f}   "
              f"{b['mae']:>7.1f} / {gain:>+5.1f}%")
    print("  （nMAE = MAE / mean(实测, 同集同分母); ⚠ 只读作「误差占该单元平均耗时的比例」"
          "—— 误差含固定底, 水平变快时 nMAE 会机械上升, 别拿它判模型好坏）")
    print(f"\n结构消融（M2 必做; 三段分解是否为净收益）:")
    print(f"  三段合成 wc  mean {out['two_trial']['mean']:.1f}  MAE {out['two_trial']['mae']:.1f}  "
          f"nMAE {out['two_trial']['nmae']*100:.2f}%  R² {out['two_trial']['r2']:.3f}")
    print(f"  直接键对 wc  mean {out['wc_direct']['mean']:.1f}  MAE {out['wc_direct']['mae']:.1f}  "
          f"nMAE {out['wc_direct']['nmae']*100:.2f}%  R² {out['wc_direct']['r2']:.3f}"
          f"  → 分解{'有' if out['two_trial']['mae'] < out['wc_direct']['mae'] else '无'}"
          f"净收益（差 {out['wc_direct']['mae']-out['two_trial']['mae']:+.1f}ms）")


# ═══════════════════════ 导出 ═══════════════════════
def export(model, hand, out_path=None):
    """产物: occ 表 (角色×组合) + gap 表 (组合×组合) + 版本戳（M3 组装层读）
    **按手分文件**（out_path=None ⇒ `产物/当量表-并击-{hand}.npz`）"""
    out_path = Path(out_path) if out_path is not None else out_npz(hand)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    combos = LEFT_COMBOS if hand == "l" else RIGHT_COMBOS
    occ = np.array([[model.occ(c, role) for c in combos] for role in ROLES], dtype=np.float64)
    gap = np.array([[model.gap(a, b) for b in combos] for a in combos], dtype=np.float64)
    meta = {"hand": hand, "model": model.name, "n_combos": len(combos),
            "roles": list(ROLES), "phi_dim": PHI_DIM, "shrink_m": SHRINK_M,
            "occ_prior": getattr(model, "occ_prior", None),
            "note": "occ = lu−fd (成形占用; 可加结构: log occ = base(组合)+offset(角色), "
                    "iso 与 S1/S3 共享基数; v10 起 base 的形状 = 列形态类别 ⊕ 连续几何 ―― "
                    "未采到的组合也能外推); gap = fd₂−lu₁ (本征换手间隙, 闸门只在合成时施加)"}
    np.savez(out_path, version=np.int64(MODEL_VERSION), combos=np.array(combos),
             occ=occ, gap=gap, meta=json.dumps(meta, ensure_ascii=False))
    print(f"\n导出 → {out_path} (version {MODEL_VERSION}, {len(combos)} 组合, "
          f"occ {occ.shape}, gap {gap.shape})")
    return out_path


# ═══════════════════════ 合成自测 ═══════════════════════
def _synth_occ_true(c, role):
    """合成真值: **恰为可加结构** base(组合形状) + offset(角色) + 小的组合特异抖动 — 检验可加模型能否还原
    ⚠ v10 起 occ 先验本身是**结构/几何**形状 ⇒ 真值必须**结构可表**: 旧版"每组合随机 extra"
    （`6·(ord 和 % 7)`）只有 onehot(组合) 能吃, 换结构先验后不可表, 自测会变成测"先验的容量"而不是
    "可加性与基数共享"。这里保留一个 **±8ms 的结构外抖动**（= 真值里模型无论如何学不到的部分,
    用来把"能借结构"与"能背组合"区分开）。"""
    base = (80.0 + 18.0 * (len(c) - 1) + 9.0 * occ_rot(c)
            + 6.0 * (occ_row_centroid(c) - 1.0)
            + 22.0 * (1.0 if OCC_SHAPE_I[tuple(cc for _, cc in slot_keys(c))] % 3 == 0 else 0.0))
    jitter = 4.0 * ((sum(ord(x) for x in c) % 5) - 2)
    return base + jitter + {"iso": -12.0, "S1": 0.0, "S3": 8.0}[role]


def _synth_gap_true(c1, c2):
    phi = phi_gap(c1, c2)
    return 120.0 + 40.0 * phi[0] + 10.0 * phi[7]     # |dr| + n2' (负载)


def _synth_rows(n_two, n_one, sigma=15.0, seed=5, n_one_only=12):
    """合成数据: occ/gap 带已知组合级结构 (几何可解释) + 噪声 → 检验管线能否还原。
    其中 n_one_only 个组合**只出现在 1 击行** —— 检验可加模型的基数共享:
    这些组合的 S1/S3 没有任何直采样本, 只能靠 base(组合) 借 iso 数据 + 段位偏移推出。"""
    import random
    rng = random.Random(seed)
    pool = list(LEFT_COMBOS)
    one_only = set(rng.sample(pool, n_one_only))
    two_pool = [c for c in pool if c not in one_only]
    rows = []
    def row(code, fd1, ld1, lu1, fd2=None, ld2=None, lu2=None):
        r = {"code": code, "error": "0", "session": "syn", "trial": "0",
             "lfd1": f"{fd1:.1f}", "lld1": f"{ld1:.1f}", "lfu1": f"{lu1:.1f}", "llu1": f"{lu1:.1f}"}
        for k in ("lfd2", "lld2", "lfu2", "llu2"):
            r[k] = "0.0"
        if fd2 is not None:
            r.update({"lfd2": f"{fd2:.1f}", "lld2": f"{ld2:.1f}", "lfu2": f"{lu2:.1f}", "llu2": f"{lu2:.1f}"})
        for h in "r":
            for p in ("fd", "ld", "fu", "lu"):
                for s in (1, 2):
                    r.setdefault(f"{h}{p}{s}", "0.0")
        rows.append(r)
    for _ in range(n_two):
        c1, c2 = rng.choice(two_pool), rng.choice(two_pool)
        o1 = _synth_occ_true(c1, "S1") + sigma * rng.gauss(0, 1) * 0.35
        gp = _synth_gap_true(c1, c2) + sigma * rng.gauss(0, 1)
        o2 = _synth_occ_true(c2, "S3") + sigma * rng.gauss(0, 1) * 0.35
        row(f"{c1}|{c2}", 0.0, abs(rng.gauss(6, 3)), o1, o1 + max(20, gp), o1 + max(20, gp) + 6,
            o1 + max(20, gp) + o2)
    for _ in range(n_one):
        c = rng.choice(pool)
        row(c, 0.0, abs(rng.gauss(6, 3)), _synth_occ_true(c, "iso") + sigma * rng.gauss(0, 1) * 0.35)
    return rows, one_only


def selftest(args):
    print("═══ 合成自测（已知真值 → 检验管线能否还原）═══")
    rows, one_only = _synth_rows(n_two=900, n_one=600)
    s = build_samples(rows, "l", use_stable=False)
    print(f"合成: ok 试次 {s['n_ok']}, occ 段 {len(s['occ'])}, gap 段 {len(s['gap'])}, "
          f"散布围栏剔除整行 {s['dropped']} 行 (段级围栏 {len(s['fences'])} 个桶); "
          f"只出现在 1 击行的组合 {len(one_only)} 个")
    tr, te, msg = split_by_trial(s)
    # (0) φ v9 自检: 维数 = 冻结 v8 + 2 / 前 8 维与 v8 **逐位一致** / 食指位镜像一致且三态齐全 /
    #     无"同指双列"（槽 3 与槽 4 同现会让 _idx_pos 取值不唯一）
    assert PHI_DIM == len(phi_gap_v8("a", "b")) + 2 == 10, PHI_DIM
    for a, b in (("we", "sd"), ("rt", "tf"), ("zx", "sdf"), ("q", "hj"), ("sdf", "lkj")):
        assert list(phi_gap(a, b))[:8] == list(phi_gap_v8(a, b)), f"v9 前 8 维 ≠ 冻结 v8: {a}→{b}"
    for h, combos in (("l", LEFT_COMBOS), ("r", RIGHT_COMBOS)):
        for c in combos:
            cols = set(_slot_cols(c))
            assert not (3 in cols and 4 in cols), f"{c}: 槽 3/4 同现（同指键区约束被违反）"
            assert _idx_pos(c) == _idx_pos(mirror_combo(c)), f"食指位镜像不一致: {c}"
    assert {_idx_pos(c) for c in LEFT_COMBOS} == {-1.0, 0.0, 1.0}, "食指位三态不全"
    print(f"  ✓ φ v9（{PHI_DIM} 维 = 冻结 v8 的 8 维 + 两侧食指位）: 前 8 维逐位一致 · "
          f"食指位镜像一致 · 三态齐全 · 无同指双列")
    # (0b) **occ 结构先验（v10）** 自检:
    #  ① 列形态格数 = 15（单键 5 + 双键 9 + 3键 1）且 79 组合全落在表内
    #  ② 与 **并击公共 的 9×7 分类件**对账: 列形态 = `col_pair`、行 = `row_pair`（同一槽位序口径）
    #  ③ (列形态, 旋转角, 行质心) ↔ (列对, 行对) 是一一对应（⇒ 结构件不丢信息、不撞格）
    #  ④ 镜像一致（右手同一格、旋转角/行质心逐位相同）
    #  ⑤ 未见组合**不退化成常数**（把某组合的独有列形态整格删空后再预测, 值仍随形状/行变化）
    assert len(OCC_SHAPES) == 15 and len(OCC_SHAPE_I) == 15, len(OCC_SHAPES)
    for hand_, combos_ in (("l", LEFT_COMBOS), ("r", RIGHT_COMBOS)):
        for c in combos_:
            shp = tuple(cc for _, cc in slot_keys(c))
            assert shp in OCC_SHAPE_I, f"{c} 的列形态落在表外"
            assert occ_rot(c) == occ_rot(mirror_combo(c)), f"旋转角镜像不一致: {c}"
            assert occ_row_centroid(c) == occ_row_centroid(mirror_combo(c)), f"行质心不一致: {c}"
            if len(c) == 2:
                assert shp == col_pair(c) and _slot_rows(c) == row_pair(c), f"分类件对不上: {c}"
    dbl_l = [c for c in LEFT_COMBOS if len(c) == 2]
    assert len({(tuple(cc for _, cc in slot_keys(c)), occ_rot(c), occ_row_centroid(c))
                for c in dbl_l}) == 63, "结构件撞格"
    assert {len(tuple(cc for _, cc in slot_keys(c))) for c in LEFT_COMBOS + RIGHT_COMBOS} == {1, 2, 3}
    assert ShrunkModel.__init__.__defaults__[1] == "struct", "v10 默认应为结构先验"
    n_occ = 1 + len(OCC_SHAPES) + 3 + len(ROLES)        # 截距 + 列形态 15 + 几何 3 + 角色 3
    print(f"  ✓ occ 结构先验（v10）: 列形态 {len(OCC_SHAPES)} 格（单键 5 + 双键 9 + 3键 1）· "
          f"与 9×7 分类件对账（col_pair/row_pair）· 63 双键 (列形态,旋转角,行质心) 一一对应 · "
          f"镜像一致 · occ 设计 {n_occ} 列（旧 onehot(组合) 口径 = {1 + len(LEFT_COMBOS) + len(ROLES)}）")
    # (0c) **gap 侧不受 occ_prior 影响**（同划分同数据 ⇒ 两模型 gap 表逐位相同）
    _g1 = ShrunkModel(occ_prior="struct").fit(tr["occ"], tr["gap"])
    _g2 = ShrunkModel(occ_prior="combo").fit(tr["occ"], tr["gap"])
    for _, a, b, _ in tr["gap"][:500]:
        assert abs(_g1.gap(a, b) - _g2.gap(a, b)) < 1e-12, f"gap 随 occ_prior 变了: {a}→{b}"
    assert _g1.n_par == n_occ + 1 + PHI_DIM
    assert _g2.n_par == (1 + len(_g2.occ_combos) + 3) + 1 + PHI_DIM
    print(f"  ✓ 接线: gap 表与 occ_prior 无关（两口径逐位相同）· 自报参数 {_g1.n_par} / {_g2.n_par}")
    # (1) 划分是 trial 级: 同一试次的段不得跨侧
    tr_rows = {i for key in ("occ", "gap", "wc") for i, *_ in tr[key]}
    te_rows = {i for key in ("occ", "gap", "wc") for i, *_ in te[key]}
    assert not (tr_rows & te_rows), f"段级泄漏: {len(tr_rows & te_rows)} 个试次跨侧"
    print(f"  ✓ trial 级划分: 训练 {len(tr_rows)} / 留出 {len(te_rows)} 试次, 无跨侧试次")
    for mname in ("shrunk", "embed"):
        if mname == "shrunk":
            model = ShrunkModel()
        else:
            model = EmbedModel(LEFT_COMBOS, epochs=args.epochs, prior=ShrunkModel().fit(tr["occ"], tr["gap"]))
        model.fit(tr["occ"], tr["gap"])
        out = evaluate(model, tr, te)
        report("l", model, msg, out, s)
        if mname == "shrunk":
            # (2) 还原能力: 段级 occ/gap 明显优于全局中位基线
            assert out["occ_seg"]["mae"] < 0.75 * out["base_occ"]["mae"], out["occ_seg"]
            assert out["two_trial"]["mae"] < 0.85 * out["base_wc"]["mae"], out["two_trial"]
            # (3) 段级 MAE 应接近不可约噪声 0.8×σ_stroke (occ 侧噪声 0.35σ)
            assert out["gap_seg"]["mae"] < 1.2 * 0.8 * 15.0, out["gap_seg"]
            print(f"  ✓ 还原: occ 段 MAE {out['occ_seg']['mae']:.1f} (基线 "
                  f"{out['base_occ']['mae']:.1f}) | wc MAE {out['two_trial']['mae']:.1f} "
                  f"(基线 {out['base_wc']['mae']:.1f})")
            # (3b) **nMAE 口径自检**（2026-10-13 用户「以后报告结果时同时报告 nMAE」）:
            #      必须恒等于 MAE / mean(同集) —— 守住"同集同分母"与接线（并击公共.nmae 唯一实现）
            for _k in ("occ_seg", "gap_seg", "one_trial", "two_trial", "wc_direct"):
                _d = out[_k]
                assert abs(_d["nmae"] - _d["mae"] / _d["mean"]) < 1e-12, (_k, _d)
            print("  ✓ nMAE 口径自检: 5 个单元均 ≡ MAE / mean(同集); "
                  + " / ".join(f"{k} {out[k]['nmae']*100:.2f}%"
                               for k in ("occ_seg", "gap_seg", "one_trial", "two_trial")))
            # (2b) **基数共享**: 只出现在 1 击行的组合, 其 S1/S3 没有直采样本,
            # 只能靠 base(组合) 借 iso 数据 + 段位偏移推出 —— v1 角色分家时这里 = 全局中位
            errs = {}
            for role in ("iso", "S1", "S3"):
                e = [abs(model.occ(c, role) - _synth_occ_true(c, role)) for c in one_only]
                errs[role] = (float(np.median(e)), float(np.max(e)))
            assert errs["S1"][0] < 10 and errs["S3"][0] < 10 and errs["iso"][0] < 10, errs
            assert max(errs[r][1] for r in errs) < 25, errs
            print(f"  ✓ 基数共享: {len(one_only)} 个 1击-only 组合的段预测误差 "
                  f"iso med {errs['iso'][0]:.1f} / S1 med {errs['S1'][0]:.1f} / "
                  f"S3 med {errs['S3'][0]:.1f} ms (max {max(errs[r][1] for r in errs):.1f})")
        else:
            assert out["gap_seg"]["mae"] < 1.35 * 0.8 * 15.0, out["gap_seg"]   # 嵌入模型略宽
            print(f"  ✓ 嵌入模型跑通: occ 段 MAE {out['occ_seg']['mae']:.1f}, "
                  f"gap 段 MAE {out['gap_seg']['mae']:.1f}")
    # (4) 导出/读回
    tmp = BASE / "产物" / "_selftest.npz"
    export(ShrunkModel().fit(tr["occ"], tr["gap"]), "l", tmp)
    with np.load(tmp, allow_pickle=False) as z:      # NpzFile 惰性读, 必须关闭后才能删文件
        assert int(z["version"]) == MODEL_VERSION and z["occ"].shape[0] == len(ROLES)
        assert z["occ"].shape[1] == z["gap"].shape[0] == z["gap"].shape[1]
        assert json.loads(str(z["meta"]))["hand"] == "l"
    tmp.unlink()
    print("  ✓ 导出/读回: version / occ(角色×组合) / gap(组合²) / meta 完整")
    _selftest_compose()
    print("合成自测通过: trial 级划分无泄漏 / 可加 occ 还原(含 1击-only 组合的基数共享) / "
          "四宫格与消融 / 导出格式 / 双边词合成 (2 击 = max_h 手链)")


def _selftest_compose():
    """双边词合成口径自测 (v2.33: 2 击 = max_h 手链; 只参与一击的手按位置取 S1/S3 角色)"""
    class _T:
        """duck-typed 表: occ/gap 由字典给定（不依赖训练, 只验合成口径）"""
        def __init__(self, occ, gap):
            self.o, self.g = occ, gap
        def occ(self, c, role):
            return self.o[(c, role)]
        def gap(self, a, b):
            return self.g[(a, b)]
    L = _T({("ab", "S1"): 100.0, ("ab", "S3"): 110.0, ("c", "S3"): 50.0, ("c", "S1"): 40.0,
            ("ab", "iso"): 95.0, ("c", "iso"): 45.0}, {("ab", "ab"): 60.0})
    R = _T({("xy", "S1"): 90.0, ("xy", "S3"): 200.0, ("xy", "iso"): 85.0},
           {("xy", "xy"): 70.0})
    mdls = {"l": L, "r": R}
    # (a) 2 击双边词 = max_h 手链（左 100+60+110=270 / 右 90+70+200=360）—— 闸门项不再相加
    assert compose_word(mdls, [("ab", "xy"), ("ab", "xy")]) == 360.0
    # (b) 闸门项若存在本会是 max S1 + max S3 = 100+200 = 300 < 360 ⇒ 两种写法同值（数据上恒如此）
    assert max(100.0, 90.0) + max(110.0, 200.0) == 300.0
    # (c) 一击词 = 该手孤立占用; 只参与**第 2 击**的手取 S3 角色（旧实现误取 S1）
    assert compose_word(mdls, [("ab", "xy")]) == max(95.0, 85.0)
    assert compose_word(mdls, [("ab", "xy"), ("", "xy")]) == max(
        100.0, 90.0 + 70.0 + 200.0)                      # 左手只参与首击 ⇒ S1 角色
    assert compose_word(mdls, [("c", "")]) == 45.0        # 单手一击词 = iso
    assert compose_word(mdls, [("", "xy"), ("ab", "")]) == max(110.0, 90.0)   # 左手只参与第 2 击 ⇒ S3
    # (d) n≥3 击口径未定 ⇒ 明确拒绝（不给貌似合理的错值）
    try:
        compose_word(mdls, [("c", "xy"), ("ab", "xy"), ("ab", "xy")])
        raise AssertionError("n≥3 击应拒绝")
    except NotImplementedError:
        pass
    print("  ✓ 双边词合成: 2 击 = max_h 手链 / 单参与手按位置取 S1·S3 / iso / n≥3 明确拒绝")


# ═══════════════════════ 主流程 ═══════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", choices=["l", "r"], default="l")
    ap.add_argument("--model", choices=["shrunk", "embed"], default="shrunk")
    ap.add_argument("--occ-prior", choices=list(OCC_PRIOR_KINDS), default=OCC_PRIOR_KINDS[0],
                    help="occ 先验形状: struct = v10 默认（列形态+几何）/ combo = v9 冻结口径")
    ap.add_argument("--epochs", type=int, default=200)
    ap.add_argument("--full", action="store_true", help="全数据重训 + 导出产物 npz")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest(args)
        return

    rows = read_tsv(DATA)
    if not rows:
        print(f"无数据: {DATA} (尚未开始采集)")
        return
    t0 = time.time()
    s = build_samples(rows, args.hand)
    tr, te, msg = split_by_trial(s)
    model = (ShrunkModel(occ_prior=args.occ_prior) if args.model == "shrunk"
             else EmbedModel(LEFT_COMBOS if args.hand == "l" else RIGHT_COMBOS, epochs=args.epochs,
                             prior=ShrunkModel(occ_prior=args.occ_prior).fit(tr["occ"], tr["gap"])))
    model.fit(tr["occ"], tr["gap"])
    out = evaluate(model, tr, te)
    report(args.hand, model, msg, out, s)
    keys = defaultdict(int)
    for _, role, c, _ in tr["occ"]:
        keys[(c, role)] += 1
    thin = sum(1 for k, n in keys.items() if n < MIN_SEG_PER_KEY)
    if thin:
        print(f"\n⚠ 段级样本不足: {thin}/{len(keys)} 个 (组合,角色) 键样本 < {MIN_SEG_PER_KEY} "
              f"→ 主要靠收缩/先验; 当前数据量只够验证管线, 不足以定当量表")
    if args.full:
        model_full = (ShrunkModel(occ_prior=args.occ_prior) if args.model == "shrunk"
                      else EmbedModel(LEFT_COMBOS if args.hand == "l" else RIGHT_COMBOS,
                                      prior=ShrunkModel(occ_prior=args.occ_prior).fit(s["occ"], s["gap"])))
        model_full.fit(s["occ"], s["gap"])
        export(model_full, args.hand)
    print(f"[耗时 {time.time()-t0:.1f}s]")


if __name__ == "__main__":
    main()
