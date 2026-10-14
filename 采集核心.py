#!/usr/bin/env python3
"""
采集核心.py — **采集器与验证工具共用的组件层** (唯一来源: 引擎语义 / 键位图组件 / 输入层
只写在这里, 谁都不许再抄一份; 分层与消费者见文件末 "本模块为什么单独存在")
  StrokeTrial: 分击状态机 (R1-R4, 对齐 RIME chord_composer; T_SYNC 可关 = 真实引擎口径;
               2026-09-29 错误捕获态: R1/R2/R3 全放开才收尾, actual 含完整错误组合)
  KeyboardCanvas: 键盘位置图 (正交/直列, 空白键帽无字母); 一击 = **多击合并一张图**,
              **图形区分击序** (v2.40, 2026-10-11 用户决策): 第 1 击 = **圈** · 第 2 击 = **叉**
              (叉长 = 圈直径, 端点落在圈上 = 内切) · 两击共有 = **圈里一个叉**; 键位标记
              **未按下时一律白色**; **按下反馈 = 颜色** (v2.51, 2026-10-12 用户决策"全白色易疲劳"):
              按下**当前该打的键** ⇒ 该击的图形变**绿** (共键按第 1 击只绿圈、按第 2 击只绿叉),
              按**不该打的键** (含非目标键) ⇒ 变**红**; 线宽恒定、**不再加粗**;
              **出错时整个画布边框闪一下红** (v2.53, `flash_error`/`flash_end`, 非文字信号);
              **不提示"现在打第几击"** (v2.41: 圈在前叉在后,
              击序图上写全 ⇒ 边框平时固定中性、图例不加粗) ; 见 KeyboardCanvas._paint;
              **半边键盘** (v2.31; **v2.57 恢复**): 只画采集手那一半, 另一半整个隐藏
              (键少一半才好定位; 手别由"另一半根本不在" + 窗口标题给出)
  ime_detach: **无视输入法**的输入层 (2026-10-01 起; **v2.46 删进程级 IME 层 / v2.47 删键盘钩子层**)
              只剩"摘除本窗口 IME 上下文"(`ImmAssociateContext`) 这一条 —— 本窗口不组字/不弹候选框,
              **tkinter 直接收到干净字母**; 按键来源 = **tkinter 事件绑定** (键名来自 event.char,
              故 `vk_to_key` 也随之删除; 见下方 输入法小节)
键盘几何/组合空间见 并击公共.py
"""
import math
import os
import sys
import time
import tkinter as tk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from 并击公共 import (KEY_POS, LEFT, LEFT_SET, RIGHT_SET,          # 键盘几何/组合空间
                     LEFT_COMBOS, RIGHT_COMBOS, REF_COMBO, canon,  # canon = 组合串唯一归一化
                     COL_FINGER_L, COL_FINGER_R, MAX_ROW_D)

T_SYNC = 0.100   # 同击按下散布上限 (秒) = R2 判据; 传 float('inf') 即关闭 R2 (真实引擎口径)
N_STROKES = 2    # 锚点数组固定 2 击 (数据格式; 试次实际击数由 strokes 决定)

# 半边键盘的手别键集 (2026-10-04): 采集哪只手就只显示那一半 —— 位置认知靠"另一半根本不在",
# 不再需要基准键标记 (f/j 短横线) 和手分界线 (中缝粗竖线) 这两类人工记号


def _hand(key):
    return 'l' if key in LEFT_SET else 'r'

# ═══════════════════ 分击状态机 (纯逻辑, GUI 与 --selftest 共用) ═══════════════════

class StrokeTrial:
    """一次试次的分击校验与计时。时间单位秒。击 = 无序键集合（练习模式 n=1）。"""

    def __init__(self, strokes, t_sync=T_SYNC):
        self.t_sync = t_sync
        self.strokes = [set(s) for s in strokes]
        self.n = len(strokes)
        self.si = 0
        self.remaining = set(self.strokes[0])
        self.downs, self.ups = [], []
        self.held = {}
        self.fd = None
        self.t0 = None
        self.done = False
        self.error = None
        self.err_tag = ""          # 落盘用短标签, 如 'R1@2' (规则@击序), ok 行为空
        self.final_formed = False
        # 错误捕获态 (2026-09-29): R1/R2/R3 出错后不再立即判死, 继续记录按键/松开,
        # 直到**所有键放开**才收尾 (done) —— 否则 actual 只记到出错键为止,
        # 完整的错误键位组合 (读图错的那个组合) 恰是分析最需要的部分。
        # R4 (击不完整) 触发时刻本身就是"全放开", 已按子集即该次尝试的全部, 不捕获。
        self.capturing = False

    def _fail(self, tag, msg):
        """记错误: error = GUI 提示, err_tag = 落盘标签"""
        self.error = f'{tag} {msg}'
        self.err_tag = f'{tag}@{self.si + 1}'
        self.capturing = tag != 'R4'

    def press(self, key, t):
        if self.done or key in self.held:
            return
        if self.error:                                     # 捕获态: 只记录, 不校验
            if self.capturing:
                self.downs.append((self.si, key, t))
                self.held[key] = t
            return
        if self.t0 is None:
            self.t0 = t
        # 事件先落盘再校验: 出错键本身必须进 downs/held, 否则 actual 无法复原实际输入,
        # R2 的散布超限幅度也会丢失 (2026-09-07 修)
        self.downs.append((self.si, key, t))
        self.held[key] = t
        if not self.remaining:                             # 当前击已成形待全放
            self._fail('R3', f'提前击: {key}')
            return
        if key not in self.remaining:
            self._fail('R1', f'键序错误: {key}')
            return
        if self.fd is not None and t - self.fd > self.t_sync:
            self._fail('R2', '散布超限')
            return
        if self.fd is None:
            self.fd = t
        self.remaining.discard(key)
        if not self.remaining and self.si == self.n - 1:
            self.final_formed = True

    def release(self, key, t):
        if self.done:
            return
        if key not in self.held:
            return
        del self.held[key]
        self.ups.append((self.si, key, t))
        if self.error:
            # 捕获态收尾: 全放开 → done (GUI 在 done+error 时落盘错误行);
            # R4 (capturing=False) 在下方 _fail 后由 GUI 立即落盘, 不走这里
            if self.capturing and not self.held:
                self.done = True
            return
        if self.held:
            return
        if self.remaining:
            self._fail('R4', '击不完整')                   # 含击内断开: 全放即输出缺键击
            return
        self.si += 1
        self.fd = None
        if self.si >= self.n:
            self.done = True
        else:
            self.remaining = set(self.strokes[self.si])

    def anchors(self):
        """每击每手 (fd, ld, fu, lu)，列序: 击1左, 击1右, 击2左, 击2右; None=该手该击无键
        固定返回 N_STROKES×2 组 (1 击试次的二击组全 None) → 数据列数恒定"""
        out = []
        for k in range(N_STROKES):
            for h in ('l', 'r'):
                ds = [t for si, key, t in self.downs if si == k and _hand(key) == h]
                us = [t for si, key, t in self.ups if si == k and _hand(key) == h]
                out.append((min(ds) - self.t0 if ds else None, max(ds) - self.t0 if ds else None,
                            min(us) - self.t0 if us else None, max(us) - self.t0 if us else None))
        return out

    def actual_str(self):
        groups = [''.join(key for si, key, _ in self.downs if si == k) for k in range(self.n)]
        return '|'.join(g for g in groups if g)

# ═══════════════════ 自测 ═══════════════════

def selftest():
    # 组合空间: 约束①② 逐条验证
    assert len(LEFT_COMBOS) == len(RIGHT_COMBOS) == 79, (len(LEFT_COMBOS), len(RIGHT_COMBOS))
    # 参考组合: sdf/lkj 在空间内且为 3 键
    assert REF_COMBO['l'] in LEFT_COMBOS and REF_COMBO['r'] in RIGHT_COMBOS
    assert len(REF_COMBO['l']) == 3 and set(REF_COMBO['l']) <= LEFT_SET
    assert len(REF_COMBO['r']) == 3 and set(REF_COMBO['r']) <= RIGHT_SET
    assert all(len(c) <= 2 for c in LEFT_COMBOS if c != REF_COMBO['l'])   # 唯一 3 键组合
    for combos, col_finger in ((LEFT_COMBOS, COL_FINGER_L), (RIGHT_COMBOS, COL_FINGER_R)):
        for c in combos:
            if len(c) == 2:
                (ra, ca), (rb, cb) = KEY_POS[c[0]], KEY_POS[c[1]]
                assert col_finger[ca] != col_finger[cb], c   # ① 单指一键
                assert abs(ra - rb) <= MAX_ROW_D, c          # ② 跨行 ≤1
    assert 'rt' not in LEFT_COMBOS and 'fg' not in LEFT_COMBOS and 'qa' not in LEFT_COMBOS  # 同指
    assert 'qx' not in LEFT_COMBOS and 'e,' not in LEFT_COMBOS                              # 跨2行/跨手 (含右手字符的串本就不在左手空间)
    assert 'sf' in LEFT_COMBOS and 'xd' in LEFT_COMBOS and 'er' in LEFT_COMBOS and 'zv' in LEFT_COMBOS
    assert '.,' in RIGHT_COMBOS and '.j' in RIGHT_COMBOS and ';u' in RIGHT_COMBOS and 'oi' in RIGHT_COMBOS
    assert 'ik' not in RIGHT_COMBOS and '.y' not in RIGHT_COMBOS
    # 拼读并击声介样例 (说明书序) 经 canon 归一化后全部合法 (canon 来自 并击公共 = 唯一口径)
    for c in ('sd','sg','eg','xg','qf','xc','cv','af','wf','zf','dg','cf','se','xd','as',
              'sf','xv','cg','er','ag','sr','qg','df','sv','ef','dr','zg','we','qr','dv','wr','ar','av'):
        assert canon(c) in LEFT_COMBOS, c
    def approx(a, b, eps=1e-9):
        return all(x is None and y is None or x is not None and y is not None and abs(x-y) < eps
                   for x, y in zip(a, b))

    def ev(st, events):
        for typ, key, t in events:
            (st.press if typ == 'd' else st.release)(key, t)

    # T1 状态机单元测试: 混合手击串 (状态机本身与采集模式无关, 校验 per-hand 锚分组)
    st = StrokeTrial(['dkl', 'aj'])
    ev(st, [('d','d',0.000), ('d','k',0.020), ('d','l',0.045),
            ('u','d',0.120), ('u','k',0.125), ('u','l',0.130),
            ('d','a',0.550), ('d','j',0.570), ('u','a',0.650), ('u','j',0.660)])
    assert st.done and not st.error, st.error
    an = st.anchors()
    assert approx(an[0], (0.0, 0.0, 0.120, 0.120)), an[0]
    assert approx(an[1], (0.020, 0.045, 0.125, 0.130)), an[1]
    assert approx(an[2], (0.550, 0.550, 0.650, 0.650)), an[2]
    assert approx(an[3], (0.570, 0.570, 0.660, 0.660)), an[3]
    assert st.actual_str() == 'dkl|aj'

    # T2 单手模式: 右手锚全 None
    st = StrokeTrial(['sf', 'xc'])
    ev(st, [('d','s',0.000), ('d','f',0.030), ('u','s',0.150), ('u','f',0.160),
            ('d','x',0.400), ('d','c',0.440), ('u','x',0.550), ('u','c',0.560)])
    assert st.done and not st.error, st.error
    an = st.anchors()
    assert approx(an[0], (0.0, 0.030, 0.150, 0.160))
    assert an[1] == (None, None, None, None)
    assert approx(an[2], (0.400, 0.440, 0.550, 0.560))

    # T3-T6: R2/R3/R1/R4 — 同时校验 err_tag 与"出错键落盘"
    st = StrokeTrial(['df', 'xc'])                       # 同手键 (d,f 均左手) 便于看散布
    st.press('d', 0.0); st.press('f', 0.15)
    assert st.error and st.error.startswith('R2') and st.err_tag == 'R2@1', (st.error, st.err_tag)
    assert st.actual_str() == 'df'                       # 超限的那一击也留在 actual 里
    an = st.anchors()[0]
    assert abs((an[1] - an[0]) - 0.15) < 1e-9, an        # 散布幅度可复原 (ld−fd=0.15)
    st = StrokeTrial(['dk', 'ef'])
    st.press('d', 0.0); st.press('k', 0.02); st.release('d', 0.1); st.press('e', 0.12)
    assert st.error and st.error.startswith('R3') and st.err_tag == 'R3@1', (st.error, st.err_tag)
    assert st.actual_str() == 'dke'                      # 抢跑键 (e) 记入当前击
    st = StrokeTrial(['dk', 'ef'])
    st.press('x', 0.0)
    assert st.error and st.error.startswith('R1') and st.err_tag == 'R1@1', (st.error, st.err_tag)
    assert st.actual_str() == 'x'                        # 错键本身落盘 (原先会丢)
    st = StrokeTrial(['sf', 'xc'])
    st.press('j', 0.0)
    assert st.error and st.error.startswith('R1') and st.err_tag == 'R1@1', (st.error, st.err_tag)
    st = StrokeTrial(['dk', 'ef'])
    st.press('d', 0.0); st.release('d', 0.1)
    assert st.error and st.error.startswith('R4') and st.err_tag == 'R4@1', (st.error, st.err_tag)
    assert st.actual_str() == 'd'                        # 缺键击的已按子集

    # T7 自动重复忽略
    st = StrokeTrial(['dk', 'ef'])
    st.press('d', 0.0); st.press('d', 0.05); st.press('k', 0.06)
    st.release('d', 0.1); st.release('k', 0.11)
    assert not st.error and st.si == 1 and not st.done, st.error

    # T8 练习模式 (单击试次, n=1)
    st = StrokeTrial(['sf'])
    st.press('s', 0.0); st.press('f', 0.03); st.release('s', 0.15); st.release('f', 0.16)
    assert st.done and not st.error
    assert approx(st.anchors()[0], (0.0, 0.030, 0.150, 0.160))
    assert st.anchors()[2] == (None, None, None, None)   # 无第二击 → 二击锚全 None

    # T9 错误捕获态 (2026-09-29): R1/R2/R3 出错后继续记录, 全放开才 done; R4 即时
    # T9a R1 击中错键: 击未成形时按错 → 捕获态, 后续键全部入账
    st = StrokeTrial(['dk', 'ef'])
    st.press('d', 0.0)
    st.press('r', 0.02)                                  # 错键 (r ∉ {k}) → R1@1, 进入捕获态
    assert st.error and st.err_tag == 'R1@1' and st.capturing and not st.done
    st.press('k', 0.04)                                  # 捕获态: 继续记 (不校验)
    st.release('r', 0.08); st.release('k', 0.10)
    assert not st.done                                   # d 仍按着 → 未收尾
    st.release('d', 0.12)
    assert st.done
    assert st.actual_str() == 'drk'                      # 完整错误键位组合
    an = st.anchors()[0]                                 # 锚按手过滤: k 右手不入左手锚
    assert abs(an[1] - 0.02) < 1e-9, an                  # 左手 ld = 最晚按下的 d/r
    # T9b R2 捕获: 超限后的补按键也入账
    st = StrokeTrial(['df', 'xc'])
    st.press('d', 0.0); st.press('f', 0.15)              # R2@1
    assert st.err_tag == 'R2@1' and st.capturing
    st.press('x', 0.20)
    for k, t in (('f', 0.25), ('x', 0.30), ('d', 0.35)):
        st.release(k, t)
    assert st.done and st.actual_str() == 'dfx'
    # T9c R4 即时: 触发即全放开, 已按子集就是该次尝试全部 (不捕获, 免把下次尝试并进本行)
    st = StrokeTrial(['dk'])
    st.press('d', 0.0); st.release('d', 0.1)
    assert st.err_tag == 'R4@1' and not st.capturing
    st.press('k', 0.3)                                   # R4 后新按键不入账 (试次已死)
    assert st.actual_str() == 'd'

    # T10 输入层 (v2.47): 只剩"摘窗口 IME"一条 —— 无 VK 映射、无钩子可测;
    # 真实摘除/收键行为由 实验/实验-IME按键捕获.py (阶段 B/C) 在真机上验证。

    print("核心自测通过: 组合空间 79×2 (78 合法 + sdf/lkj 参考) / 约束①② / R1-R4 / "
          "err_tag / 锚点分组 / 自动重复 / 错误捕获态")


# ═══════════════════ 键盘位置图 (正交/直列, 空白键帽无字母) ═══════════════════

# 键位图线型 (唯一源; 采集器与 实验/键位图预览.py 都从这里取)
# v2.40 (2026-10-11 用户决策) = **图形区分击序**: 第 1 击 = 圈 · 第 2 击 = 叉
# (叉长 = 圈直径, 端点落在圈上) · 两击共有 = 圈里一个叉; 颜色统一白色。
# v2.41 (2026-10-11 用户决策"不需要提示击次了"): **不再提示"现在打第几击"** —— 圈/叉已把击序写全
# (圈在前、叉在后), 故画布边框改回**固定中性色**, 图例不再加粗/不再着色, 试次行只写 Trial N。
# v2.51 (2026-10-12 用户决策"全白色易疲劳 + 共键该按当前击分别亮"): **按下反馈改用颜色, 不再加粗** ——
#   · 形状仍然只表示"属于第几击"; 颜色表示"这一下按得对不对":
#     按下**属于当前正在打的那一击**的键 ⇒ 该击的图形变绿, **另一个图形保持白**
#     (共键 s 在第 1 击只绿圈、过到第 2 击只绿叉 —— 用户要求"第 1 击圈亮起、第 2 击叉亮起");
#     按下**不属于当前击**的键 (非目标键、另一击独有的键) ⇒ 变红 (按错了)。
#   · 线宽**恒定** `KEY_W` ⇒ `KEY_W_PRESS` 已删 (高亮不再靠加粗)。
# v2.53 (2026-10-12 用户决策"出错时整个键盘边框闪一下红"): **画布边框在出错时短暂变红再复原**
#   (`flash_error`/`flash_end`) —— 给"没在看控制台"的人一个**非文字**的即时信号。
#   只用 `KEY_BAD` (与"按错的键"同色) 且**只改边框颜色** (不加粗); v2.41 那条"边框不随击序变化"
#   仍然成立: 只有**出错**才动边框, 且 `ERR_FLASH_MS` 后自动复原。
KEY_MARK = "#ffffff"                      # 未按下的目标图形 (圈与叉同色 = 统一白色)
KEY_OK = "#4ade80"                        # 按下 ✓ = 键属于当前这一击 ⇒ 该击的图形变绿
KEY_BAD = "#ff5b5b"                       # 按下 ✗ = 键不属于当前击 / 非目标键 ⇒ 变红 (也是闪红用色)
KEY_W = 2                                 # **基准**线宽 (运行期 = stroke_w = round(KEY_W×s), v2.54)
KEY_EMPTY_EDGE = "#3a3a3a"                # 非目标键极暗圈 = 键位骨架 (不表示任何一击)
KEY_FRAME = "#333333"                     # 画布边框: 中性 (v2.41 起不提示击次; v2.53 出错时闪红)
ERR_FLASH_MS = 450                        # 出错闪红时长 (毫秒): 短到不干扰打字, 长到看得见
# 键帽几何: **每键 = 一个圆圈 + 一个叉** (v2.32 圆即键帽 — 方形键帽容器删除, 2026-10-06 用户实测
# "圆圈显示效果更好"; 圆与叉都一律**不填充**): 圈 φ34; 格宽 38 + 间隙 4 = 42 ⇒ 键间留 8px。
# v2.54 (2026-10-12 用户决策"窗口/键位图太小了, 键位图大小随窗口变化, 窗口默认全屏的一半"):
#   上列尺寸降级为**基准设计尺寸** (下称 s=1); 实际渲染 = 基准 × **等比缩放系数 s**
#   (`KeyboardCanvas._relayout`, 由画布 `<Configure>` 驱动) —— 等比 ⇒ 圈永远是圆、键间距/内边距/
#   线宽一起缩放, 图在画布内居中 (窗口长宽比与键盘不同时留白, 不拉伸)。
R_KEY = 17.0                              # 圈半径 (基准; 默认 38/2−2; 运行期是 canvas.r_key)
# 叉端点偏移 = r/√2 (内切): 端点**落在圈上** ⇒ 每笔线长 = 2·(r/√2)·√2 = 2r = 圈直径 (v2.40 用户要求;
# 半径随窗口缩放后这条关系逐字不变 —— 由 _relayout 按当前 r 重算, 见 canvas.mark_strokes 旁注释)
KEY_COLS = max(c for _, c in KEY_POS.values()) + 1      # 键位图网格 (从 KEY_POS 派生, 不写死)
KEY_ROWS = max(r for r, _ in KEY_POS.values()) + 1


class KeyboardCanvas(tk.Canvas):
    """30 键键盘图: 每键 = **一个圆圈线条 + 一个叉** (两个叉笔), 一律**不填充**;
    **图形表示击序** (v2.40) —— 第 1 击 = 圈 / 第 2 击 = 叉 (叉长 = 圈直径, 端点落在圈上) /
    两击共有 = 圈里一个叉; **颜色表示"这一下按得对不对"** (v2.51) —— 未按下 = 白,
    按下当前该打的键 = 绿 (共键只绿**当前那一击**的图形), 按不该打的键 = 红;
    线宽恒定 (不再加粗); **半边键盘** (`set_hand`, v2.31; **v2.57 恢复**: 只画采集手那一半,
    另一半整个隐藏 —— 键少一半才好一眼定位目标; ⚠ 只隐藏、**不改尺寸基准**, 见 `_relayout`);
    **尺寸随画布大小等比缩放** (v2.54, `<Configure>` → `_relayout`: 大窗口 = 大键位图,
    圈仍是圆、叉仍内切、线宽一起缩放; 图居中, 不拉伸)

    一击 = **一张合并图** (2026-10-02 用户决策): 两击的目标都画在同一张键盘上, 不再上下摆两块
    键盘 (见 set_strokes)。合并后"打到第几击"没法靠图的位置分开, 所以:
      · **击序由图形编码** (v2.40, 2026-10-11): 圈 = 第 1 击 / 叉 = 第 2 击 / 圈+叉 = 两击共有
        ⇒ **2 击试次一出现就看得见第 2 击的叉**, 1 击试次全程只有圈 (没有叉)
      · 非目标键 = 极暗骨架圈 (键位参照, 不表示任何一击); 按下 = **红圈** (按错了)
      · **不提示"现在打第几击"** (v2.41, 2026-10-11 用户决策): 圈在前、叉在后, 击序图上写全了 ——
        边框恒为中性色 (只有**出错**时才闪一下红, v2.53), 画布本身不随击序变化
    """

    def __init__(self, master, key_w=38, key_h=38, gap=4, pad=8):
        """key_w/key_h/gap/pad = **基准设计尺寸** (s=1 时的格宽/格高/间隙/内边距, 默认 = 历史值);
        实际渲染尺寸 = 基准 × 等比系数 (由画布当前大小决定, v2.54)。请求尺寸 = 基准外框
        ⇒ 未被布局管理器放大时 (预览/未映射) 就是基准排版。"""
        self._design = (key_w, key_h, gap, pad)
        self._base_w = 2 * pad + KEY_COLS * key_w + (KEY_COLS - 1) * gap    # 默认 432
        self._base_h = 2 * pad + KEY_ROWS * key_h + (KEY_ROWS - 1) * gap    # 默认 138
        self.r_key_base = min(key_w, key_h) / 2 - 2                         # 默认 17 (= R_KEY)
        super().__init__(master, width=int(self._base_w), height=int(self._base_h), bg="#181818",
                         highlightthickness=3, highlightbackground=KEY_FRAME)   # 固定中性边框 (v2.41)
        self.circles, self.crosses = {}, {}       # 每键: 圈 (第 1 击) / 叉 (第 2 击, 两笔)
        for key in KEY_POS:
            # 坐标先占位, 紧接的 `_relayout` 按基准排版写真实坐标 (v2.54)
            self.circles[key] = self.create_oval(0, 0, 0, 0, fill="", outline=KEY_EMPTY_EDGE,
                                                 width=KEY_W)
            # 叉 = 两笔 (↘ + ↗), 端点 (cx±xd, cy±xd) **落在圈上** ⇒ 每笔长 = 圈直径 (v2.40)
            self.crosses[key] = (
                self.create_line(0, 0, 0, 0, fill=KEY_MARK, width=KEY_W, state="hidden"),
                self.create_line(0, 0, 0, 0, fill=KEY_MARK, width=KEY_W, state="hidden"))
        self.hand = None                       # 半边显示: None=两手都画 / 'l' / 'r' (set_hand, v2.57)
        self.strokes, self.stroke_base = [], 0      # 击序键集 / 本画布第 0 项的绝对击序
        self.target_strokes, self.targets = {}, set()   # 每键的击序集合 / 目标键集
        self.pressed, self.press_stroke = set(), None   # 按下的键 / 当前正在打的那一击 (v2.51)
        self._flash_handle = None              # 出错闪红的复原定时器 (v2.53; None = 没在闪)
        self.scale, self.r_key, self.stroke_w = 1.0, R_KEY, KEY_W   # 当前缩放/半径/线宽 (只读回读)
        self._last_size = None                 # 上一次 Configure 的尺寸 (v2.54 防抖)
        self._relayout(int(self._base_w), int(self._base_h))     # 初始 = 基准排版
        self.bind("<Configure>", self._on_configure)

    # ── 尺寸: 随画布等比缩放 (v2.54, 2026-10-12 用户决策"键位图太小了, 大小随窗口变化") ──
    def _on_configure(self, event):
        """画布尺寸变了 ⇒ 等比重排。⚠ **先比尺寸再排**: `<Configure>` 事件很频繁 (窗口拖动/布局
        重算), 而且重排自己也会让 Tk 再发一次 ⇒ 不比较就可能来回抖。

        ⚠ 传下去的是**可绘面积** = 事件尺寸 − 2×`highlightthickness`: `<Configure>` 报的是含高亮环的
        窗口尺寸, 而 canvas 坐标系的原点在**环内侧** (实测: 画在 (0,0) 的图元 bbox 从环内起算) ——
        不减掉的话键位图会左右各溢出半个环宽 (被环裁掉, 吃掉内边距)。"""
        w = event.width - 2 * int(self.cget("highlightthickness"))
        h = event.height - 2 * int(self.cget("highlightthickness"))
        if (w, h) == self._last_size:
            return
        self._last_size = (w, h)
        self._relayout(w, h)

    def _relayout(self, w, h):
        """按画布实际尺寸 w×h **等比**重排键位 (v2.54)。

        `s = min(w/基准宽, h/基准高)` —— **等比**: 圈永远是圆 (绝不拉伸成椭圆), 格宽/间隙/
        内边距/线宽/叉端点全部一起缩放; 图整体**居中** (窗口长宽比与键盘不同就在短边留白)。
        只改图元 `coords`/`width` (**不重建图元** ⇒ 颜色/可见性/半边隐藏状态一律不受影响)。
        叉仍是"内切于圈的两笔、每笔长 = 圈直径", 只是半径换成了缩放后的 `r`。
        尺寸还没成形 (<10px: 未映射/被最小化) 时直接返回, 保持上一次排版 (否则会被压成 0)。"""
        if w < 10 or h < 10:
            return
        kw_, kh_, gap_, pad_ = self._design
        # 尺寸基准恒为**整张键盘** (10 列 × 3 行) —— **与是否半边隐藏无关** (v2.57):
        # 可见半边仍在"整张键盘"里自己那一侧 (位置语义不变), 隐藏的那半边的空间就留白;
        # 要"让可见半边填满窗口"是另一种口径 (v2.31–v2.54 曾按可见半边定标, 用户没要)。
        s = min(w / self._base_w, h / self._base_h)
        kw, kh, gap = kw_ * s, kh_ * s, gap_ * s
        r, xd = self.r_key_base * s, self.r_key_base * s / math.sqrt(2)
        gw = KEY_COLS * kw + (KEY_COLS - 1) * gap
        gh = KEY_ROWS * kh + (KEY_ROWS - 1) * gap
        ox, oy = (w - gw) / 2, (h - gh) / 2                  # 居中 (等比 ⇒ 短边留白)
        sw = max(1, round(KEY_W * s))                        # 线宽也缩放 (大图下 2px 会显细)
        self.scale, self.r_key, self.stroke_w = s, r, sw
        for key, (row, col) in KEY_POS.items():
            cx = ox + col * (kw + gap) + kw / 2
            cy = oy + row * (kh + gap) + kh / 2
            self.coords(self.circles[key], cx - r, cy - r, cx + r, cy + r)
            self.itemconfig(self.circles[key], width=sw)
            self.coords(self.crosses[key][0], cx - xd, cy - xd, cx + xd, cy + xd)
            self.coords(self.crosses[key][1], cx - xd, cy + xd, cx + xd, cy - xd)
            for it in self.crosses[key]:
                self.itemconfig(it, width=sw)

    def set_hand(self, hand):
        """半边键盘 (v2.31, 2026-10-04 用户决策; **v2.55 曾撤销 → v2.57 恢复**):
        只显示采集手那一半, 另一半整个隐藏 —— 屏幕上的键少一半, 目标一眼就能找到
        (用户 2026-10-12: "否则难以定位")。**键位保持原位, 不重排居中** (位置本身提示手别)。

        ⚠ 与 v2.31–v2.54 的差别: 这里**只隐藏、不改尺寸基准** —— 缩放基准恒为整张键盘
        (见 `_relayout`), 所以可见半边的键距/大小与"显示完整键盘"时**完全一致**,
        只是另一半不画了 (不会因为隐藏而把图放大)。
        hand = 'left'/'right'/'l'/'r'; None = 两半都显示 (预览/旧单色场景)。"""
        self.hand = {'left': 'l', 'right': 'r'}.get(hand, hand)
        self._paint()

    def shown(self, key):
        """该键在本画布上是否可见 (半边键盘: 另一半的键连人带标记整个隐藏)"""
        return any(self.itemcget(i, "state") != "hidden"
                   for i in (self.circles[key], *self.crosses[key]))

    def set_strokes(self, strokes):
        """多击合并目标: strokes = [第1击键集, 第2击键集, ...] (**击序自本画布的第 0 击起**)。

        `target_strokes` = 逐键的击序集合 (共有键 = {0, 1}) —— 与 `_paint` 的图形规则同源:
        第 1 击画圈 / 第 2 击画叉 / 两者都有 = 圈里一个叉 (v2.40)。
        """
        self.stroke_base = 0
        self._set_strokes(strokes)

    def set_targets(self, keys, stroke=0):
        """单击目标 (画单块图/单击的场景): `stroke` = 这些键属于第几击 —— 0 画圈 / 1 画叉
        (--split 的第 2 块图 = 第 2 击, 必须传 stroke=1; 预览/错误工具用默认 0 画圈)"""
        self.stroke_base = stroke
        self._set_strokes([keys])

    def _set_strokes(self, strokes):
        """写入击序键集 → 逐键击序集合 (自检/冒烟用 mark_strokes 回读画布真实状态)"""
        self.strokes = [set(s) for s in strokes]
        self.target_strokes = {}
        for i, ks in enumerate(self.strokes):
            for key in ks:
                self.target_strokes.setdefault(key, set()).add(self.stroke_base + i)
        self.targets = set().union(*self.strokes) if self.strokes else set()
        self.pressed, self.press_stroke = set(), None      # 目标换了 ⇒ 按下态一并复位 (v2.51)
        self._paint()

    def mark_strokes(self, key):
        """该键**画出来**的击序集合 (0 = 圈 / 1 = 叉; 空集 = 非目标键)。

        读画布真实图元状态 (哪个图形当前可见), 但"属于第几击"以 `target_strokes` 为准 ——
        按下态只改**颜色** (v2.51; 非目标键按下变红), 并不声称任何击序 ⇒ 回了交集才不会把
        "按下的错键"读成第 1 击。
        ⚠ 因此它**不能**发现"该藏的图形没藏"(如只属于第 1 击的键把叉画了出来) —— 这类断言
        在冒烟里直接查 `circles`/`crosses` 的 state。"""
        st = self.target_strokes.get(key) or frozenset()
        if not st or not self.shown(key):
            return frozenset()          # 非目标键 / 半边键盘里被隐藏的另一手
        drawn = set()
        if self.itemcget(self.circles[key], "state") != "hidden":
            drawn.add(0)
        if any(self.itemcget(i, "state") != "hidden" for i in self.crosses[key]):
            drawn.add(1)
        return frozenset(s for s in st if s in drawn)

    def flash_error(self, ms=ERR_FLASH_MS):
        """出错闪红 (v2.53, 2026-10-12 用户决策"出错时整个键盘边框闪一下红"):

        边框从 `KEY_FRAME` 变 `KEY_BAD` (与"按错的键"同色), `ms` 毫秒后由 `flash_end` 复原 ——
        **非文字**的即时信号, 给没在看控制台的人看。只改**颜色** (不加粗, 与 v2.51 的按下反馈同规矩);
        v2.41 那条"边框不随击序变化"仍成立: **只有出错才动边框**, 且会自动复原。
        重复调用 = 重新计时 (同一次错误里连按不会反复闪 —— 采集器用 `_err_flashed` 每试次只调一次)。"""
        self.config(highlightbackground=KEY_BAD)
        if self._flash_handle is not None:
            try:
                self.after_cancel(self._flash_handle)
            except Exception:
                pass                       # 定时器可能已被销毁/已触发 —— 无关紧要
        self._flash_handle = self.after(ms, self.flash_end)

    def flash_end(self):
        """停闪并复原边框 (`flash_error` 的定时器到点会调它; 退出清理与冒烟/预览手动收状态也用它)。

        幂等: 没在闪时调用只保证边框是中性色。"""
        if self._flash_handle is not None:
            try:
                self.after_cancel(self._flash_handle)
            except Exception:
                pass
            self._flash_handle = None
        self.config(highlightbackground=KEY_FRAME)

    def flashing(self):
        """是否正在闪红 (只读回读, 供断言读**画布真实状态**; 判据 = 边框色 == `KEY_BAD`)"""
        return self.cget("highlightbackground") == KEY_BAD

    def mark_pressed(self, keys, stroke=None):
        """按下集 + **当前正在打的那一击** (v2.51)。

        `stroke` = 绝对击序 (0 = 第 1 击 / 1 = 第 2 击; 与 `target_strokes` 同坐标系),
        只决定**颜色**: 按下且属于当前击的键 = 绿 (共键只绿**当前那一击**的图形, 另一个保持白),
        按下但不属于当前击 = 红; `None` = 拿不到当前击 (预览/旧调用) ⇒ 按下的目标键图形全绿。"""
        self.pressed = set(keys)
        self.press_stroke = stroke
        self._paint()

    def _press_color(self, held, s, st):
        """键上**属于第 s 击的那个图形**现在该用什么颜色 (v2.51; 只对目标键调用):

        未按下 = 白 (`KEY_MARK`); 按下 **且该键属于当前正在打的那一击** ⇒ 该击的图形绿
        (`KEY_OK`)、**另一击的图形保持白**; 按下但该键不属于当前击 ⇒ 红 (`KEY_BAD`, 按错了)。
        `press_stroke is None` (没有"当前击"信息) ⇒ 按下的目标图形全绿。"""
        if not held:
            return KEY_MARK
        if self.press_stroke is None:
            return KEY_OK if s in st else KEY_MARK
        if self.press_stroke in st:
            return KEY_OK if s == self.press_stroke else KEY_MARK
        return KEY_BAD

    def _paint(self):
        """图形规则 (v2.40, 2026-10-11 用户决策 —— **形状**区分击序):
          第 1 击 = **圈** · 第 2 击 = **叉** (每笔长 = 圈直径, 端点落在圈上 = 内切)
          · 两击共有 = **圈里一个叉** · 非目标键 = 极暗骨架圈

        颜色规则 (v2.51, 2026-10-12 用户决策"全白色易疲劳 + 共键按当前击分别亮"):
          未按下 = 白; 按下**当前该打的键** ⇒ 该击的图形绿、另一个图形白 (共键按第 1 击只绿圈、
          过到第 2 击只绿叉); 按下**不该打的键** (非目标键、另一击独有的键) ⇒ 红。
          **线宽恒定** `KEY_W` —— v2.51 起按下不再加粗, 反馈只走颜色 (旧 `KEY_W_PRESS` 已删)。
          **不画"当前击"** (v2.41 用户决策): 圈/叉已把击序写全 ⇒ 图形本身不随击序变化
          ("当前击"只影响**按下时**哪一个图形变绿)。
        每键的击序来自 `target_strokes` ⇒ 图形与 `set_strokes/set_targets` 写入的击序同源。"""
        for key, rid in self.circles.items():
            cross = self.crosses[key]
            if self.hand is not None and _hand(key) != self.hand:
                # 半边隐藏 (v2.31; v2.57 恢复): 另一只手的键整个不画 (圈与叉都藏起来)
                for it in (rid, *cross):
                    self.itemconfig(it, state="hidden")
                continue
            st = self.target_strokes.get(key) or frozenset()
            held = key in self.pressed
            if not st:
                # 非目标键: 平时 = 极暗空圈 (键位骨架, 叉不画); **按下 = 红圈** (按错, v2.51)。
                # 注意仍要显式设 state=normal —— 半边隐藏必须可逆 (v2.32 修: 旧版普通键分支不恢复
                # state, 换手试次整图只剩共键可见)
                self.itemconfig(rid, fill="", width=self.stroke_w, state="normal",
                                outline=KEY_BAD if held else KEY_EMPTY_EDGE)
                for it in cross:
                    self.itemconfig(it, state="hidden")
                continue
            # 目标键: 圈 = 第 1 击的图形 / 叉 = 第 2 击的图形 —— 颜色各自算 (v2.51)
            self.itemconfig(rid, fill="", width=self.stroke_w,
                            outline=self._press_color(held, 0, st),
                            state="normal" if 0 in st else "hidden")
            for it in cross:                                       # 叉用 line 的 fill 上色
                self.itemconfig(it, width=self.stroke_w, fill=self._press_color(held, 1, st),
                                state="normal" if 1 in st else "hidden")


# ═══════════════════ Windows 按键捕获: 无视输入法 (2026-10-01 用户实测反馈) ═══════════════════
# 问题: 输入法处于**中文态**时 tkinter 收不到按键 —— 字母先被 IME 拿去组字, Tk 只收到
#   keysym='??' 且 char='' 的 <KeyPress> (采集器据此判定"没有按键"); 而且 IME 会真的输出汉字、
#   弹候选框。实测 (zh-CN IME 中文态 + 真实注入按键, 脚本 实验/实验-IME按键捕获.py):
#     j/f 的 KeyPress char='' (只有 up 事件带 'j'/'f'); space 被 IME 变成 '减'。
# 解决 (**一条**, v2.47; 2026-10-12 用户决策"去掉钩子层, 只保留摘除窗口 IME"):
#   **摘除窗口 IME** `ImmAssociateContext(hwnd, NULL)` (ime_detach): 本窗口没有输入上下文 ⇒ IME
#   不参与, **tkinter 的 <KeyPress> 直接收到干净字母** (char='j'/'f'/' '), 且不组字/不输出编码/
#   不弹候选框。窗口每次激活后重摘一次 (系统会在激活时重新关联输入上下文)。
#   ⇒ 按键来源 = **tkinter 事件绑定** (采集器 `root.bind("<KeyPress>"/"<KeyRelease>")`), 键名取
#      `event.char`/`event.keysym` (不再需要 VK 映射)。
#   ⚠ **已删掉的两层** (留档, 别凭记忆恢复):
#     · **低层键盘钩子** WH_KEYBOARD_LL (v2.24 起的主来源, **v2.47 删**): 在输入进入任何消息队列
#       **之前**截键并吞掉 (IME 连键都看不到, 中英文态完全一致), 但代价是一整套全局钩子机制
#       (跨进程钩子 + 消息泵线程 + 队列轮询 + 全局吞键)。既然"摘窗口 IME"实测已够, 就不再背这份
#       复杂度; 顺带**不再全局吞键** (其他程序更不受影响)。
#     · **进程级禁用 IME** ImmDisableIME(0) (v2.24 第③层, **v2.46 删**): 只禁用调用线程, 且必须在
#       第一个顶层窗口建起来之前调用 (晚一步静默失败)。
#   另有 WM_IME_SETCONTEXT(lParam=0) 的子类化做法 (微软 DirectX 官方文章, 需改写 Tk 窗口过程
#   ⇒ 本机不采用)。
# 计时口径 (v2.47 起): 锚点 = 主线程处理 `<KeyPress>`/`<KeyRelease>` 时取 `time.perf_counter()`
#   (旧版在钩子回调里取时间戳, 再经 5ms 轮询送进主线程)。同一试次内所有锚点**仍然同源**, 段内
#   相对时序不受影响; 但两版的主循环延迟特性不同 (旧版免疫调度延迟、新版含事件分发延迟) ⇒
#   **跨这次改动别比亚毫秒差** (当量报的是 ms 期望值, 混算危害有界, 报数时须知道有这道界)。
IS_WINDOWS = sys.platform == "win32"


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _imm32 = ctypes.WinDLL("imm32", use_last_error=True)

    _GA_ROOT = 2

    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    # 抢前台相关 (v2.37): restype/argtypes 必须显式声明 —— 缺 restype 时 ctypes 按 c_int
    # 解释返回值, x64 下窗口句柄会被截断 (句柄高位非 0 时 GetWindowThreadProcessId 拿到
    # 错句柄 ⇒ 前台自检永远为假 ⇒ 采集器收不到任何按键)
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetFocus.argtypes = [wintypes.HWND]
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    _imm32.ImmAssociateContext.restype = ctypes.c_void_p
    _imm32.ImmAssociateContext.argtypes = [wintypes.HWND, ctypes.c_void_p]

    def app_is_foreground():
        """前台窗口是否属于**本进程** (采集器只在前台收键: 看门狗据此决定动不动试次)"""
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return pid.value == os.getpid()

    def tk_toplevel(root):
        """tkinter 顶层窗口句柄 (winfo_id() 在 Windows 上返回内部子窗口; 顶层要 GA_ROOT)"""
        return _user32.GetAncestor(wintypes.HWND(root.winfo_id()), _GA_ROOT) or root.winfo_id()

    def ime_detach(root):
        """把输入法从本窗口摘掉 (ImmAssociateContext(hwnd, NULL)): 本窗口不再组字/弹候选框。
        返回摘掉旧上下文的窗口数 (>0 = 原本确实挂着 IME); GetFocus() 只返回**本线程**的焦点窗口"""
        n = 0
        for h in {tk_toplevel(root), root.winfo_id(), _user32.GetFocus()}:
            if h and _imm32.ImmAssociateContext(wintypes.HWND(h), None):
                n += 1
        return n

    def claim_foreground(root):
        """把本窗口抢到**系统前台** (v2.37): 采集器只能在本进程前台时收键 (钩子按设计只在
        前台吞键/入队), 而新建窗口并不总能拿到前台 (Windows 前台锁) —— 结果是"启动后打字
        没反应、界面像卡住、一条数据不落"。AttachThreadInput 绕前台锁, 与实验脚本同法。
        只应在**启动时调一次** (反复抢焦点会打扰用户); 返回是否已成为前台窗口。

        调用前请确认窗口可见 (withdraw 状态下抢前台无意义)。"""
        hwnd = tk_toplevel(root)
        if not hwnd or hwnd == _user32.GetForegroundWindow():
            return True
        fg = _user32.GetForegroundWindow()
        tid = _user32.GetWindowThreadProcessId(wintypes.HWND(fg), None) if fg else 0
        me = _kernel32.GetCurrentThreadId()
        try:
            if tid:
                _user32.AttachThreadInput(tid, me, True)
            _user32.BringWindowToTop(wintypes.HWND(hwnd))
            _user32.SetForegroundWindow(wintypes.HWND(hwnd))
            _user32.SetFocus(wintypes.HWND(hwnd))
        except Exception:
            pass
        finally:
            if tid:
                _user32.AttachThreadInput(tid, me, False)
        return tk_toplevel(root) == _user32.GetForegroundWindow()


else:                                   # 非 Windows: 空实现 (钩子/IME 是 Windows 特性)
    def app_is_foreground():
        return False

    def claim_foreground(root):
        return False

    def tk_toplevel(root):
        return 0

    def ime_detach(root):
        return 0


# ═══════════════════ 本模块为什么单独存在 (2026-10-11 复核) ═══════════════════
# 最初 (v2.11) 的理由 = **两个采集脚本共用同一引擎** (主采集 + 错误成本采集) ⇒ 抽成公共模块。
# 错误成本工具已于 2026-10-11 删除 ⇒ 该理由**不再成立**, 但分层仍然保留, 因为**消费者有三个**
# (只有一个恰好是应用):
#   · `采集-并击当量.py`（主采集）: StrokeTrial + KeyboardCanvas + 输入层 + 键帽常量
#   · `实验/实验-IME按键捕获.py`（输入层**验证**）: 只要 ime_detach / app_is_foreground / tk_toplevel ——
#     验证工具必须打到**采集器真正在跑的那份实现**, 而不是另抄一份; 它不需要采集器的数据路径与
#     GUI（`采集-并击当量.py` 的模块级全局 OUT / _WEIGHTS 也不适合被当库用）
#   · `实验/键位图预览.py`（画法 dump）: 只要 KeyboardCanvas —— 同理, 预览必须与 GUI 同源
# ⇒ 判据: **只要"验证/预览工具"还要引用它, 就不该并进应用模块**; 反之若哪天连这两个工具都消失,
#   再考虑并回 `采集-并击当量.py`。本模块可用 `python 采集核心.py` 独立自测 (无 GUI/无数据副作用)。
if __name__ == "__main__":
    selftest()
