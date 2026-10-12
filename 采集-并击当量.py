#!/usr/bin/env python3
"""
并击当量采集工具 v2.48（2 击试次 = 4 码 = 一个二字词）
v2.48 (2026-10-12 用户要求"同步增加该功能"): **补上 `--no-ime` 排障开关** —— 与姊妹项目
                    `../串击击键当量/采集输入层.py` 的 `--no-ime` 同义: 整体关掉输入层
                    (`ime=False` ⇒ 不摘除、不重摘、不起周期任务) ⇒ **回到修复前行为**
                    (一点不碰输入法; 中文输入法态下将收不到按键 —— 采集器读 `event.char` 判"没有按键")。
                    实现: 构造器加 `ime=True` 参数 → `self._ime`; `_setup_input` 的两条 IME 动作与
                    `_ime_guard()` 起链、`_on_focus_in` 重摘全部受 `self._ime` 控制; 控制台照实打
                    "--no-ime 已关闭" 一行。**不改事件源、不改时间戳取法、不改落盘列** ⇒ 口径不受影响
                    (与 v2.47 删钩子不同: 那次删的是时间戳的来源)。用途 = 现场 A/B 证明这层真在起作用
                    (默认中文态可采 vs `--no-ime` 中文态收不到) + 二分定位"打字没反应"是否输入层导致
                    + 某台机器上摘除本身出问题时的逃生/回滚 (退回"先切英文再采")。`--smoke` 用计数打桩
                    断言"`ime=False` 一次都不摘 / `ime=True` 必摘"。
v2.47 (2026-10-12 用户决策 "去掉钩子层, 只保留摘除窗口 IME"): **输入层只剩"摘窗口 IME"一条** ——
                    删掉 **低层键盘钩子** `WinKeyHook`（`WH_KEYBOARD_LL`, v2.24 起的主来源）:
                    按键来源改回 **tkinter 事件绑定**（`<KeyPress>`/`<KeyRelease>`, 一直是回退路径）,
                    而"中文态收不到按键"这个原始问题由 **摘除窗口 IME**（`ime_detach` =
                    `ImmAssociateContext(hwnd, NULL)`, 激活时 + 每 2 s 重摘）单独解决 ——
                    实测阶段 B: 只留它时注入的字母就是**干净 down 事件**（本机 zh-CN 中文态下验证）。
                    **连带删除**: `WinKeyHook`/`vk_to_key`/`_VK_OEM`（键名改取 `event.char`, 不再有
                    VK 码来源）; `self.hook`/`self._no_hook`/`_poll_hook()`（含它那 5ms 轮询链与
                    队列异常隔离）; 构造参数 `hook=`; 命令行 `--no-hook`; `stop_hook()` → **`stop_guards()`**;
                    `_polling` → **`_running`**（不再有"轮询"这回事）。**保留**: 摘窗口 IME（含
                    `_on_focus_in` 重摘与 `_ime_guard` 每 2 s 重摘）、前台自检 `app_is_foreground`、
                    启动 `claim_foreground` 抢前台（**没有钩子后更关键**: 按键只到**有焦点**的窗口）、
                    `_focus_guard` + `_stuck_guard` 两条自愈路径、计数器 `key_events`。
                    ⚠ **计时口径变了**（见文件末"计时"一节 + `采集核心.py` 输入法小节）: 锚点时间戳
                    由"钩子回调内取"改为"tkinter 事件处理内取" —— 试次内同源 ⇒ 段内相对时序不变,
                    但主循环延迟特性不同 ⇒ **跨这次改动别比亚毫秒差**。**行为等价面**: 不再全局吞键
                    (别的程序更不受影响), 非前台照样收不到键 (本就如此)。
                    `--smoke`: 输入层断言改为"无钩子属性/无 `--no-hook`/`on_press` 归一化键名一致",
                    并把原"轮询链异常隔离"改为"**按键处理异常隔离**"（`on_press`/`on_release` 内隔离）。
                    **数据侧零改动**（22 列/门控/计时实现口径不动）。
v2.45 (2026-10-12 用户决策 "用法单独写一个说明书…放一个问号图标, 点击可以展开说明; 界面里就不需要
                    第一击圈/第二击叉这一行了; 只保留当前 trial 序号和总样本数信息这两行"):
                    **说明书独立成文 + 界面只剩两行字** ——
                    ① **`采集器说明书.md`**（项目根, 独立文档）: 圈/叉记法（哪一击是圈、哪一击是叉、
                       共有键画什么）、两行信息的含义、按键与错误码、数据落点、常见问题、启动开关;
                    ② **右上角 `?` 图标**（小圆圈 + "?", 与键位图同为"圆"的语言）→ 点击**展开/收起**
                       说明书抽屉（`tk.Text` + 滚动条, 17 行高）; 展开/收起都调 `_fit_geometry()` 让窗口
                       自适应; **首次展开才读盘**; 读不到文件 → 面板里**明说路径**（不静默空着）;
                       渲染 = 极简 Markdown（只认 `#` 标题 / `-`·`*` 列表 / 空行, 去掉 `**` 与反引号,
                       刻意不做完整解析 —— 语法扩展也不会让显示失真）;
                    ③ **删掉图例行**（"第 1 击 ○ → 第 2 击 ✕"）: 记法说明已收进说明书 ⇒ 界面上只剩
                       **顶部 `左 成功/样本 : 右 成功/样本`**（v2.44）+ **底部 `Trial N`**（v2.41）
                       这两行字; `_sync_legend` / `legend*` 全部删除（`--split` 两块图各自的
                       "第 1 击/第 2 击"标题保留 —— 那标的是**块**, 不是记法）。
                    **数据侧零改动**; `--smoke` 新增: `?` 默认收起 · 点开/再点收起的展开态与窗口高度 ·
                    正文来自独立文档且含记法与两行信息的关键词 · Markdown 标记被渲染掉 ·
                    缺文件明说路径 · 图例相关属性**真的不存在**。
v2.44 (2026-10-12 用户决策 "界面上方改成左成功数/样本数:右成功数/样本数"): **顶部恢复一行**
                    (`label_hands`, 显 "左 成功/样本 : 右 成功/样本") —— 与 v2.43 删掉的那三行
                    **不同**: 它不是"给旁观者看的说明书", 而是**只读数据文件的证据量计数**。
                    口径: **成功 = `error=0` 的已落盘行, 样本 = 该手全部已落盘行**;
                    数据源 = `scan_hand_counts(OUT)` **启动现扫 `当量数据.tsv`** + 每落一行在内存
                    累加 (落盘失败的行两个数都不加 —— 文件里没有的不算证据; 练习数据不计)
                    ⇒ **不新建持久计数器, 不存在与文件漂移的第二种真相**。手别取 `code` 首击。
v2.43 (2026-10-12 用户决策 "图中红色部分删除 · 绿色部分只显示当前 trial 次数 · 丢失焦点/超时的
                    红色提醒也删除"): **界面精简到只剩"要打什么"** —— 删掉四行**给旁观者看**的
                    说明/监控文字, 留下: 图例 (记法说明) → 键位图 → 反馈行 → 试次号。
                    ① 顶部「采集手: 左右 1:1 随机单手（每试次抽边 · 增补落后侧）」整行删除;
                    ② 标题/平衡行「并击击键测速 · 左手 ⟳ 左 N : 右 M P(右)=p」整行删除
                       (`label_title` 删; **手别**改由窗口标题 + 图本身给出 —— 键位图只画采集手
                       那一半; 左右计数 `hand_totals` 本是 `choose_hand` 的输入, 只不再显示);
                    ③ 底部操作提示行「按亮键并击… | 空格跳过 | Esc 退出」整行删除 (`label_hint` 删);
                    ④ 计数行「已记录: N ｜ 按键 M」整行删除 (`label_count`/`_update_count_label` 删)
                       ⇒ 计数区**只留 `Trial N`** (`label_block`; 击数与击序图上已写全, 见 v2.40/41);
                    ⑤ **焦点与超时提醒不再上屏** (`_refresh_warn` 只留"内部错误/落盘失败"两条真问题;
                       `_was_fg`/`_stale`/`_trial_ts`/`STALE_HINT_S` 随之删除)。
                    **底层防护一条不减**: 启动抢前台、`_focus_guard` 周期任务 (前台才跑看门狗 ⇒
                    非前台时不动试次)、`_stuck_guard` 两条自愈路径、`_poll_*` 异常隔离、落盘失败
                    可见 —— 按键流计数 `key_events` 与左右计数仍在, 只是改从**控制台报错行**露出
                    ("键到没到"这条诊断仍可查)。**数据侧零改动** (22 列/门控/计时/口径全不动)。
v2.41 (2026-10-11 用户决策 "不需要提示击次了"): **撤掉"现在打第几击"的全部提示** ——
                    圈在前、叉在后, 击序图上写全了, 无需另提示。删: ① 画布**边框色**随当前击
                    变化 (`set_active_stroke`/`set_active`/`active_stroke`/`accents` 与
                    `ACCENT1/ACCENT2` 常量**整体删除**, 边框恒为中性 `KEY_FRAME`); ② 图例
                    **当前击加粗** (`_sync_legend` 只留"1 击试次淡掉第 2 击档"这条**试次**信息);
                    ③ 试次行的 `· k击 · 当前第 j 击` → **只写 `Trial N`** (`label_block`)。
                    图例本身保留 (它是**记法说明**: 圈 = 第 1 击 / 叉 = 第 2 击), 但改**全白**
                    (不再着色)。⇒ 整个界面**再无任何颜色编码**, 且画布内容**只由击序决定**,
                    不随"打到第几击"变化 (v2.39/v2.40 那类"推进击序时画面闪变"的类别连根消失)。
                    **数据侧零改动** (22 列/门控/计时/口径全不动; 纯显示层)。
v2.40 (2026-10-11 用户决策 "换一种表示方法"): **图形区分击序, 颜色统一白色** ——
                    第 1 击 = **圈** · 第 2 击 = **叉** (叉长 = 圈直径, 端点落在圈上 = 内切)
                    · 两击共有 = **圈里一个叉**; 键位标记**一律白色** (不再用蓝/红分击),
                    **按下 = 加粗高亮, 松开恢复** (白已最亮 ⇒ 高亮只能靠线宽 2→5);
                    非目标键 = 极暗空圈 (键位骨架, 不表示任何一击)。
                    "现在打第几击"不再由键位颜色承载, 仍由**画布边框色** (蓝=第 1 击 / 红=第 2 击)
                    + **图例加粗** + 试次行 "当前第 j 击" 提示; 图例图形与键帽同源 (圈 / 叉)。
                    ⚠ **v2.41 起这三条提示已全部撤除** (见文件头 v2.41 条目)。
                    `--split` 旧布局同改 (下块 = 第 2 击 ⇒ `set_targets(..., stroke=1)` 画叉)。
                    **数据侧零改动** (22 列/门控/计时/口径全不动; 纯显示层)。
v2.39 (2026-10-11 用户实测两轮澄清后定案: "打完 1 击试次松手后红闪一下又回蓝, 不是换试次"
                    + "二击的试次应该一开始就显示红色"): **恢复逐击上色 + 试次首笔自洽 (消闪红)**
                    **实测确认** (逐时刻采样画布): **1 击试次全过程没有任何红色** (击 1 目标全蓝;
                    释放后 `si=1 ⇒ done` ⇒ 边框转灰、键回蓝)。⇒ 用户看到的红来自**下一试次的首笔**:
                    `_paint_targets` 画目标时用的还是**上一试次遗留的 `active_stroke`**(完成态=None),
                    v2.39 的"只给当前击上色"口径下那一笔先把第 2 击画成红, 几毫秒后被"当前击=1"
                    的一笔覆盖成灰 ⇒ 用户肉眼看到"打完 1 击试次松手后红闪一下又回蓝, 又不是换试次"。
                    **修 (按用户要求)**: ① **恢复逐击上色** —— 每一击的键按自己的击序上色 (第 1 击蓝 /
                    第 2 击红) ⇒ **2 击试次一出现就看得见第 2 击的红**, 1 击试次全蓝 (全程无红),
                    共有键仍 = 首击色 (v2.35); ② **试次首笔自洽** —— `_paint_targets` 先把
                    `active_stroke` 定到本试次的击 1 再画目标 ⇒ 首笔与随后的 `_update_kb` 完全一致,
                    中间态不复存在 (闪红的根因); ③ 撤销"未到击次灰" (`KEY_PENDING_EDGE` 删除)。
                    另保留: 试次行 **"Trial N · k击 · 当前第 j 击"** + 图例当前击加粗 + 边框 3px。
                    **数据侧零改动**; 冒烟新增"2 击首笔即红"与"首笔≡后续状态 (不闪)"两条断言。
v2.38 (2026-10-11 用户实测"快打时偶发界面卡住 / 松开时圈变红"): **收不了尾的看门狗** ——
                    机制: **错误捕获态** (R1/R2/R3, 2026-09-29 语义) 要求"所有键都放开"才收尾;
                    快打/滚动按键 (下一键按下时上一键还没全放) 会长时间保持"有键按住" ⇒ 试次永不
                    结束 —— 界面停在原试次、按键无反应、**连错误行都不落盘**, 现象与"卡死"完全一样
                    (用户新 session 里 R1@2/R3@2 错误行 = 滚动打法的证据)。此时按下的键画成"蓝闪",
                    松开又回到它的**目标色** (第 2 击目标 = 红) ⇒ 用户看到"松开时圈瞬间变红, 按理不该红"。
                    修: ① **看门狗** —— 捕获态静默 5s 视同"已全放"→ 错误行照常落盘 + 继续
                    (`CAPTURE_STUCK_S`); 正常试次静默 20s (漏收松开事件) 同法收尾 (`TRIAL_STUCK_S`)。
                    ② 错误提示补 **"（全部松开即继续）"** —— 旧版只说 "✗ R1 …", 用户不知道在等什么。
                    ③ 试次间隔 (300-800ms) 里按键改为**明确提示** "⏳ 下一试次还没出现 —— 这一下没有
                    被记录" (旧版静默丢弃 ⇒ 快打抢拍时击序错位)。
                    ④ **当前击可见**: 图例「第 1/2 击」当前击**加粗** + 画布边框 2→3px
                    (合并图里"现在打第几击"原来只由细边框提示, 快打时看不出)。
                    **数据侧零改动** (22 列/门控/计时/口径未动); 看门狗落的是**错误行**(本就不进当量)
                    或"缺松开锚"的 ok 行(分析侧按段不齐丢弃), 不污染口径。
v2.37 (2026-10-11 用户实测"一击打完后界面卡住不动"): **静默失联防护** —— 旧版有四条
                    "界面看起来卡死、且一条数据都不落、还没有任何提示"的路径, 现全部隔离 + 可见:
                    ① `_poll_hook` 按键分发无异常隔离 ⇒ 一个事件抛异常就永不再重排 ⇒ 键盘彻底失联
                       (钩子还在吞键, 连 Esc 都收不到); ⚠ `_poll_hook` 已随钩子层于 v2.47 删除
                       (这条保证现在由 `on_press`/`on_release` 内的异常隔离承担); ② `_record` 写盘失败 (OneDrive/杀软/Excel
                       占用) 同样打断轮询链且不提示; ③ `_start_next` 抛异常让 phase 永久停在
                       "blocked" (此后按键被静默忽略); ④ 窗口不在前台时钩子放行、按键进不了采集器。
                    现在: ①②③ 一律隔离 + 界面红字告警 (控制台打全栈), ④ 用**焦点自检**提示
                    ("⚠ 窗口未获得焦点 —— 按键不会被采集") + **按键流计数**(计数行实时显示
                    "按键 N": 涨 = 键到了采集器, 不涨 = 键根本没进来), 区分"卡死"与"没焦点"。
                    落盘失败的行不计入 `recorded`/采样覆盖 (文件里没有的不算证据), 但流程照常推进。
                    **数据侧零改动** (22 列格式/门控/计时/口径全不动), 只加固控制流与可见性。
v2.34 (2026-10-11): **混采比 1击:2击 1:2→1:4（临时档）** —— 加速 gap 段达标（gap 行/天 ×1.5;
                    闭环模拟确认早退协议无法加速后的真杠杆之一）; 回退条件见 MIX_ONE_TWO 注释;
                    数据侧零改动（22 列格式/门控/计时/稳定期分类型计算全部不变）
v2.22 起: 左右手 1:1 增补混采; v2.23 (2026-10-01): 移除固定单手模式 (只剩随机单手);
v2.24 (2026-10-01): **无视输入法** —— 当时 = 低层键盘钩子 (主) + 摘除窗口 IME (回退)
                    (⚠ v2.46 删了进程级 ImmDisableIME、v2.47 删了钩子层 ⇒ 现只剩摘窗口 IME)
v2.31 (2026-10-04): **半边键盘** —— 只显示采集手那一半 (删基准键标记 + 手分界线)
v2.32 (2026-10-06): **圆形键帽** (删方形容器; 圆圈一律不填充, 按下只亮圈) + 修两个显示 bug:
                    ① 共键按下态改用 held (松开即灭 —— 旧用 downs 残留已放开的键,
                    击 1 的共键一放就随击序提前亮橙); ② 半边隐藏可逆 (旧 _paint 普通键
                    分支不恢复 state, 换手试次整张图只剩共键可见)
v2.33 (2026-10-08): **完成提示只显示时间** —— 一击 `xxms`; 二击 `xx+xx+xx=xxms`
                    (S1+S2+S3=wc; 三段各自取整后相加 ⇒ 屏幕算式恒自洽, 落盘仍用未取整浮点)。
                    练习模式同口径 (原先显示 combo/散布/进度, 那些仍在启动报告与落盘里)。
                    错误提示 (✗ R1/R2/R3/R4) 与"␣ 已跳过"不变。
设计文档: README.md §3-4（单手三段口径 + 闸门感知合成）

试次 = 2 击, 均为同一只手（**每试次随机抽边**, 只有这一种模式）。每击 = 该手 1-2 键并击组合。
只采词内两击转移; 词间注意力中断不采集（对齐串击惯例）。

显示: 键盘位置图（正交网格/直列键盘）——空白键帽无字母。**两击合并为一张图**（v2.26,
      2026-10-02 用户决策）: **图形区分击序**（v2.40, 2026-10-11 用户决策）——
      **第 1 击 = 圈 · 第 2 击 = 叉**（叉长 = 圈直径, 端点落在圈上 = 内切）·
      **两击共有 = 圈里一个叉**; 键位标记**一律白色**, 按下 = 加粗高亮、松开恢复;
      非目标键 = 极暗空圈（键位骨架）。⇒ **2 击试次一出现就看得见第 2 击的叉**,
      1 击试次全程只有圈。（历经 绿第三色 → 左半右半 → 叉形四三角 → 实心双圆 → 方键帽+圆环 →
      圆键帽逐击上色 → 只给当前击上色 七版配色方案; 第八版 = 形状编码）
      **不提示"现在打第几击"**（v2.41, 2026-10-11 用户决策）: 圈在前、叉在后 ⇒ 击序图上写全,
      故**没有**边框色提示、**没有**图例加粗、试次行**只写 `Trial N`** —— 整个界面
      **不含任何颜色编码** (标记白 / 非目标键极暗 / 边框中性)。图例保留, 只作**记法说明**
      （第 1 击 = 圈 / 第 2 击 = 叉, 一律白色; 1 击试次淡掉第 2 击档 = 试次信息）。
      --split 可回到旧的两击上下两图（下块 = 第 2 击, 同样画叉）。
      **半边键盘**（v2.31, 2026-10-04 用户决策）: 只画本试次采集手的那一半（键位保持原位）,
      另一半整个隐藏 —— 手别提示靠"另一半根本不在", 替代基准键标记（f/j 短横线）与
      手分界线（中缝粗竖线）这两类人工记号（均已删）。
      **非目标手输入禁用**（v2.35, 2026-10-11 用户决策）: 目标在左手 → 右手键一律忽略
      （不产生 R1）, 反之同理 —— 防按错。
      纯位置认知, 数据仍记 canonical 键串。

组合合法性约束（2026-08-19 实测反馈, README §3.4）:
  ① 单指一键 — 同一手指键区内只能取 1 键（如左食指 r/t/f/g/v/b 任两键不可同按）
  ② 跨行 ≤1  — 两键行距 2 几乎不可按（如 q+x）
  → 合法组合: 左右手各 78 (15 单 + 63 双); 拼读并击 51/44 是子集
  + **3 键组合 1 个/手**: sdf(左) / jkl(右) = 同排三指顺指（唯一 3 键）。
    2026-09-30 用户决策: 它**不再是判定的参考锚**（判定改为"同角色、同键数组合的总体中心",
    见 分析-难度剔除.py `--ref pooled`）⇒ 采样**与 2 键同比例**（REF_BOOST=1.0, 不再 ×5）,
    数据作为副产品; 排除表仍拒绝排除它（保留唯一的 3 键数据点, 通用模型用）。

模式: 左右手 1:1 随机单手混采（唯一模式, 无固定单手开关）[--practice]
  · 每试次按累计欠账抽边 (`hand_probability`): 先还历史欠账, 之后稳在 1:1, 两侧始终交错
  · 2026-10-01 用户决策: 移除"只左手/只右手"固定模式 —— 方案要求左右对称、练习效应也要对称,
    固定单手会破坏这两条; 单手数据无法参与"双手交集"剔除 (只手无数据 ⇒ 一个都不动)
  正式采集（默认）: 2 击试次（= 4 码 = 一个二字词）, 同手两击, 每击 1-2 键组合。
    无熟化前置协议 —— 直接采集, 练习段由稳定期方法统一剔除（姊妹项目哲学）;
    排除表每 REFRESH_EVERY 试次重载 → 分析-难度剔除.py 的判定采集中即时生效
  --practice（可选, 别名 --drill）: 单击反复练习 = 热身。练习进度存 练习进度.json
    （轮转 = 练得最少的优先; 难度判定与孤立基线均由正式数据的混采覆盖, §4.5）

输入层 (v2.47, 2026-10-12 用户决策"去掉钩子层, 只保留摘除窗口 IME"): **无视输入法**
  原始问题: 输入法中文态下 tkinter 收不到按键 (字母被 IME 拿去组字, <KeyPress> 的 char 为空),
  且 IME 会输出汉字/弹候选框。现在只靠一条机制解决:
  **摘除本窗口 IME 上下文** (ImmAssociateContext(hwnd, NULL); 窗口激活时 + 每 2 s 重摘一次) ⇒
  本窗口不组字/不输出编码/不弹候选框, **tkinter 直接收到干净字母** (实测 zh-CN 中文态:
  注入 j/f/space ⇒ char='j'/'f'/' ')。按键来源 = tkinter 事件绑定 (`on_press`/`on_release`)。
  ⚠ 已删的两层: 低层键盘钩子 (v2.24 主来源, v2.47 删) 与进程级 ImmDisableIME (v2.46 删)。
  **`--no-ime` (v2.48)**: 整体关掉这一层(回到修复前, 中文态会收不到键) —— 排障/A-B 对照用。
  验证脚本: 实验/实验-IME按键捕获.py (真实注入按键, 含复现与修复断言)

分击校验（对齐 RIME chord_composer: 同按为一击、全放时输出）:
  R1 键序错误 / R2 散布超限(>T_SYNC) / R3 提前击 / R4 击不完整(含击内断开)

计时: 每击每手记 fd/ld/fu/lu (ms, 相对试次首按); 主锚 = lu (全放=进解析时点)。
      单手采集时非活动手四锚恒为 0.0（列数恒 22: code + 16 锚 + error/err_type/actual/trial/session）。
- 空格跳过; Esc 退出; 试次间随机延迟 300-800ms; --selftest / --smoke 自测
"""
import sys, time, random, argparse, json, traceback, math
from collections import defaultdict
from pathlib import Path
import tkinter as tk
BASE = Path(__file__).resolve().parent    # 项目根 = 本脚本所在目录 (数据/排除表全落此, 整目录可迁移)
sys.path.insert(0, str(BASE))
from 采集核心 import (StrokeTrial, KeyboardCanvas, _hand,           # 引擎语义/GUI 组件唯一来源
                     KEY_MARK, KEY_W, KEY_W_PRESS, R_KEY,            # 键位标记: 统一白色 + 按下加粗
                     KEY_FRAME,                                       # 画布边框 = 固定中性 (v2.41)
                     N_STROKES, ime_detach, IS_WINDOWS,                # 输入层: 摘窗口 IME (v2.47)
                     app_is_foreground, claim_foreground,             # 前台自检/抢前台 (v2.37)
                     selftest as core_selftest)
from 并击公共 import LEFT, RIGHT, LEFT_SET, RIGHT_SET                # 手别/键盘序唯一来源

OUT = BASE / "当量数据.tsv"
PRACTICE_OUT = BASE / "练习数据.tsv"
PRACTICE_JSON = BASE / "练习进度.json"
KEYS = LEFT_SET | RIGHT_SET  # 全键盘 30 键 (派生量)
MIX_ONE_TWO = (1, 4)         # 混采比例 一击:二击 = 1:4 → P(1击)=1/5 (v2.34, 2026-10-11 用户决策:
                             #   **临时档** —— 加速 gap 段达标, gap 行/天 ×1.5; 闭环模拟确认
                             #   早退协议无法加速后, 这是两个真杠杆之一（memory 2026-10-11）。
                             #   **回退条件**: gap 段 ~3050/手（每端 n≈50×61 组合）后改回 (1,2);
                             #   1击数据变慢不中断 —— iso 与稳定期按类型各自计算, 不受污染。
                             #   旧值 (1,2) = v2.9 姊妹项目混采协议)
                             #   1 击试次 = 孤立角色 occ 测量 + 一击词(一级字/简词);
                             #   两类试次的稳定期**分别计算** (时间尺度不同, README §4.6)
REFRESH_EVERY = 200          # 每 N 试次重载组合排除表 (动态剔除生效; v2.8)
CAPTURE_STUCK_S = 5.0        # 错误捕获态静默多久后自动收尾 (秒; v2.38 看门狗, 防永久卡住)
TRIAL_STUCK_S = 20.0         # 正常试次静默多久后自动收尾 (秒; v2.38 看门狗, 防漏收松开事件)

# ── 左右手 1:1 混采 + **增补** (v2.22, 2026-10-01 用户决策) ────────────────────────
# 为什么必须同时采两手 (用户): 方案要求左右手可用组合**对称**, 剔除又只能在"两手都差"时动作
#   ⇒ 右手没有自己的数据就无法判定; 而且**练习效应**要求两手的熟练曲线同期 —— 先采完一手再
#   采另一手, 两手的水平差会混进"手别效应"里, 再也分不开。
# 机制 (沿用 串击击键当量 的"码长混采": 每试次按比例抽类型 + 各类型独立计数池 +
#   1/(n+1) 多样性增补) —— 把"类型"从码长换成**手**:
#   · 基础份额 = HAND_TARGET (1:1), **每试次独立抽** ⇒ 两侧在时间上交错 (练习效应对称)
#   · **增补**: 累计计数落后的一侧按欠账把概率推高 → 先还清历史欠账, 之后自我纠正局部漂移,
#     再稳在 1:1。偏置有上下限 ⇒ 落后侧最多 ~82%, 另一侧始终有 ~18% ⇒ 不会退化成单手段。
#   · 手内一切照旧: 1击:2击 = 1:4 (v2.34 临时档)、结构权重、1/(n+1) 多样性、降权系数 (各手独立计数池)
#   · v2.23 (2026-10-01 用户决策): **移除"只左手/只右手"固定模式** —— 采集手总是按增补规则
#     随机抽边 (无 CLI/GUI 开关)。固定单手会让另一手没有同期数据 (练习效应不可比 + 双手交集
#     永远为空), 与"同时采两手 + 双手交集剔除"直接冲突。
HAND_TARGET = (1, 1)         # 目标累计 左:右
HAND_CATCHUP = 400.0         # 增补视野 (试次): 欠账 → 概率偏置 = 欠账/视野 × 0.5
HAND_MAX_SKEW = 0.32         # 相对 1:1 的最大偏置 ⇒ 单侧概率 ∈ [0.18, 0.82]
HAND_COUNT_OK_ONLY = True    # 计数只算成功试次 (判据吃的是成功试次 ⇒ 直接对齐证据量)


def hand_probability(n_l, n_r, target=HAND_TARGET, catchup=HAND_CATCHUP, skew=HAND_MAX_SKEW):
    """累计计数 (n_l, n_r) → 下一试次采**右手**的概率 (增补规则; 纯函数, 便于自测)
    基础份额 ± 欠账偏置, 并夹在 [share−skew, share+skew] = **[0.18, 0.82]** (保证两侧始终交错)。

    ⚠ 2026-10-01 修: 原式写的是 `min(1−skew, max(skew, p))` = [0.32, 0.68] —— 与文档/GUI/启动行
    声称的 ±0.32 (即 [0.18, 0.82]) 不符, 增补力度只有设计的一半 (右手追平 897 的历史欠账从
    ~2800 试次拖到 ~5000 试次)。由首轮 v2.24 采集数据的左右比例 (8:9) 复核时发现。"""
    tl, tr = target
    share = tr / (tl + tr)
    exp_r = (n_l + n_r) * share                 # 1:1 时 = 总数/2
    p = share + (exp_r - n_r) / catchup * 0.5   # 右手欠 ⇒ 推高; 左手欠 ⇒ 压低
    return min(share + skew, max(share - skew, p))


# ── 组合空间 / 几何 / 参考组合: 来自共用模块 并击公共.py (口径唯一来源, 勿在此重复定义) ──
from 并击公共 import LEFT_COMBOS, RIGHT_COMBOS, REF_COMBO, COMBO_W
LEFT_COMBOS = list(LEFT_COMBOS)          # 副本 (共用模块常量已含 3 键组合, 勿原地改)
RIGHT_COMBOS = list(RIGHT_COMBOS)
# 3 键组合 (sdf/jkl) 采样权重倍数: 2026-09-30 起 = 1.0 (与 2 键同比例; 它不再是判定锚)
REF_BOOST = 1.0                          # 保留常量: 实验脚本 (实验-剔除样本量.py) 仍引用

# ── 组合排除表 (人工确认的最难组合, 从采样/练习空间剔除) ──
EXCLUDE_PATH = BASE / "组合排除表.txt"
_REF3_WARNED = set()     # 3 键拒绝提示去重: 该规则是**静态**的, 而表每 200 试次重读一次 ——
                         # 不去重就会把同一条提示反复刷屏 (2026-10-08: 表里记入 sdf 后发现)


def _refuse_ref3(c):
    """3 键组合 (sdf/jkl) 拒绝排除 —— 保留唯一的 3 键数据点, 通用模型用; 提示每进程只说一次"""
    if c not in _REF3_WARNED:
        _REF3_WARNED.add(c)
        print(f"排除表拒绝排除 3 键组合: {c} (保留唯一 3 键数据点, 通用模型用)")


def load_excluded(path=EXCLUDE_PATH):
    """每行一个组合 (# 注释); 返回 (左排除, 右排除) — 任意序/非法行容忍"""
    lex, rex = set(), set()
    if not Path(path).exists():
        return lex, rex
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.split("#")[0].strip().lower()
        if not s:
            continue
        if len(set(s)) != len(s) or not set(s) <= KEYS:
            print(f"排除表忽略无效行: {line!r}")
            continue
        if set(s) <= LEFT_SET:
            c = ''.join(sorted(s, key=LEFT.find))
            if c == REF_COMBO['l']:
                _refuse_ref3(c)
            elif c in LEFT_COMBOS:
                lex.add(c)
            else:
                print(f"排除表忽略非法左组合: {line!r}")
        else:
            c = ''.join(sorted(s, key=RIGHT.find))
            if c == REF_COMBO['r']:
                _refuse_ref3(c)
            elif c in RIGHT_COMBOS:
                rex.add(c)
            else:
                print(f"排除表忽略非法右组合: {line!r}")
    return lex, rex

_EX_L, _EX_R = load_excluded()
LEFT_ACTIVE  = [c for c in LEFT_COMBOS  if c not in _EX_L]   # 正式采样/练习空间
RIGHT_ACTIVE = [c for c in RIGHT_COMBOS if c not in _EX_R]

def refresh_excluded(path=EXCLUDE_PATH):
    """动态重载排除表 (v2.8: 采集中由 分析-难度剔除.py 改写, 工具定期刷新)"""
    global _EX_L, _EX_R, LEFT_ACTIVE, RIGHT_ACTIVE
    lex, rex = load_excluded(path)
    if lex == _EX_L and rex == _EX_R:
        return False
    _EX_L, _EX_R = lex, rex
    LEFT_ACTIVE  = [c for c in LEFT_COMBOS  if c not in _EX_L]
    RIGHT_ACTIVE = [c for c in RIGHT_COMBOS if c not in _EX_R]
    return True

# ── 组合降权表 (③ 软降权: 疑似出局 → 采样权重 ×系数; 2026-09-30) ──
WEIGHT_PATH = BASE / "组合降权表.txt"

def load_weights(path=WEIGHT_PATH):
    """组合降权表 (`组合<TAB>权重`, # 注释) → {组合: 系数}; 权重 1 = 不降权。
    非法行/超界值容忍 (打印并忽略); 权重 0 视为"要硬剔", 请改用排除表 ⇒ 这里忽略之。"""
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        low = line.strip().lower()
        if low.startswith("#"):
            continue
        # 只按空白切分: 逗号是合法键名 (右手 ",/"/";," 等双键), 不能当分隔符替换掉
        parts = line.split("#")[0].split()
        if not parts:
            continue
        if len(parts) != 2:
            print(f"降权表忽略无法解析的行: {line!r}")
            continue
        s, w = parts[0], parts[1]
        if len(set(s)) != len(s) or not set(s) <= KEYS:
            print(f"降权表忽略无效行: {line!r}")
            continue
        c = (''.join(sorted(s, key=LEFT.find)) if set(s) <= LEFT_SET
             else ''.join(sorted(s, key=RIGHT.find)))
        if c not in LEFT_COMBOS and c not in RIGHT_COMBOS:
            print(f"降权表忽略非法组合: {line!r}")
            continue
        try:
            f = float(w)
        except ValueError:
            print(f"降权表忽略非数值权重: {line!r}")
            continue
        if not 0.0 < f <= 1.0:
            print(f"降权表权重须在 (0,1] (剔除请用排除表): {line!r}")
            continue
        out[c] = f
    return out

_WEIGHTS = load_weights()

def refresh_weights(path=WEIGHT_PATH):
    """动态重载降权表 (与分析-难度剔除.py 的改写同步; 每 REFRESH_EVERY 试次)"""
    global _WEIGHTS
    w = load_weights(path)
    if w == _WEIGHTS:
        return False
    _WEIGHTS = w
    return True

HEADER = (["code"]
          + [f"{h}{p}{k}" for k in range(1, N_STROKES+1) for h in "lr" for p in ("fd","ld","fu","lu")]
          + ["error", "err_type", "actual", "trial", "session"])
PRACTICE_HEADER = ["code", "fd", "ld", "fu", "lu", "error", "err_type", "actual",
                   "trial", "session"]

def load_counts(path):
    """已有数据 → (手内转移计数, 手内单击计数) — 欠样本加权采样用
    1 击行只计单击 (孤立试次), 2 击行计首击单击 + 击对"""
    hand_pairs, hand_singles = defaultdict(int), defaultdict(int)
    if not Path(path).exists():
        return hand_pairs, hand_singles
    with open(path, encoding="utf-8") as f:
        hdr = f.readline().rstrip("\n").split("\t")
        ci = hdr.index("code") if "code" in hdr else 0
        for line in f:
            row = line.strip().split("\t")
            if len(row) <= ci:
                continue
            strokes = row[ci].split("|")
            if not strokes[0]:
                continue
            for h, side in (('l', LEFT_SET), ('r', RIGHT_SET)):
                cs = [''.join(c for c in s if c in side) for s in strokes]
                if not cs[0]:
                    continue
                hand_singles[(h, cs[0])] += 1
                if len(cs) > 1 and cs[1]:
                    hand_pairs[(h, cs[0], cs[1])] += 1
    return hand_pairs, hand_singles

def _left_part(s):
    return ''.join(c for c in s if c in LEFT_SET)

def _right_part(s):
    return ''.join(c for c in s if c in RIGHT_SET)

def load_hand_totals(path, ok_only=HAND_COUNT_OK_ONLY):
    """已有数据 → {'l': n, 'r': n} (该手参与过的试次数) —— 左右 1:1 增补用
    默认只算成功试次 (判据吃成功试次 ⇒ 直接对齐"证据量"; 错误试次两边都扣)"""
    tot = {'l': 0, 'r': 0}
    if not Path(path).exists():
        return tot
    with open(path, encoding="utf-8") as f:
        hdr = f.readline().rstrip("\n").split("\t")
        ci = hdr.index("code") if "code" in hdr else 0
        ei = hdr.index("error") if "error" in hdr else None
        for line in f:
            row = line.strip().split("\t")
            if len(row) <= ci or not row[ci]:
                continue
            if ok_only and ei is not None and len(row) > ei and row[ei] != "0":
                continue
            for h, side in (('l', LEFT_SET), ('r', RIGHT_SET)):
                if any(any(ch in side for ch in s) for s in row[ci].split("|")):
                    tot[h] += 1
    return tot

# ── 练习进度持久化 ──
def load_progress():
    """练习进度 {组合: n}; 兼容旧格式 {组合: {"n":…}}"""
    if PRACTICE_JSON.exists():
        with open(PRACTICE_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_progress(d):
    with open(PRACTICE_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1, sort_keys=True)

def scan_hand_counts(path=None):
    """扫 `当量数据.tsv` → {手: [成功行数, 样本行数]} (v2.44 顶部计数行的**初值**)

    口径: **文件是唯一真相** (铁律 1) —— 不新建持久计数器 (会与文件漂移), 启动时现扫一遍,
    之后每落一行在内存里累加。手别取 `code` 首击 (构造上必然单手); `error=0` 记成功。
    文件不存在/列数不符/组合跨手 的行一律跳过 (不猜)。练习模式写的是 `练习数据.tsv`,
    不进这个计数 (练习数据不进模型, 铁律 1)。"""
    cnt = {'l': [0, 0], 'r': [0, 0]}
    p = Path(path) if path is not None else OUT
    if not p.exists():
        return cnt
    for line in p.read_text(encoding="utf-8").splitlines()[1:]:      # [0] = 表头
        f = line.split("\t")
        if len(f) != len(HEADER) or not f[0]:
            continue
        first = f[0].split("|")[0]
        h = 'l' if set(first) <= LEFT_SET else ('r' if set(first) <= RIGHT_SET else None)
        if h is None:
            continue
        cnt[h][1] += 1
        cnt[h][0] += 1 if f[17] == "0" else 0
    return cnt


class ChordSpeedTest:
    def __init__(self, practice=False, root=None, merge=True, ime=True):
        self.practice = practice
        self._running = False                  # 周期任务开关 (退出/测试收尾时置 False; v2.47)
        self.merge = merge                     # 两击合并为一张键位图 (v2.26 默认; --split 关掉)
        self._ime = bool(ime)                  # 输入层开关 (v2.48; --no-ime 关掉 ⇒ 回到修复前)
        self.root = root or tk.Tk()
        self.root.configure(bg="#1e1e1e")

        self.total_trials = 0
        self.recorded = 0
        self.code_strokes = []
        self.st = None
        self.phase = "waiting"
        self._next_handle = None               # 延迟调度句柄 (冒烟测试可 _cancel_next 清掉)
        # 表头标志: 文件"存在且非空"才算已写 (空的残留文件/预创建文件需补写表头)
        self._header_written = OUT.exists() and OUT.stat().st_size > 0
        self._practice_header_written = PRACTICE_OUT.exists() and PRACTICE_OUT.stat().st_size > 0
        self.hand_pairs, self.hand_singles = load_counts(OUT)
        self.hand_totals = load_hand_totals(OUT)      # 左右 1:1 增补的累计计数
        # 顶部计数行 (v2.44): 每手 **成功数/样本数** —— 从数据文件现扫 (文件是唯一真相)
        self.hand_counts = scan_hand_counts(OUT)
        # 开局握手 = 落后的一侧 (首次运行 0:0 → 左手); 此后每试次按增补规则重抽
        self.hand = "right" if self.hand_totals['l'] >= self.hand_totals['r'] else "left"
        self.down = set()                      # GUI 级物理按下键集 (跨试次; 防自动重复误判)
        # ── 静默失联防护 (v2.37, 2026-10-11 用户报"一击后界面卡住不动") ──
        # 症状: 界面停在原试次、按键无反应、**一条数据都没落盘**。旧版这些都是**静默**的:
        #   ① `_poll_hook` 的按键分发一旦抛异常, 轮询链**再也不重排** ⇒ 键盘彻底失联
        #      (v2.47 随钩子层删除; 现在由 `on_press`/`on_release` 内的异常隔离承担同一条保证);
        #   ② `_record` 写盘失败 (OneDrive/杀软/Excel 占用) 同样会打断控制流, 且不提示;
        #   ③ `_start_next` 抛异常会让 phase 永久停在 "blocked" (此后按键被静默忽略);
        #   ④ 窗口不在前台时按键进不了采集器 ⇒ 界面"按了没反应"却毫无提示。
        # 现在: ①②③ 一律隔离 + 可见告警 (见 `_report_error`), ④ 靠**启动抢前台** + 看门狗兜底。
        self.err_count = 0                     # 内部错误次数 (已隔离, 界面显示)
        self.save_failures = 0                 # 落盘失败行数 (未保存的试次, 界面显示)
        self.key_events = 0                    # 本会话收到的按键事件数 (v2.43: 随控制台报错行输出)
        self._last_err = ""                    # 最近一次内部错误 (一行摘要)
        self._last_key_ts = time.perf_counter()  # 最后一次收到按键的时刻 (看门狗用; v2.38)
        raw = load_progress()                  # 兼容旧格式 {组合: {"n":…}}
        self.progress = {c: (v if isinstance(v, int) else v.get("n", 0))
                         for c, v in raw.items()}
        self.session_id = time.strftime("%Y%m%d-%H%M%S")

        self.root.bind("<KeyPress>", self.on_press)
        self.root.bind("<KeyRelease>", self.on_release)

        # ── 布局 (v2.43 精简 / v2.44 顶部计数 / v2.45 帮助面板) ──
        # 界面上只剩两行文字: 顶部 `左 成功/样本 : 右 成功/样本` (v2.44) 与底部 `Trial N` (v2.41);
        # 记法说明 (圈/叉各指哪一击) 与全部操作细节都收进 **`?` 说明书** (v2.45, 点开才占地方)。
        self.label_hands = tk.Label(self.root, text="", font=("Consolas", 12),
                                     fg="#888", bg="#1e1e1e")
        self.label_hands.pack(pady=(10, 2))

        kb_frame = tk.Frame(self.root, bg="#1e1e1e")
        kb_frame.pack(pady=(2, 4))
        self._build_keyboards(kb_frame)

        self.label_info = tk.Label(self.root, text="", font=("Consolas", 14),
                                    fg="#ccc", bg="#1e1e1e")
        self.label_info.pack(pady=(6, 2))
        # 告警行 (v2.43 精简): 只留**真问题** (内部错误 / 落盘失败 —— 都意味着数据或流程出事了);
        # "窗口未获焦点"与"试次久未完成"两条提醒按用户决策删除 (采集者自己看得见屏幕, 不需要
        # 程序反复念; 底层防护不变: 启动抢前台、看门狗自动收尾、异常隔离都还在)。
        self.label_warn = tk.Label(self.root, text="", font=("Consolas", 12),
                                    fg="#ff7b72", bg="#1e1e1e")
        self.label_warn.pack(pady=2)
        self.label_block = tk.Label(self.root, text="", font=("Consolas", 10),
                                     fg="#555", bg="#1e1e1e")
        self.label_block.pack(pady=(2, 12))

        self._build_help()                     # `?` 图标 + 说明书面板 (v2.45)

        self._fit_geometry()
        self._set_window_title()
        self._update_hand_counts()             # 顶部计数行: 左 成功/样本 : 右 成功/样本 (v2.44)
        self._write_header()
        self._startup_report()
        self.new_code()
        self.root.focus_set()
        self._setup_input()                    # 输入层: 无视输入法 (v2.24)
        self._focus_guard()                    # 前台跟踪 + 看门狗 (v2.37/v2.38; 不再出提示行)

    # ── 键位图 (v2.26): 两击合并成一张 (默认) / --split 回退上下两块 ──
    def _build_keyboards(self, kb_frame):
        """合并图 (默认): **只有一块键盘** —— v2.45 起**图例行删除**: 记法说明 (「圈 = 第 1 击 /
        叉 = 第 2 击 / 圈里一个叉 = 两击共用」) 收进 `?` 说明书 (`_toggle_manual`), 界面上只留
        "要打什么" + 顶部计数行 + 底部 `Trial N`。图形规则在 KeyboardCanvas._paint (唯一源)。
        --split: 旧布局 (2026-09-29) = 两击上下两块键盘 + 标题 + ↓ 箭头, 兼容旧协议
        (那两块图各自带"第 1 击/第 2 击"标题 —— 它标的是**块**, 不是记法, 保留)。"""
        if self.merge:
            self.kb = KeyboardCanvas(kb_frame)
            self.kb.grid(row=0, column=0)
            return
        for idx in (0, 1):
            cap = tk.Label(kb_frame, text=f"第 {idx+1} 击", font=("Consolas", 12),
                           fg=KEY_MARK, bg="#1e1e1e")
            cap.grid(row=idx*3, column=0, pady=(0, 4))
            kb = KeyboardCanvas(kb_frame)
            kb.grid(row=idx*3 + 1, column=0)
            setattr(self, f"kb{idx+1}", kb)
        tk.Label(kb_frame, text="↓", font=("Consolas", 20), fg="#666",
                 bg="#1e1e1e").grid(row=2, column=0)

    def _fit_geometry(self):
        """窗口 = 内容需求 (布局一改就不用再手改常数: 硬编码会过期 → 标签被裁; 冒烟有断言)"""
        self.root.update_idletasks()
        w = max(520, self.root.winfo_reqwidth())        # 宽度下限: 键盘 428 + 余量
        h = self.root.winfo_reqheight() + 16            # 高度: 内容 + 一点余量 (合并图比两图矮很多)
        self.root.geometry(f"{w}x{h}")
        # ⚠ 只做几何 —— 报告/取目标/装输入层只在 __init__ 尾部走一次:
        #   曾误把初始化尾部粘进这里 ⇒ _setup_input 跑两遍 (当时 = 低层键盘钩子装了两道,
        #   第一道成孤儿钩装着吞键却无人消费, `stop_hook` 也只卸最后一道) + 启动报告打印两遍。
        #   钩子已于 v2.47 删除, 但这条教训仍适用: 重复初始化会重复挂周期任务/重复抢前台。

    # ── 输入层 (v2.47): **只保留"摘除窗口 IME"** ⇒ 无视输入法状态 ──
    # 背景 (2026-10-01 用户实测): 输入法处于中文态时, 字母先被 IME 拿去组字, tkinter 只收到
    #   keysym='??' / char='' 的 <KeyPress> ⇒ 采集器判定"没有按键"; 且 IME 会输出汉字/弹候选框。
    #   解法 = 摘除本窗口 IME 上下文 (v2.24 的第②层, 现在是唯一一层) —— 本窗口不组字/不弹候选框,
    #   Tk 直接收到干净字母; 按键来源 = tkinter 事件绑定 (一直是回退路径, 现为主路径)。
    #   复现与验证脚本: 实验/实验-IME按键捕获.py (真实注入按键)
    # v2.48: `--no-ime` 排障开关 (= 姊妹项目 `采集输入层.py` 的 `--no-ime`, 2026-10-12 同步) ——
    #   整体关掉这一层 ⇒ 回到**修复前**行为 (一点不碰输入法; 中文态下将收不到按键), 用于现场
    #   A/B (证明这层真在起作用) 与二分定位"打字没反应"是不是输入层造成的。不改事件源与计时取法。
    def _setup_input(self):
        """装输入层 (v2.47 起只有一条): 摘除本窗口 IME ⇒ tkinter 直接收干净字母
        (v2.48: `ime=False` = 完全不摘, 回到修复前)"""
        if self._ime:
            n = ime_detach(self.root) if IS_WINDOWS else 0
            print("  · IME(窗口级): " + ("已摘除本窗口输入上下文 (不组字/不弹候选框; 中文态照样可采)"
                                         if n else "本窗口无输入法上下文 (无需摘除)"))
        else:
            print("  · IME(窗口级): --no-ime 已关闭 ⇒ 不摘除输入法, 回到修复前 "
                  "(中文输入法态下可能收不到按键; 排障用)")
        print("  · 按键捕获: tkinter 事件 (<KeyPress>/<KeyRelease>; v2.47 起无键盘钩子) "
              "—— 窗口需保持前台/焦点 (非前台时按键到别的窗口, 采不到)")
        self._running = True
        self.root.bind("<FocusIn>", self._on_focus_in)
        self.root.bind("<FocusOut>", self._on_focus_out)
        # 启动抢一次系统前台 (v2.37): 没有钩子后**按键只到有焦点的窗口** —— 新建窗口并不总能拿到
        # 前台 (前台锁), 那就会"打字没反应、界面像卡住、数据不落"。窗口不可见 (冒烟/隐藏) 时不抢。
        if IS_WINDOWS and self.root.winfo_viewable():
            print("  · 前台: " + ("已取得 (现在可以直接打字)" if claim_foreground(self.root)
                                 else "⚠ 未取得 —— 请点一下本窗口再打"))
        if self._ime:                          # --no-ime: 连周期重摘也不起 (这一层整体不存在)
            self._ime_guard()

    def _on_focus_in(self, event=None):
        """窗口激活: 系统可能重新关联输入法上下文 ⇒ 重摘一次 (很便宜; `--no-ime` 时不做)"""
        if IS_WINDOWS and self._ime:
            ime_detach(self.root)

    def _on_focus_out(self, event=None):
        """失焦: 清空物理按下集 —— 失焦期间的 keyup 会落到别的窗口, 否则该键永久卡住"""
        self.down.clear()

    def _focus_guard(self):
        """每 500ms 跑一次: ① 看门狗**只在本窗口前台时才动试次** (用户离开就别收尾 —— 他可能
        正要去别的窗口看一眼再回来; 非前台时按键到别的窗口 ⇒ 本就收不到);
        ② (v2.43 起不再出焦点/超时提示行 —— 用户决策: 采集者看得见自己的屏幕)。

        ⚠ 这条周期任务**必须一直活着**: `_stuck_guard` 是"收不了尾"的自愈路径 (v2.38),
        没有它就会出现"界面停在原试次、按键无反应、连错误行都不落盘"的永久卡死。"""
        if not self._running:
            return
        fg = app_is_foreground() if IS_WINDOWS else True
        if fg:
            self._stuck_guard()
        self.root.after(500, self._focus_guard)

    def _stuck_guard(self):
        """看门狗 (v2.38, 2026-10-11 用户实测"快打时偶发界面卡住"): 采集器**绝不能永久卡住**。

        两条"收不了尾"路径都必须自愈 —— 它们的现象完全一样 (界面停在原试次、按键无反应、
        **连错误行都不落盘**), 而用户只会以为程序卡了一下, 不知道自己在等什么:
        ① **错误捕获态** (R1/R2/R3) 按 2026-09-29 的语义要**所有键都放开**才收尾。快打/滚动按键
           (下一键按下时上一键还没全放) 会长时间保持"有键按住" ⇒ 试次永不结束。用户往往还在
           等程序反应、手没离开键 ⇒ 永久卡住。**静默 5s 即视为停手**: 视同全放 → 错误行照常落盘。
        ② 正常试次里若某个键的"松开"事件丢了 (焦点切换/事件丢失), 也会永远等下去 ⇒ 20s 后按
           "已全放"收尾 (与 800ms `_force_advance` 同口径: 落 ok 行, 缺松开锚的段分析侧本就丢弃)。"""
        if self.st is None or self.st.done:
            return
        idle = time.perf_counter() - self._last_key_ts
        if self.st.error and self.st.capturing:
            if idle > CAPTURE_STUCK_S:
                self.st.held.clear()            # 视同"全部放开" (物理状态 self.down 不动)
                self.st.done = True
                print(f"⚠ 错误捕获态静默 {idle:.1f}s → 自动收尾 (视为已全放; 错误行照常落盘, "
                      f"不再是永久卡住)", file=sys.stderr, flush=True)
                self._record(ok=False)
                self._schedule_next()
        elif self.phase == "typing" and not self.st.error and idle > TRIAL_STUCK_S:
            self.st.done = True
            print(f"⚠ 试次静默 {idle:.1f}s (疑似漏收松开事件) → 自动收尾", file=sys.stderr, flush=True)
            self._record(ok=True)
            self._schedule_next()

    def _err_text(self):
        """错误提示 (v2.38): 捕获态要**明确告诉用户怎么脱身** —— 旧版只说 "✗ R1 …",
        用户不知道程序在等"所有键放开", 于是按更多键/手不离键 ⇒ 永久卡住。"""
        t = "✗ " + (self.st.error or "")
        return t + "（全部松开即继续）" if (self.st is not None and self.st.capturing) else t

    def _refresh_warn(self):
        """告警行 (v2.43 精简) = **只报真问题**: 内部错误 / 落盘失败 —— 两者都意味着"数据可能
        少了一段"或"流程出过事", 必须当场看得见。
        (v2.37 的"窗口未获焦点"与"试次久未完成"两条提示**已按用户决策删除** —— 采集者本人
        看得见屏幕与自己的手; 底层防护不受影响: 启动抢前台、看门狗自动收尾、异常隔离仍在。)"""
        if not hasattr(self, "label_warn"):
            return
        msgs = []
        if self.err_count:
            msgs.append(f"⚠ 内部错误×{self.err_count}: {self._last_err} (已跳过, 全栈见控制台)")
        if self.save_failures:
            msgs.append(f"⚠ 落盘失败 {self.save_failures} 行 —— 这些试次没有保存")
        self.label_warn.config(text="  ｜  ".join(msgs))

    def _report_error(self, where, exc=None):
        """内部错误统一上报 (v2.37): 控制台打全栈 + 界面状态行显示 —— 一切静默失败都变成可见。

        设计原则: 采集器**绝不能因为一个内部错误而静默停摆** (用户会以为只是"卡了一下",
        继续盲打, 结果那段时间的试次全丢)。错误一律隔离, 流程照常推进, 但必须看得见。"""
        self.err_count += 1
        detail = f"{type(exc).__name__}: {exc}" if exc is not None else "见控制台"
        self._last_err = f"{where} → {detail}"
        # 本会话按键流计数随错误一起打到控制台 (v2.43: 界面上的计数行已删) —— "按键在涨 =
        # 键到了采集器 (问题在判分/落盘); 不涨 = 键根本没进来 (焦点/钩子)" 这条诊断仍可查
        print(f"⚠ [{where}] 内部错误 (第 {self.err_count} 次, 已跳过并继续运行): {detail}"
              f" ｜ 本会话已收按键 {self.key_events}", file=sys.stderr, flush=True)
        traceback.print_exc()
        try:
            self._refresh_warn()
        except Exception:
            pass                       # 界面不可用也不能让上报本身成为新的异常源

    def _append_line(self, path, row):
        """追加一行; 落盘失败**不中断采集** (v2.37) —— 旧版直接抛, 一次 OneDrive/杀软/Excel
        占用就能让界面静默卡死。失败时返回 False (调用方据此不推进采样计数), 并明确告警:
        这些试次**没有保存**, 用户当场就该知道, 而不是事后才发现数据缺了一段。"""
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("\t".join(row) + "\n")
            return True
        except OSError as exc:
            self.save_failures += 1
            self._report_error(f"落盘 {Path(path).name}", exc)
            return False

    def _ime_guard(self):
        """每 2 秒重摘一次窗口 IME (激活/切换输入法后系统会重新关联; 双保险)

        ⚠ 只在 `self._ime` 为真时被 `_setup_input` 起链 (v2.48): `--no-ime` 下这条周期任务
        整体不存在 —— 不是"起了链但空转", 而是根本没有输入层这回事 (函数自身也判 `self._ime`,
        所以就算被误调也不会摘)。链尾 `after` 由 `_running` 兜底停住 (与 `_focus_guard` 同生命周期)。"""
        if not self._running or not self._ime:
            return
        if IS_WINDOWS:
            ime_detach(self.root)
        self.root.after(2000, self._ime_guard)

    def stop_guards(self):
        """停掉周期任务与 IME 重摘 (退出前必调; v2.47 前这里卸的是键盘钩子)

        ⚠ `_running = False` 之后 `_focus_guard` / `_ime_guard` 的下一次 `after` 回调直接返回
        ⇒ 周期任务链止住 (否则同一进程里连续冒烟三次会叠三套看门狗)。"""
        self._running = False

    # ── 表头 ──
    def _write_header(self):
        """正式数据表头 (仅当文件不存在时写一次; 缺表头会让分析脚本错读首行)"""
        if not self._header_written:
            with open(OUT, "a", encoding="utf-8") as f:
                f.write("\t".join(HEADER) + "\n")
            self._header_written = True

    # ── 采集手 (唯一模式: 每试次随机单手 + 1:1 增补) ──
    def choose_hand(self, rng=random):
        """本试次该采哪只手 → 'left'/'right'
        左右 1:1 **增补** (HAND_TARGET/hand_probability): 每试次独立抽, 落后的一侧概率被推高
        ⇒ 先还历史欠账, 之后自我纠偏, 且两侧始终交错出现 (练习效应对称)。
        v2.23: 固定单手模式已移除 (方案要求左右对称 + 双手交集剔除要求两手有同期数据)。"""
        return "right" if rng.random() < hand_probability(self.hand_totals['l'],
                                                          self.hand_totals['r']) else "left"

    def _set_window_title(self):
        """窗口标题 = 采集手 + 练习态 (v2.43: 界面上的标题/平衡行已删 ⇒ 这是"哪只手"的文字落点;
        手别其实也由图本身给出 —— 键位图只画采集手那一半)"""
        hand_txt = {"left": "左手", "right": "右手"}[self.hand]
        mode = ("练习 · " if self.practice else "") + hand_txt + " ⟳"
        self.root.title(f"并击击键测速（{mode}）")

    def _update_hand_counts(self):
        """顶部计数行 (v2.44): `左 成功/样本 : 右 成功/样本` —— 成功 = `error=0` 的**已落盘**行,
        样本 = 该手全部**已落盘**行 (落盘失败的行两个数都不加: 文件里没有的不算证据);
        口径 = `scan_hand_counts` (启动现扫数据文件) + 每落一行累加; 练习数据不计。"""
        l, r = self.hand_counts['l'], self.hand_counts['r']
        self.label_hands.config(text=f"左 {l[0]}/{l[1]} : 右 {r[0]}/{r[1]}")

    # ── `?` 说明书 (v2.45, 2026-10-12 用户决策"用法单独写一个说明书…放一个问号图标, 点击可以展开说明") ──
    def _build_help(self):
        """右上角 `?` 图标 + 说明书抽屉 (默认收起, 点开才占地方)。

        说明书是**独立文档** `采集器说明书.md` (项目根, 与代码同目录 ⇒ 整目录可迁移) ——
        界面只负责**显示**它, 不在代码里再抄一份内容 (抄一份 = 迟早与文档漂移)。"""
        self.manual_open = False
        self._manual_loaded = False
        self.manual_frame = tk.Frame(self.root, bg="#1e1e1e")
        self.manual_text = tk.Text(self.manual_frame, width=62, height=17, wrap="word",
                                   font=("Consolas", 10), fg="#bbb", bg="#141414",
                                   relief="flat", highlightthickness=0, padx=10, pady=6,
                                   cursor="arrow")
        self.manual_text.tag_configure("h", font=("Consolas", 12, "bold"),
                                       foreground="#f0f0f0", spacing1=6, spacing3=2)
        bar = tk.Scrollbar(self.manual_frame, command=self.manual_text.yview)
        self.manual_text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.manual_text.pack(side="left", fill="both", expand=True)
        # 图标 = 小圆圈 + "?" (与键位图同为"圆"语言); place 到右上角 (窗口长高也贴角)
        self.btn_help = tk.Canvas(self.root, width=20, height=20, bg="#1e1e1e",
                                  highlightthickness=0, cursor="hand2")
        self._help_ring = self.btn_help.create_oval(2, 2, 18, 18, outline="#555", width=1)
        self.btn_help.create_text(10, 10, text="?", fill="#999", font=("Consolas", 11, "bold"))
        self.btn_help.place(relx=1.0, x=-8, y=8, anchor="ne")
        self.btn_help.bind("<Button-1>", self._toggle_manual)

    def _toggle_manual(self, _ev=None):
        """点 `?`: 展开/收起说明书 (首次展开才读盘)。展开态与收起态都会 `_fit_geometry` 调窗口。

        ⚠ 读不到说明书文件时**在面板里明说路径** (不静默空着) —— 与 v2.37 那条教训一致:
        "看不见的失败"必须变成看得见的。"""
        if self.manual_open:
            self.manual_frame.pack_forget()
            self.manual_open = False
        else:
            if not self._manual_loaded:
                self.manual_text.configure(state="normal")
                self.manual_text.delete("1.0", "end")
                self._render_manual(self._read_manual())
                self.manual_text.configure(state="disabled")
                self._manual_loaded = True
            self.manual_frame.pack(pady=(2, 4))
            self.manual_open = True
        self.btn_help.itemconfig(self._help_ring,
                                outline="#999" if self.manual_open else "#555")  # 图标高亮 = 已展开
        self._fit_geometry()

    def _read_manual(self):
        """说明书正文 (Markdown) = `采集器说明书.md` (项目根); 缺失/读失败 → 返回可见的提示文本"""
        path = BASE / "采集器说明书.md"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            return (f"# 读不到说明书\n\n{path}\n\n{type(exc).__name__}: {exc}\n\n"
                    "请确认项目根下存在 `采集器说明书.md`（与 采集-并击当量.py 同目录）。")

    def _render_manual(self, md):
        """极简 Markdown → Text: 只认 `#` 标题 / `-`·`*` 列表 / 空行, 并去掉 `**` 与反引号。

        刻意不做完整解析 —— 说明书是给人看的, 少量规则够用, 且**不会因为语法扩展而显示失真**。"""
        t = self.manual_text
        for raw in md.splitlines():
            line = raw.rstrip()
            if not line:
                t.insert("end", "\n")
            elif line.startswith("#"):
                t.insert("end", line.lstrip("# ").replace("**", "") + "\n", "h")
            elif line.lstrip()[:2] in ("- ", "* "):
                t.insert("end", "    • " + line.lstrip()[2:].replace("**", "") + "\n")
            else:
                t.insert("end", line.replace("**", "").replace("`", "") + "\n")

    # ── 组合空间 / 练习进度 ──
    def _combos_of_hand(self, h):
        return LEFT_ACTIVE if h == 'l' else RIGHT_ACTIVE

    def _combos_all(self, h):
        return LEFT_COMBOS if h == 'l' else RIGHT_COMBOS

    def _n_practiced(self, combo):
        return self.progress.get(combo, 0)

    def _startup_report(self):
        print("  · 键位图: " + ("两击**合并为一张**, **图形区分击序** (v2.40: 第 1 击 = 圈 / "
                               "第 2 击 = 叉<长 = 圈直径, 端点落在圈上> / 共有 = 圈里一个叉; "
                               "标记统一白色, 按下 = 加粗高亮、松开恢复; **不提示当前击次** <v2.41; v2.45 起**无图例行**, "
                               "记法说明见右上 `?` (采集器说明书.md)> "
                               "—— v2.26 合并 + "
                               "v2.32 圆形键帽 + v2.31 半边键盘, --split 可回到两图"
                               if self.merge else
                               "两击**上下两块**图 (旧布局 2026-09-29; v2.26 默认已改合并; "
                               "v2.40 上块 = 圈 / 下块 = 叉)"))
        h = 'l' if self.hand == "left" else 'r'
        act = self._combos_of_hand(h)
        ref = REF_COMBO[h]
        print(f"组合空间({h}手): {len(act)} 活跃 / {len(self._combos_all(h))} 合法"
              f" (3 键组合 {ref} 与 2 键同比例 ×{REF_BOOST:g}; 2026-09-30 起不再加权)")
        dw = {c: _WEIGHTS[c] for c in act if _WEIGHTS.get(c, 1.0) < 1.0}
        if dw:
            print(f"软降权(③): {h}手 {len(dw)} 个组合按 组合降权表.txt 降权 "
                  f"(疑似出局, ×{min(dw.values()):g}~{max(dw.values()):g}; 可回滚)")
        if self.practice:
            touched = sum(1 for c in act if self._n_practiced(c) > 0)
            total = sum(self._n_practiced(c) for c in act)
            print(f"练习模式(热身): 已练 {touched}/{len(act)} 组合, 共 {total} 次"
                  f" (轮转 = 练得最少的优先; 难度判定不依赖练习数据, §4.5)")
        else:
            print(f"正式采集: 混采 1击:2击 = {MIX_ONE_TWO[0]}:{MIX_ONE_TWO[1]}"
                  f" (P(1击)={MIX_ONE_TWO[0]/sum(MIX_ONE_TWO):.0%})；练习段由稳定期方法剔除"
                  f" (分析-难度剔除.py 动态维护排除表)")
            print("  · 采集手 = 左右 1:1 随机单手 (v2.23 起无固定单手开关; 每试次抽边, 增补落后侧)")
            n_l, n_r = self.hand_totals['l'], self.hand_totals['r']
            print(f"  · 左右手 1:1 混采 + 增补: 已采 左 {n_l} : 右 {n_r} (目标 "
                  f"{HAND_TARGET[0]}:{HAND_TARGET[1]}) → 本试次 P(右)={hand_probability(n_l, n_r):.2f}"
                  f" (偏置上限 ±{HAND_MAX_SKEW:g}; 两侧始终交错 ⇒ 练习效应对称)")

    def _next_practice_combo(self):
        """练习轮转: 练得最少的组合优先 (均匀覆盖; 不设达标判据)"""
        h = 'l' if self.hand == "left" else 'r'
        return min(self._combos_of_hand(h), key=lambda c: (self._n_practiced(c), c))

    # ── 采样 ──
    def _combo_w(self, combo):
        """结构权重 (单键:双键:三键 = 2:1:1) × **软降权系数** (③; 未列入降权表 = 1.0)。
        2026-09-30: 3 键组合不再额外加权; 疑似出局的组合按 组合降权表.txt 降权 (可回滚)。
        (v2.39 清理: 旧签名多一个从未使用的 `h` 参数)"""
        return COMBO_W[len(combo)] * _WEIGHTS.get(combo, 1.0)

    def _sample_stroke(self, prev=None):
        """该手组合采样: 结构权重(单:双=2:1) × 降权系数 × 转移多样性 1/(n+1)"""
        h = 'l' if self.hand == "left" else 'r'
        pool = self._combos_of_hand(h)
        part = _left_part if h == 'l' else _right_part
        if prev is None:
            cnt = lambda s: self.hand_singles.get((h, part(s)), 0)
        else:
            cnt = lambda s: self.hand_pairs.get((h, part(prev), part(s)), 0)
        weights = [self._combo_w(c) / (cnt(c) + 1) for c in pool]
        return random.choices(pool, weights=weights, k=1)[0]

    def new_code(self):
        self._cancel_release_timeout()
        self._maybe_refresh_excluded()
        new_hand = self.choose_hand()          # 每试次按增补规则抽边 (两侧交错 ⇒ 练习效应对称)
        if new_hand != self.hand:
            self.hand = new_hand
            self._set_window_title()           # v2.43: 手别只写在窗口标题 (界面平衡行已删)
        if self.practice:
            strokes = [self._next_practice_combo()]
        else:
            n = random.choices((1, 2), weights=MIX_ONE_TWO, k=1)[0]   # 混采 1击:2击
            strokes = [self._sample_stroke()]
            for _ in range(n - 1):
                strokes.append(self._sample_stroke(strokes[-1]))
        self.code_strokes = strokes
        self.st = StrokeTrial(strokes)
        self.phase = "waiting"
        self._last_key_ts = time.perf_counter()  # 看门狗从本试次起点计时 (v2.38)
        self._paint_targets()
        self._update_kb()                      # 也负责写试次行 "Trial N" (v2.41) 与按下态
        self.label_info.config(text="")

    def _maybe_refresh_excluded(self):
        """每 REFRESH_EVERY 试次重载 排除表 + 降权表 (分析-难度剔除.py 可随时改写, 即时生效)"""
        if self.total_trials and self.total_trials % REFRESH_EVERY == 0:
            h = 'l' if self.hand == "left" else 'r'
            if refresh_excluded():
                print(f"[trial {self.total_trials}] 排除表已刷新: {h}手活跃组合 "
                      f"{len(self._combos_of_hand(h))}")
            if refresh_weights():
                n_dw = sum(1 for c in self._combos_of_hand(h) if _WEIGHTS.get(c, 1.0) < 1.0)
                print(f"[trial {self.total_trials}] 降权表已刷新: {h}手降权组合 {n_dw} 个 "
                      f"(疑似出局, 可回滚)")

    def _hand_anchor(self, stroke, hand):
        """该击该手 (fd, ld, fu, lu)；该手该击无键 → None (v2.6 三段口径取用)"""
        an = self.st.anchors()
        a = an[(stroke - 1) * 2 + (0 if hand == "l" else 1)]
        return a if a[3] is not None else None

    def _update_kb(self):
        # 试次行 (v2.41, 2026-10-11 用户决策"不需要提示击次了"): **只写 Trial N** —— 圈/叉已把
        # 击序与击数写全 (只圈 = 1 击; 圈+叉 = 2 击, 圈在前叉在后), 不再用文字重复提示。
        self.label_block.config(text=f"Trial {self._trial_num()}")
        # 按下态 = **正按着的键** (held, 松开即灭; v2.32 修) —— 旧用 downs (历史全部按下过
        # 的键, 只增不减), 击 1 的共键一放开就残留在按下集, 击序推进到 2 时瞬间被点亮成
        # "按着"(还没真的按第二击) ⇒ 共键"提前亮"; 普通键也会常亮不灭
        if self.merge:
            # 合并图: 目标由 _paint_targets 一次画好, 这里只更新按下态 (v2.41: 无"当前击"提示)
            self.kb.mark_pressed(set(self.st.held))
            return
        for idx, kb in enumerate((self.kb1, self.kb2)):
            # 两块图各代表一击: 只把"当前击那块"的按下键点亮 (另一块没有按键输入)
            kb.mark_pressed(set(self.st.held)
                            if not (self.st.error or self.st.done) and self.st.si == idx else set())

    def _paint_targets(self):
        """按当前目标画键位图 (合并图: 两击一张; **图形规则在 KeyboardCanvas._paint** ——
        第 1 击 = 圈 / 第 2 击 = 叉 / 共有 = 圈里一个叉, 标记统一白色);
        半边键盘 (v2.31): 只显示本试次采集手那一半, 键位保持原位

        v2.41: 不再有"当前击"状态 ⇒ 本方法只画目标 + 按下集复位, 画布内容**只由击序决定**
        (v2.39/v2.40 曾需要"先 set_active_stroke(0) 再画目标"来消掉逐击上色的中间态;
        现在那条不变量退化成"图形与击序同源", 冒烟仍有"首笔 ≡ 后续状态"断言守着)。"""
        h = 'l' if self.hand == "left" else 'r'
        if self.merge:
            self.kb.set_hand(h)
            self.kb.set_strokes(self.code_strokes)
        else:
            self.kb1.set_hand(h)
            self.kb2.set_hand(h)
            self.kb1.set_targets(self.code_strokes[0], stroke=0)   # 上块 = 第 1 击 ⇒ 圈
            # 下块 = 第 2 击 ⇒ **stroke=1 才画叉** (v2.40; 1 击试次无第二击 → 空)
            self.kb2.set_targets(self.code_strokes[1] if len(self.code_strokes) > 1 else set(),
                                 stroke=1)

    def _disabled_hand(self, ch):
        """非目标手禁用 (v2.35, 2026-10-11 用户决策): 目标键位在左手时禁用右手输入 (防按错),
        反之同理。空格 (跳过) / Escape (退出) 不属于任何手, 不受影响;
        self.hand 未定 (理论上不发生) 时不禁用。"""
        if ch not in KEYS or self.hand not in ("left", "right"):
            return False
        return _hand(ch) != ("l" if self.hand == "left" else "r")

    # ── 按键 (v2.47 起唯一来源 = tkinter 事件绑定; 键名在此归一化后进同一套逻辑) ──
    # 归一化口径: 字母/标点取 `event.char` 的小写 (中文态下 IME 已摘 ⇒ char 就是干净字母);
    # `Escape` 走 keysym (它没有 char); 松开事件 char 可能为空 ⇒ 与按下同样带 keysym 兜底 (v2.39)。
    # ⚠ 异常必须在这里隔离 (v2.37 精神的延续): 一次按键处理出错**绝不能**让采集停摆 ——
    #   上报 (控制台全栈 + 界面告警) 后照常继续收下一个键。
    def on_press(self, event):
        """tkinter <KeyPress>"""
        try:
            key = 'Escape' if event.keysym == 'Escape' else (event.char.lower() or event.keysym)
            self.on_key_down(key)
        except Exception as exc:
            self._report_error("按键处理", exc)

    def on_release(self, event):
        """tkinter <KeyRelease> (v2.39 修: 与按下同样带 keysym 兜底 —— 某些按键的 keyup
        事件 char 为空, 旧版会把键名传成 '' ⇒ 该键永远留在"按下集"里, 卡住后续同一键的输入)"""
        try:
            self.on_key_up(event.char.lower() or event.keysym.lower())
        except Exception as exc:
            self._report_error("按键处理", exc)

    def on_key_down(self, key, t=None):
        """物理按下 (key = 小写字符 / ' ' / 'Escape'; t 缺省则现取 `time.perf_counter()`)"""
        self.key_events += 1                   # 按键流计数 (v2.37 诊断: 键到没到采集器;
                                               #   v2.43 起随控制台报错行输出, 不再占界面)
        self._last_key_ts = time.perf_counter()   # 看门狗用: 有按键 = 用户在场 (v2.38)
        if key == 'Escape':
            self.root.quit()
            return
        ch = key
        if ch and ch in KEYS:
            # 跨试次按键残留防护: 已按下的键再次触发 = 自动重复 (可能跨越出错后的下一试次),
            # 忽略之 — 否则会被当作"按下了不该按的键"产生伪 R1 错误
            if ch in self.down:
                return
            self.down.add(ch)
        # 非目标手禁用 (v2.35, 2026-10-11 用户决策): 目标在左手 → 右手键一律忽略 (防按错)。
        # 只是不进状态机、不产生 R1 (键本身照常由窗口消息处理 —— v2.47 起没有钩子吞键这回事)。
        # self.down 仍跟踪 (上面已加) ⇒ 按住跨试次的自动重复照样被抑制。
        if self._disabled_hand(ch):
            return
        if self.phase == "blocked":
            # v2.38: 试次间隔 (300-800ms) 里按键一律丢弃 —— **必须说出来**。快打时用户会抢在
            # 新目标出现前按键, 那一击被静默丢掉 ⇒ 用户以为自己在打第 1 击、程序却还没开始,
            # 于是"按下的键突然变红"(其实那键是新试次第 2 击的目标) 这类错位。
            if ch in KEYS:
                self.label_info.config(text="⏳ 下一试次还没出现 —— 这一下没有被记录")
            return
        if ch == ' ':
            self.total_trials += 1
            self.label_info.config(text="␣ 已跳过")
            self._schedule_next()
            return
        if not ch or ch not in KEYS:
            return
        t = time.perf_counter() if t is None else t
        if self.phase == "waiting":
            self.phase = "typing"
        self.st.press(ch, t)
        self._update_kb()
        if self.st.error and not self.st.capturing:
            self.label_info.config(text=self._err_text())
            self._record(ok=False)                 # R4: 触发即全放开, 立即收尾
            self._schedule_next()
        elif self.st.error:
            # 错误捕获态: 错误立即提示, 但等全放开才落盘 (actual 才含完整错误组合)
            self.label_info.config(text=self._err_text())
        elif self.st.final_formed and not self.st.done:
            if not hasattr(self, "_release_timeout"):
                self._release_timeout = self.root.after(800, self._force_advance)

    def on_key_up(self, key, t=None):
        """物理松开 (与 on_key_down 同一套归一化键名)"""
        ch = key
        self._last_key_ts = time.perf_counter()   # 看门狗用 (松开也算用户在场; v2.38)
        if not ch or ch not in KEYS:
            return
        self.down.discard(ch)            # 物理状态始终跟踪 (含 blocked 期间)
        if self._disabled_hand(ch):      # 非目标手: 松开同样忽略 (按下已被忽略)
            return
        if self.phase != "typing":
            return
        self.st.release(ch, time.perf_counter() if t is None else t)
        self._update_kb()
        if self.st.error:
            self.label_info.config(text=self._err_text())
            if self.st.done or not self.st.capturing:
                self._record(ok=False)             # 捕获完成 (全放开) 或 R4 → 落盘
                self._schedule_next()
        elif self.st.done:
            if self.practice:
                self._on_practice_done()
            else:
                h = 'l' if self.hand == "left" else 'r'
                a1 = self._hand_anchor(1, h)
                a2 = self._hand_anchor(2, h)
                if a1 is None:          # 防御: 该手本试次无键 (正常流程不会发生, 采样恒属当前手)
                    h = 'r' if h == 'l' else 'l'
                    a1 = self._hand_anchor(1, h)
                    a2 = self._hand_anchor(2, h)
                if a1 is None:          # 两只手都没有锚 (异常) → 只报完成, 不报 ms
                    self.label_info.config(text="✓")
                elif a2:    # 二击词: wc = S1+S2+S3 = fd1→lu2
                    # 三段各自取整后再相加当总时间 —— 保证屏幕上"a+b+c=?"算式自洽
                    # (真值 wc 用的是未取整浮点并照常落盘, 显示取整只差 <1.5ms)
                    s1 = round((a1[3] - a1[0]) * 1000)
                    s2 = round((a2[0] - a1[3]) * 1000)
                    s3 = round((a2[3] - a2[0]) * 1000)
                    self.label_info.config(text=f"{s1}+{s2}+{s3}={s1 + s2 + s3}ms")
                else:       # 一击词: 孤立占用 occ = fd→lu
                    self.label_info.config(text=f"{round((a1[3] - a1[0]) * 1000)}ms")
            self._record(ok=True)
            self._schedule_next()

    # ── 练习模式 (热身): 只记次数量与散布, 不设判据 ──
    def _on_practice_done(self):
        combo = self.code_strokes[0]
        a = self.st.anchors()[0 if self.hand == "left" else 1]
        if a[0] is None:                   # 防御: 该手本试次无键 (正常流程不会发生)
            a = self.st.anchors()[1 if self.hand == "left" else 0]
        fd, lu = a[0], a[3]
        self.progress[combo] = self._n_practiced(combo) + 1
        save_progress(self.progress)
        # 提示与正式采集同口径: 只显示时间 (occ = fd→lu); 进度/散布仍在落盘与启动报告里
        self.label_info.config(text="✓" if fd is None else f"{round((lu - fd) * 1000)}ms")

    # ── 记录 ──
    def _record(self, ok):
        """落盘一行并推进采样计数

        ⚠ v2.37 修复: 写盘走 `_append_line` (异常隔离) —— 旧版 `open(...,"a").write` 直接抛,
        一次文件被占用 (OneDrive 同步/杀软/Excel) 就会打断当时的按键轮询链 (钩子, v2.47 已删)
        ⇒ 界面静默卡死、且用户不知道这些试次根本没保存。现在: 写失败 → 界面红字告警 +
        计数行显示 "落盘失败 N", 流程照常推进; **采样计数不推进** (文件里没有的行不能计入覆盖/手别欠账)。"""
        anchors = self.st.anchors()
        fmt = lambda v: f"{v*1000:.1f}" if v is not None else "0.0"
        if self.practice:
            if not self._practice_header_written:
                self._practice_header_written = self._append_line(PRACTICE_OUT, PRACTICE_HEADER)
            fd, ld, fu, lu = anchors[0 if self.hand == "left" else 1]
            row = [self.code_strokes[0], fmt(fd), fmt(ld), fmt(fu), fmt(lu),
                   "0" if ok else "1", self.st.err_tag if not ok else "",
                   "" if ok else self.st.actual_str(),
                   str(self._trial_num()), self.session_id]
            saved = self._append_line(PRACTICE_OUT, row)
        else:
            row = ["|".join(self.code_strokes)]
            row += [fmt(v) for a in anchors for v in a]
            row += ["0" if ok else "1", self.st.err_tag if not ok else "",
                    "" if ok else self.st.actual_str(),
                    str(self._trial_num()), self.session_id]
            saved = self._append_line(OUT, row)
            if saved:                            # 顶部计数只计**真的落盘了**的行 (文件里没有的不算样本)
                h = 'l' if self.hand == "left" else 'r'
                self.hand_counts[h][1] += 1      # 样本数 (成功 + 错误)
                self.hand_counts[h][0] += 1 if ok else 0
                self._update_hand_counts()
                if ok:                           # 采样覆盖只计**已保存**的正确试次 (未落盘的不算证据)
                    ss = self.code_strokes
                    side = LEFT_SET if h == 'l' else RIGHT_SET
                    cs = [''.join(c for c in s if c in side) for s in ss]
                    self.hand_singles[(h, cs[0])] += 1
                    if len(cs) > 1:              # 1 击行不计击对 (孤立试次无转移)
                        self.hand_pairs[(h, cs[0], cs[1])] += 1
                    self.hand_totals[h] += 1     # 左右 1:1 增补计数 (只算成功试次 = 证据量;
                                                 #   它喂 choose_hand; 界面另显 hand_counts)
        self.recorded += 1 if saved else 0
        self.total_trials += 1
        self._cancel_release_timeout()

    def _trial_num(self):
        return self.total_trials + 1

    def _force_advance(self):
        if self.st is not None and self.st.final_formed and not self.st.done and self.phase == "typing":
            self.st.done = True
            self._record(ok=True)
            self._schedule_next()

    def _cancel_release_timeout(self):
        if hasattr(self, "_release_timeout"):
            try:
                self.root.after_cancel(self._release_timeout)
            except Exception:
                pass
            del self._release_timeout

    def _cancel_next(self):
        """取消已排队的下一试次 (冒烟测试清理用; 应用本身不主动取消)"""
        if self._next_handle is not None:
            try:
                self.root.after_cancel(self._next_handle)
            except Exception:
                pass
            self._next_handle = None

    def _schedule_next(self, delay_ms=None):
        if delay_ms is None:
            delay_ms = random.randint(300, 800)
        self.phase = "blocked"
        self._next_handle = self.root.after(delay_ms, self._start_next)

    def _start_next(self):
        """排下下一试次; ⚠ v2.37: 这里的异常必须自己兜住 —— 旧版一旦 `new_code()` 抛异常
        (抽样/画图/刷新表), phase 就**永久停在 "blocked"**: 此后每个按键都被静默忽略
        (`if self.phase == "blocked": return`, 只有 Esc 例外), 界面看起来就是卡死。"""
        self._next_handle = None
        try:
            self.new_code()
        except Exception as exc:
            self._report_error("下一试次", exc)
            self._schedule_next(1000)      # 重排而不是停在 blocked ⇒ 采集不会静默停摆

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.stop_guards()               # 退出前停周期任务 (看门狗/IME 重摘)

# ═══════════════════ 自测 ═══════════════════

def selftest():
    """核心自测 (状态机/组合空间) + 本工具专属 (排除表/混采/参考占比)"""
    core_selftest()
    import tempfile
    # 排除表解析: 任意序 / 非法行容忍 / 归一化
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write("# 注释\nqg\ngq\nxx\nj.\nrt\n")
        tpath = tf.name
    lex, rex = load_excluded(Path(tpath))
    assert lex == {'qg'} and rex == {'j.'}, (lex, rex)      # gq→qg 归一; xx/rt 非法忽略
    Path(tpath).unlink()
    # 排除表拒绝排除 3 键组合 (唯一 3 键数据点, 保留)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write("sdf\njkl\nqg\n")
        tpath = tf.name
    lex, rex = load_excluded(Path(tpath))
    assert lex == {'qg'} and rex == set(), (lex, rex)
    Path(tpath).unlink()
    assert len(LEFT_ACTIVE) <= len(LEFT_COMBOS) and len(RIGHT_ACTIVE) <= len(RIGHT_COMBOS)
    # 混采比例: P(1击) 由 MIX_ONE_TWO 唯一决定 (改常量不必改自测; v2.34 起 = 1:4 ⇒ 1/5)
    random.seed(0)
    p1 = MIX_ONE_TWO[0] / sum(MIX_ONE_TWO)
    n1 = sum(random.choices((1, 2), weights=MIX_ONE_TWO, k=1)[0] == 1 for _ in range(30000))
    assert abs(n1 / 30000 - p1) < 0.02, (n1 / 30000, p1)
    # 3 键组合 (sdf/jkl) 采样占比 = 与 2 键同比例 (2026-09-30 起不再加权; 分析不依赖它)
    w = [COMBO_W[len(c)] * (REF_BOOST if c == REF_COMBO['l'] else 1.0) for c in LEFT_COMBOS]
    share = REF_BOOST * COMBO_W[3] / sum(w)
    two_key_share = COMBO_W[2] / sum(w)
    assert REF_BOOST == 1.0 and abs(share - two_key_share) < 1e-9, (share, two_key_share)
    # 降权表解析 (③ 软降权): 归一化 / 非法行容忍 / 权重 0 与越界值忽略 / 有效权重乘进采样
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write("# 组合降权表\nqg\t0.25\nsd 0.5\nxx 0.1\nzf\t0.0\ncv\t1.5\ngq\t0.3\n"
                 "# [manual]\ndg\t0.1\n")
        tpath = tf.name
    ws = load_weights(Path(tpath))
    assert ws == {"qg": 0.3, "sd": 0.5, "dg": 0.1}, ws   # gq→qg 后者覆盖; xx/0.0/1.5 忽略
    Path(tpath).unlink()
    app = object.__new__(ChordSpeedTest)                  # 只验 _combo_w 的乘子 (不建 GUI)
    globals()["_WEIGHTS"] = {"qg": 0.25}
    assert abs(ChordSpeedTest._combo_w(app, "qg") - COMBO_W[2] * 0.25) < 1e-12
    assert ChordSpeedTest._combo_w(app, "zf") == COMBO_W[2]                # 未列入 = 1.0
    assert ChordSpeedTest._combo_w(app, REF_COMBO['l']) == COMBO_W[3]
    globals()["_WEIGHTS"] = {}
    # 左右 1:1 增补 (v2.22): 从历史欠账收敛到 1:1, 且两侧始终交错出现
    # 偏置上限 = 0.5 ± HAND_MAX_SKEW = [0.18, 0.82] (2026-10-01 修: 原 clamp 误写成 [skew, 1−skew])
    assert hand_probability(0, 0) == 0.5
    assert abs(hand_probability(1000, 0) - (0.5 + HAND_MAX_SKEW)) < 1e-9
    assert abs(hand_probability(0, 1000) - (0.5 - HAND_MAX_SKEW)) < 1e-9
    assert 0.5 - HAND_MAX_SKEW > 0 and 0.5 + HAND_MAX_SKEW < 1      # 两侧都留概率 ⇒ 不退化成单手段
    assert hand_probability(500, 400) > 0.5 + 1e-9                 # 右手落后 ⇒ 抬高右手概率
    assert hand_probability(400, 500) < 0.5 - 1e-9                 # 右手领先 ⇒ 压低
    rng2 = random.Random(20261001)
    n_l, n_r, seq = 1000, 0, []                                    # 模拟历史欠账 1000:0
    for _ in range(3000):
        take_r = rng2.random() < hand_probability(n_l, n_r)
        seq.append('r' if take_r else 'l')
        n_l, n_r = (n_l, n_r + 1) if take_r else (n_l + 1, n_r)
    ratio = n_r / (n_l + n_r)
    win = [sum(1 for s in seq[i:i + 20] if s == 'r') for i in range(0, len(seq) - 20, 20)]
    assert 0.46 < ratio < 0.54, (n_l, n_r, ratio)                  # 收敛到 1:1 (±4%)
    assert all(0 < w < 20 for w in win), win[:5]                   # 每个 20 试次窗口两侧都出现
    # v2.23: 固定单手模式已移除 —— 构造器不再收 hand 参数 (手只能由 choose_hand 抽)
    # v2.47: 构造器也不再收 hook 参数 (键盘钩子层已删, 输入层只剩摘窗口 IME)
    # v2.48: 新增 ime= 输入层开关 (--no-ime 关掉整层; 与姊妹项目采集输入层.py 同义)
    import inspect
    sig = list(inspect.signature(ChordSpeedTest.__init__).parameters)
    assert sig == ["self", "practice", "root", "merge", "ime"], sig
    print(f"工具自测通过: 排除表(含保留 3 键组合) / 混采 1击:2击={MIX_ONE_TWO[0]}:{MIX_ONE_TWO[1]} / "
          f"3 键组合与 2 键同比例 {100*share:.2f}% / 降权表(权重乘进采样) / "
          f"左右 1:1 增补(自 1000:0 收敛到 {ratio:.1%}; 20 试次窗口两侧都在) / "
          f"无固定单手模式(仅随机抽边)")


# ═══════════════════ GUI 冒烟测试 (隐藏窗口) ═══════════════════

def smoke(tmp_out=True):
    """GUI 冒烟: 隐藏窗口, 数据写入临时文件 (不污染正式数据)"""
    import tempfile, os
    from types import SimpleNamespace as _NS     # 别用 `types` 这个名字: 冒烟里它被占作击数集合
    global OUT
    real_out = OUT
    if tmp_out:
        fd, tmp = tempfile.mkstemp(suffix=".tsv")
        os.close(fd)                      # mkstemp 的 fd 需显式关闭, 否则 Windows 无法删除
        OUT = Path(tmp)
    try:
        root = tk.Tk()
        root.withdraw()

        def mk(kb, key):
            """该键**画出来**的标记 (读画布真实状态, 不重写画法规则):
            '圈' / '叉' / '圈叉' (目标键) · '按' (非目标键按下 = 亮圈) ·
            '空' (非目标键骨架圈) · '隐' (半边键盘的另一半)"""
            if not kb.shown(key):
                return "隐"
            st = kb.mark_strokes(key)
            if st:
                return {frozenset({0}): "圈", frozenset({1}): "叉",
                        frozenset({0, 1}): "圈叉"}[st]
            return "按" if key in kb.pressed else "空"

        def packed(w):
            """该控件是否**被 pack 管理** (= 展开态)。⚠ 冒烟全程 root 是 withdraw 的, 子件的
            `winfo_ismapped()` 恒为 0 ⇒ 只能问几何管理器 (pack_info), 它反映 pack_forget 与否。"""
            try:
                w.pack_info()
                return True
            except tk.TclError:
                return False

        def snapshot(kb):
            """画布的**全部可见状态** (逐键标记 + 圈/叉线宽 + 画布边框色) —— "首笔 ≡ 后续"断言用"""
            return ({k: (mk(kb, k), kb.itemcget(kb.circles[k], "width"),
                         tuple(kb.itemcget(i, "width") for i in kb.crosses[k]))
                     for k in kb.circles}, kb.cget("highlightbackground"))

        app = ChordSpeedTest(root=root)                 # 默认 = 两击合并单图 (v2.26)
        assert not hasattr(app, "kb1") and not hasattr(app, "kb2"), "默认应为合并单图"
        assert isinstance(app.kb, KeyboardCanvas) and len(app.kb.circles) == 30
        assert len(app.kb.crosses) == 30 and all(len(v) == 2 for v in app.kb.crosses.values())
        # 输入层 (v2.47, 无视 IME = **只有"摘窗口 IME"一条**): 钩子相关的属性/开关必须真的不存在
        # (防回潮); 按键路径 = tkinter 事件处理 + 状态机入口
        for name in ("hook", "_no_hook", "_poll_hook", "stop_hook"):
            assert not hasattr(app, name), f"{name} 应随 v2.47 删除"
        assert callable(app.on_key_down) and callable(app.on_key_up)
        assert callable(app.on_press) and callable(app.on_release) and callable(app.stop_guards)
        # 半边键盘 (v2.31): 无基准键标记/无分界线; 只画本试次采集手那一半, 键位保持原位
        assert not hasattr(app.kb, "marks") and not hasattr(app.kb, "split_line")
        h = 'l' if app.hand == "left" else 'r'
        assert app.kb.hand == h, (app.kb.hand, app.hand)
        hidden = {k for k in app.kb.circles if not app.kb.shown(k)}
        assert hidden == (RIGHT_SET if h == 'l' else LEFT_SET), \
            (h, sorted(hidden))                      # 另一半整个隐藏 (圈与叉都不可见); 本半 15 键可见
        # **v2.32 修 (换手试次整图消失)**: 半边隐藏必须可逆 —— 本手的圆全部 state=normal。
        # 旧 _paint 普通键分支不恢复 state, 上一试次采另一手时本手的圆停留在 hidden,
        # 新试次整张图只剩共键可见。这里来回切手验证可逆 + 空键圈不填充 (用户 2026-10-06)
        app.kb.set_hand('r' if h == 'l' else 'l')
        app.kb.set_hand(h)
        assert {k for k in app.kb.circles if not app.kb.shown(k)} == hidden
        assert app.kb.itemcget(app.kb.circles['q' if h == 'l' else 'y'], "fill") == ""
        # 合并图 = 一张键盘 (v2.45 起**再没有图例行** —— 记法说明收进 `?` 说明书)
        root.update_idletasks()
        assert (app.kb.grid_info()["row"], app.kb.grid_info()["column"]) == (0, 0), \
            app.kb.grid_info()
        # v2.45: 图例相关的控件/方法必须真的不存在 (防回潮)
        for name in ("legend", "legend_mark", "legend_mark_canvas", "_sync_legend"):
            assert not hasattr(app, name), f"{name} 应随 v2.45 删除"
        # `?` 说明书 (v2.45): 图标在, **默认收起**, 正文来自独立文档 (不在代码里再抄一份)
        assert isinstance(app.btn_help, tk.Canvas) and app.manual_open is False
        assert not packed(app.manual_frame), "说明书默认必须收起"
        assert app._read_manual().startswith("# 并击当量采集器"), app._read_manual()[:40]
        # v2.41: 画布与图例**都没有"当前击"状态** —— 边框固定中性, 图例不加粗, 无 set_active*
        assert app.kb.cget("highlightbackground") == KEY_FRAME
        for m in ("set_active_stroke", "set_active"):
            assert not hasattr(app.kb, m), f"{m} 应随 v2.41 删除"
        # 窗口不小于内容需求 (硬编码 geometry 会随布局改动过期 → 标签被裁)。
        # withdraw 下 wm_geometry 是冻结快照 (Tk 不重算布局) → 先 deiconify 让
        # _fit_geometry 的请求真正生效, 核对完再收回 (smoke 全程保持隐藏)
        root.deiconify()
        root.update_idletasks()
        gw, gh = (int(v) for v in root.wm_geometry().split("+")[0].split("x"))
        assert (gw, gh) >= (root.winfo_reqwidth(), root.winfo_reqheight()), \
            (gw, gh, root.winfo_reqwidth(), root.winfo_reqheight())
        assert root.winfo_reqheight() <= root.winfo_screenheight() - 60, \
            (root.winfo_reqheight(), root.winfo_screenheight())
        root.withdraw()
        # 混采 + 随机单手: 跑 80 个试次, 两类都出现, 组合出自**本试次抽到的那只手**, 且两手都抽到
        types, hands_seen = set(), set()
        for _ in range(80):
            types.add(len(app.code_strokes))
            pool = LEFT_COMBOS if app.hand == "left" else RIGHT_COMBOS
            assert all(s in pool for s in app.code_strokes), (app.hand, app.code_strokes)
            hands_seen.add(app.hand)
            app.new_code()
        assert types == {1, 2}, types
        assert hands_seen == {"left", "right"}, hands_seen   # 1:1 抽边 ⇒ 80 试次内两手必都出现
        # 1 击试次: 只有圈 (无叉) + 图例淡掉「第 2 击」; 走完流程 → 写行 (二击锚为 0.0)
        app.hand = "left"                             # 下面用例全为左手组合 (半边显示对应左半)
        app.code_strokes = ['sf']
        app.st = StrokeTrial(['sf'])
        app.phase = "typing"
        app._paint_targets()
        assert [mk(app.kb, k) for k in 'sf'] == ['圈', '圈'], "1 击试次 = 圈"
        assert mk(app.kb, 'x') == '空', "非目标键 = 键位骨架圈 (不表示任何一击)"
        app.st.press('s', 0.0); app.st.press('f', 0.03)
        app.st.release('s', 0.15); app.st.release('f', 0.16)
        assert app.st.done
        app._record(ok=True)
        lines = Path(OUT).read_text(encoding="utf-8").strip().split("\n")
        assert lines[0].split("\t") == HEADER, lines[0][:60]      # 表头存在且列名正确
        last = lines[-1].split("\t")
        assert len(last) == len(HEADER) == 22, len(last)
        assert last[0] == "sf" and last[1] == "0.0", last[:3]      # fd1=0
        assert all(v == "0.0" for v in last[9:17]), last[9:17]     # 二击锚全 0.0
        assert last[17] == "0" and last[18] == "", last[17:20]     # ok 行: error=0, err_type 空
        # 2 击试次正常: 目标 = 两击组合
        app.hand = "left"                             # 以下用例全为左手组合 (半边显示对应左半)
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.phase = "typing"
        app._paint_targets()
        assert app.kb.targets == set('sfxc')
        # 图形规则 (v2.40, 2026-10-11 用户决策 —— **形状**区分击序, 颜色统一白色):
        # 第 1 击 = 圈 / 第 2 击 = 叉 / 共有 = 圈里一个叉; 按下 = 加粗高亮, 松开恢复
        app.code_strokes = ['sf', 'sv']                # 左手 s: 两击都要打 → 共有
        app.st = StrokeTrial(app.code_strokes)
        app.phase = "typing"
        app._paint_targets(); app._update_kb()
        assert app.kb.target_strokes['s'] == {0, 1}, app.kb.target_strokes    # 共有 = 两击都含
        assert app.kb.target_strokes['f'] == {0} and app.kb.target_strokes['v'] == {1}
        assert app.kb.targets == set('sfv'), app.kb.targets
        assert not hasattr(app.kb, "shared") and not hasattr(app.kb, "inner")  # 同心双圆已删
        assert [mk(app.kb, k) for k in ('s', 'f', 'v')] == ['圈叉', '圈', '叉'], \
            "第 1 击 = 圈 / 第 2 击 = 叉 / 共有 = 圈里一个叉 (v2.40 用户口径)"
        # 图形规则的另一侧 (回读 mark_strokes 不查"该藏的图形有没有藏", 这里直接查图元 state):
        assert app.kb.itemcget(app.kb.circles['f'], "state") == "normal"        # 击1 独有: 有圈
        assert all(app.kb.itemcget(i, "state") == "hidden" for i in app.kb.crosses['f'])
        assert app.kb.itemcget(app.kb.circles['v'], "state") == "hidden"        # 击2 独有: 无圈
        assert all(app.kb.itemcget(i, "state") == "normal" for i in app.kb.crosses['v'])
        # 标记**一律白色** (不再用蓝/红分击): 圈 = oval.outline, 叉 = line.fill
        assert app.kb.itemcget(app.kb.circles['f'], "outline") == KEY_MARK
        assert all(app.kb.itemcget(i, "fill") == KEY_MARK for i in app.kb.crosses['v'])
        # 叉的几何 (用户要求"叉的长就是圈的直径"): 端点**落在圈上** (内切) ⇒ 每笔线长 = 圈直径
        cc = app.kb.coords(app.kb.circles['v'])
        ln = app.kb.coords(app.kb.crosses['v'][0])
        cx, cy = (cc[0] + cc[2]) / 2, (cc[1] + cc[3]) / 2
        assert abs(math.hypot(ln[2] - ln[0], ln[3] - ln[1]) - 2 * R_KEY) < 1e-9, (ln, R_KEY)
        assert abs(math.hypot(ln[0] - cx, ln[1] - cy) - R_KEY) < 1e-9, "叉端点必须落在圈上"
        assert abs((ln[0] + ln[2]) / 2 - cx) < 1e-9 and abs((ln[1] + ln[3]) / 2 - cy) < 1e-9
        # 图例已删 (v2.45) ⇒ 这里改为验证 `?` 说明书**真的能展开/收起**且正文渲染出了两行信息
        assert app.manual_open is False and not packed(app.manual_frame)
        app._toggle_manual()                          # 点 `?` → 展开
        root.update_idletasks()
        assert app.manual_open is True and packed(app.manual_frame)
        body = app.manual_text.get("1.0", "end")
        assert "圈" in body and "叉" in body and "Trial" in body and "成功数/样本数" in body, \
            "说明书正文应含记法与两行信息的解释: " + body[:80]
        assert "**" not in body and "#" not in body.split("\n")[0], "Markdown 标记应被渲染掉"
        h_open = root.winfo_reqheight()
        app._toggle_manual()                          # 再点 → 收起
        root.update_idletasks()
        assert app.manual_open is False and not packed(app.manual_frame)
        assert root.winfo_reqheight() < h_open, (root.winfo_reqheight(), h_open)
        # 缺失说明书文件 → 面板里明说路径 (不静默空着)
        real_read = app.__class__._read_manual
        app.__class__._read_manual = lambda self: "# 读不到说明书\n\n/某路径/采集器说明书.md"
        app._manual_loaded = False
        app._toggle_manual()
        assert "读不到说明书" in app.manual_text.get("1.0", "end")
        app.__class__._read_manual = real_read
        app._manual_loaded = False
        app._toggle_manual()                          # 收起, 交回后续用例
        app._cancel_next()
        # 试次首笔必须与随后 _update_kb 的状态**完全一致** (回归断言, 2026-10-11 实测):
        # 旧版首笔用上一试次遗留的 active_stroke 上色, 几毫秒后才被覆盖 ⇒ 用户看到"闪一下"
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.phase = "typing"
        app._paint_targets()                          # 只画首笔 (尚未 _update_kb)
        first = snapshot(app.kb)
        app._update_kb()
        assert snapshot(app.kb) == first, "试次首笔与 _update_kb 后的画布不一致 ⇒ 中间态会闪一下"
        # 推进击序时**画布不得有任何变化** (v2.41: 已无"当前击"提示 ⇒ 边框固定、图形固定)
        app.code_strokes = ['sf', 'sv']
        app.st = StrokeTrial(['sf', 'sv'])
        app.phase = "typing"
        app.down.clear()
        app._paint_targets(); app._update_kb()        # 画布与 st 必须同步 (换了目标就要重画)
        assert app.kb.cget("highlightbackground") == KEY_FRAME     # 边框恒为中性 (不再提示击次)
        app.st.press('s', 0.0); app._update_kb()
        assert float(app.kb.itemcget(app.kb.circles['s'], "width")) == KEY_W_PRESS
        assert all(float(app.kb.itemcget(i, "width")) == KEY_W_PRESS for i in app.kb.crosses['s'])
        assert app.kb.itemcget(app.kb.circles['s'], "fill") == ""    # 按下也不填充 (只加粗)
        assert mk(app.kb, 's') == '圈叉'                              # 图形不随按下变化
        app.st.press('f', 0.03); app._update_kb()
        assert float(app.kb.itemcget(app.kb.circles['f'], "width")) == KEY_W_PRESS
        assert app.kb.itemcget(app.kb.circles['f'], "fill") == ""
        # 击1 释放共键 s (f 还按着): s 立即恢复原线宽 —— **v2.32 主修**: 旧用 downs,
        # 已放开的键残留在按下集, 全放后 si=1 时共键瞬间被点亮 (还没按第二击)
        app.st.release('s', 0.05); app._update_kb()
        assert float(app.kb.itemcget(app.kb.circles['s'], "width")) == KEY_W
        app.st.release('f', 0.06)     # 击1 全放 → si=1
        assert app.st.si == 1
        app._update_kb()
        assert app.kb.cget("highlightbackground") == KEY_FRAME, "击序推进不得改变边框 (v2.41)"
        assert [mk(app.kb, k) for k in ('s', 'f', 'v')] == ['圈叉', '圈', '叉']   # 图形恒定
        app.st.press('s', 0.08); app._update_kb()                     # 击2 按共键 → 加粗
        assert float(app.kb.itemcget(app.kb.circles['s'], "width")) == KEY_W_PRESS
        assert float(app.kb.itemcget(app.kb.crosses['s'][0], "width")) == KEY_W_PRESS
        app.st.press('v', 0.09); app._update_kb()                     # 击2 按叉键 → 叉笔加粗
        assert float(app.kb.itemcget(app.kb.crosses['v'][0], "width")) == KEY_W_PRESS
        app.st.release('s', 0.15); app.st.release('v', 0.16)
        # **非目标键按下也高亮** (v2.40: "键位按下时高亮" 对任何键成立; 与旧版"按错键也亮"一致) ——
        # 只亮圈、不加叉, `mark_strokes` 仍是空集 (按错键不会被读成"属于第 1 击")。这里按的 q
        # 会触发 R1 (非目标键 = 真实错误场景), 但本块只验证显示, 不走落盘路径。
        app.code_strokes = ['sf', 'sv']
        app.st = StrokeTrial(['sf', 'sv'])
        app.phase = "typing"
        app.down.clear()
        app._paint_targets(); app._update_kb()
        assert mk(app.kb, 'q') == '空', "非目标键平时 = 极暗骨架圈"
        app.st.press('q', 0.20); app._update_kb()
        assert mk(app.kb, 'q') == '按' and app.kb.mark_strokes('q') == frozenset()
        assert app.kb.itemcget(app.kb.circles['q'], "outline") == KEY_MARK
        assert float(app.kb.itemcget(app.kb.circles['q'], "width")) == KEY_W_PRESS
        assert all(app.kb.itemcget(i, "state") == "hidden" for i in app.kb.crosses['q'])
        app.st.release('q', 0.22); app._update_kb()
        assert mk(app.kb, 'q') == '空', "松开即恢复骨架圈"
        # 2 击但无共有键: 图例第 2 击仍亮; 第 2 击独有键 = 单叉 (无圈)
        app.code_strokes = ['sf', 'xc']
        app._paint_targets(); app._update_kb()
        assert [mk(app.kb, k) for k in ('s', 'x')] == ['圈', '叉']
        # ── 图形口径 (2026-10-11 用户决策确立) ──
        # ① **2 击试次: 第 2 击的叉从试次一出现就在** (用户要求); 且首笔之后不再变
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.phase = "typing"
        app.down.clear()
        app._paint_targets()                                  # 首笔 (尚未 _update_kb)
        assert [mk(app.kb, k) for k in ('s', 'x')] == ['圈', '叉'], \
            "2 击试次一出现, 第 2 击的叉就该在 (用户要求)"
        first = snapshot(app.kb)
        app._update_kb()                                      # 随后那一笔必须一致 (无中间态 ⇒ 不闪)
        assert snapshot(app.kb) == first
        # ② **1 击试次全程不得出现第 2 击的叉** —— 用户报障的直接回归断言
        # (2026-10-11: "打完 1 击试次松手后看见红, 之后马上又变蓝" ⇒ 1 击试次里不该有任何
        #  第 2 击的痕迹。v2.40 起"第 2 击的痕迹"只剩**叉**这一种 —— 颜色/边框提示已随 v2.41 删除)
        app.hand = "left"; app.code_strokes = ['sf']
        app.st = StrokeTrial(['sf']); app.phase = "typing"
        app.down.clear(); app._paint_targets()
        for step in (lambda: None,                            # 含"首笔"这一步 (旧版就是这里闪的)
                     lambda: app._update_kb(),
                     lambda: app.on_key_down('s', 0.0), lambda: app.on_key_down('f', 0.03),
                     lambda: app.on_key_up('s', 0.10), lambda: app.on_key_up('f', 0.11)):
            step()
            assert not any(1 in app.kb.mark_strokes(k) for k in app.kb.circles), \
                "1 击试次里出现了第 2 击的叉"
            assert all(1 not in v for v in app.kb.target_strokes.values()), \
                "1 击试次的目标里混进了第 2 击"
            assert app.kb.cget("highlightbackground") == KEY_FRAME, "边框不得随击次变化 (v2.41)"
            assert "当前" not in app.label_block.cget("text"), app.label_block.cget("text")
        app._cancel_next()
        # 错误捕获态 (2026-09-29): R1 出错后继续按键, 全放开才落盘 → actual 含完整错误组合
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.st.press('s', 0.0); app.st.press('f', 0.03)
        app.st.release('s', 0.05); app.st.release('f', 0.06)   # 击1 成形
        app.st.press('d', 0.08)                                # 错键 → R1@2, 捕获态
        assert app.st.error and app.st.err_tag == 'R1@2' and app.st.capturing
        assert not app.st.done
        app.st.press('g', 0.10)                                # 捕获: 继续记 (不校验)
        app.st.release('d', 0.12)
        assert not app.st.done                                 # g 仍按着 → 未落盘时机
        app.st.release('g', 0.14)                              # 全放开 → done
        assert app.st.done
        app._record(ok=False)
        last = Path(OUT).read_text(encoding="utf-8").strip().split("\n")[-1].split("\t")
        assert last[17] == "1" and last[18] == "R1@2", last[17:19]
        assert last[19] == "sf|dg", last[19]                   # 完整错误键位组合
        # 固定单手模式已移除 (v2.23): 没有 hand_var / on_hand_change, 抽边只能走 choose_hand
        assert not hasattr(app, "hand_var") and not hasattr(app, "on_hand_change")
        rng_smoke = random.Random(7)
        assert {app.choose_hand(rng_smoke) for _ in range(200)} == {"left", "right"}
        # 输入层共用按键路径 (v2.24): 直接喂按键 (等价于钩子/IME 摘除后的事件) → 走完状态机落盘
        n_before = app.recorded
        app.hand = "left"                           # 手别与试次内容一致 (正常流程由采样保证)
        app.code_strokes = ['sf']
        app.st = StrokeTrial(['sf'])
        app.phase = "typing"
        app._paint_targets()
        app.on_key_down('s', 0.0); app.on_key_down('f', 0.03)
        app.on_key_up('s', 0.15); app.on_key_up('f', 0.16)
        assert app.st.done and app.recorded == n_before + 1, (app.recorded, n_before)
        last = Path(OUT).read_text(encoding="utf-8").strip().split("\n")[-1].split("\t")
        assert last[0] == "sf" and last[17] == "0", last[:20]
        # 完成提示只显示时间 (2026-10-08 用户决策): 一击 = "xxms" (occ = lu−fd = 0.16s)
        assert app.label_info.cget("text") == "160ms", app.label_info.cget("text")
        app._cancel_next()                          # 清掉本用例排下的下一试次
        # 完成提示: 二击 = "S1+S2+S3=wc ms" (三段取整后相加 ⇒ 算式恒自洽)
        app.hand = "left"
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.phase = "typing"
        app._paint_targets()
        app.on_key_down('s', 0.0); app.on_key_down('f', 0.03)
        app.on_key_up('s', 0.10); app.on_key_up('f', 0.11)      # 击1: S1 = 0.11
        app.on_key_down('x', 0.20); app.on_key_down('c', 0.23)
        app.on_key_up('x', 0.30); app.on_key_up('c', 0.31)      # 击2: S2 = 0.09, S3 = 0.11
        assert app.st.done
        assert app.label_info.cget("text") == "110+90+110=310ms", app.label_info.cget("text")
        a, b, c = (int(v) for v in app.label_info.cget("text")[:-2].replace("ms", "").split("=")[0].split("+"))
        assert int(app.label_info.cget("text")[:-2].split("=")[1]) == a + b + c
        app._cancel_next()
        # 非目标手禁用 (v2.35): 目标在左手 → 右手键被忽略 (不进状态机/不产生 R1),
        # 本手键照常; 空格/Escape 不属于任何手不受影响 (跳过逻辑另有断言)
        app.hand = "left"
        app.code_strokes = ['sf']
        app.st = StrokeTrial(['sf'])
        app.phase = "typing"
        app._paint_targets()
        app.on_key_down('y', 0.005); app.on_key_up('y', 0.01)   # 右手键 → 忽略
        assert len(app.st.downs) == 0 and not app.st.error, app.st.downs
        app.on_key_down('s', 0.02); app.on_key_up('s', 0.03)    # 本手键 → 正常进状态机
        assert [k for _, k, _ in app.st.downs] == ['s'], app.st.downs
        app.st = StrokeTrial(['sf'])                # 复位 (清掉 s 的半击状态)
        app._cancel_next()
        # tkinter 事件 → on_press/on_release → 状态机 (合成事件对象喂进去, 不碰真实键盘)
        # v2.47: 这条路原来是"钩子队列 → 5ms 轮询"的回退路径, 现在**就是主路径**
        def key_ev(ks, ch=None):                # 合成 <KeyPress>/<KeyRelease> 事件
            return _NS(keysym=ks, char=(ks if ch is None else ch))
        app.hand = "left"
        app.code_strokes = ['xc']
        app.st = StrokeTrial(['xc'])
        app.phase = "typing"
        app._paint_targets()
        app.on_press(key_ev('x')); app.on_press(key_ev('c'))     # 同一击 (调用间隔 ≪ T_SYNC)
        app.on_release(key_ev('x')); app.on_release(key_ev('c'))  # 全放开 ⇒ 一击成形
        assert app.st.done and not app.st.err_tag, (app.st.done, app.st.err_tag)
        # 归一化口径: 字母取 char 的小写 (Shift 大写也认); 松开 char 为空时用 keysym 兜底 (v2.39)
        app.code_strokes = ['x']
        app.st = StrokeTrial(['x'])
        app.phase = "typing"
        app.on_press(key_ev('X', 'X'))        # char='X' → 键名必须归一成 'x'
        assert [k for _, k, _ in app.st.downs] == ['x'], app.st.downs
        app.on_release(key_ev('X', ''))       # 松开 char='' → 靠 keysym 认键
        assert app.st.done and not app.st.err_tag, (app.st.done, app.st.err_tag)
        app._cancel_next()
        # ── v2.37 静默失联防护 (v2.47 起由**按键处理隔离**承担) ──
        # 旧版风险是"`_poll_hook` 分发抛异常 ⇒ 轮询链断 ⇒ 键盘彻底失联"; 钩子删掉后同一条保证
        # 落在 `on_press`/`on_release` 上: 单个按键处理抛异常 → 上报 + 隔离, **后续按键照常处理**
        real_down = app.on_key_down

        def boom(key, t=None):                # 只有 'q' 抛 (模拟"某个事件处理炸了")
            if key == 'q':
                raise RuntimeError("冒烟注入的事件异常")
            return real_down(key, t)

        app.on_key_down = boom
        app.hand = "left"
        app.code_strokes = ['x']
        app.st = StrokeTrial(['x'])
        app.phase = "typing"
        app._paint_targets()
        n_err0 = app.err_count
        app.on_press(key_ev('q'))             # 抛 → 必须被隔离 (不上抛、不静默)
        assert app.err_count == n_err0 + 1, app.err_count        # 异常被上报 (不是静默)
        assert "按键处理" in app.label_warn.cget("text"), app.label_warn.cget("text")
        app.on_press(key_ev('x')); app.on_release(key_ev('x'))    # 后续按键照常处理
        assert app.st.done, "异常之后的按键没被继续处理 ⇒ 按键路径断了"
        app.on_key_down = real_down
        app._cancel_next()
        # ② 落盘失败不卡死: 指向不存在的目录 → _record 不抛, 计数与告警可见, 采样计数不推进
        good_out = OUT                                # smoke 顶部已 global OUT = 临时文件
        OUT = Path(str(good_out) + "_不存在目录") / "x.tsv"
        rec0, tot0, fail0 = app.recorded, app.total_trials, app.save_failures
        app.hand = "left"
        app.code_strokes = ['sf']
        app.st = StrokeTrial(['sf'])
        app.st.press('s', 0.0); app.st.press('f', 0.03)
        app.st.release('s', 0.15); app.st.release('f', 0.16)
        app._record(ok=True)                          # 不该抛
        assert app.save_failures == fail0 + 1, app.save_failures
        assert app.recorded == rec0, "落盘失败的试次不能计入已记录/覆盖"
        assert app.total_trials == tot0 + 1, app.total_trials
        assert "落盘" in app.label_warn.cget("text"), app.label_warn.cget("text")
        OUT = good_out
        app._cancel_next()
        # ③ 下一试次调度隔离: new_code 抛异常 → 不抛穿, phase 不永久停在 blocked
        real_new_code = app.new_code

        def boom_new_code():
            raise RuntimeError("冒烟注入的抽样异常")

        app.new_code = boom_new_code
        app.phase = "blocked"
        n_err1 = app.err_count
        app._start_next()                             # 不该抛
        assert app.err_count == n_err1 + 1, app.err_count
        assert app._next_handle is not None, "异常后未重排下一试次 ⇒ 会永久卡在 blocked"
        app._cancel_next()
        app.new_code = real_new_code
        # ④ v2.43 界面精简: 周期任务仍在 (但**不再出焦点/超时提示行**), 按键流计数改走控制台
        assert callable(app._focus_guard)             # 周期任务仍在 (__init__ 已跑过一次)
        n_keys = app.key_events
        app.on_key_down('y', 0.0)
        assert app.key_events == n_keys + 1, app.key_events
        assert app._last_key_ts > 0
        # 删掉的行/字段必须真的不存在 (防它们悄悄回来)
        for name in ("label_title", "label_count", "label_hint", "_was_fg", "_stale", "_trial_ts",
                     "STALE_HINT_S"):
            assert not hasattr(app, name) and name not in globals(), f"{name} 应随 v2.43 删除"
        # 未获焦点**不再出提示**, 但仍不得动试次 (看门狗只在前台跑); 真问题 (内部错误) 仍要报
        keep = (app.err_count, app.save_failures)     # 前面几块已注入过真问题, 这里先清零看"空"态
        app.err_count = app.save_failures = 0
        app._refresh_warn()
        assert app.label_warn.cget("text") == "", app.label_warn.cget("text")
        n_stuck = []
        real_stuck, real_fg = app._stuck_guard, globals()["app_is_foreground"]
        app._stuck_guard = lambda: n_stuck.append(1)
        app._running = True
        try:
            globals()["app_is_foreground"] = lambda: False
            app._focus_guard()
            assert app.label_warn.cget("text") == "", \
                f"非前台不得再出提示: {app.label_warn.cget('text')}"
            assert n_stuck == [], "非前台时看门狗不得动试次 (用户可能只是去别的窗口看一眼)"
            globals()["app_is_foreground"] = lambda: True
            app._focus_guard()
            assert n_stuck == [1], "前台时看门狗必须跑 (v2.38 防永久卡住)"
        finally:
            app._stuck_guard, app._running = real_stuck, False
            globals()["app_is_foreground"] = real_fg
        app.err_count = 1                             # 内部错误仍必须显示
        app._refresh_warn()
        assert "内部错误" in app.label_warn.cget("text"), app.label_warn.cget("text")
        app.err_count, app.save_failures = keep       # 恢复: 真问题照样报, 且不含已删的两条提醒
        app._refresh_warn()
        assert "内部错误" in app.label_warn.cget("text") and "落盘失败" in app.label_warn.cget("text")
        assert "焦点" not in app.label_warn.cget("text")
        assert "久未完成" not in app.label_warn.cget("text")
        app._cancel_next()
        # ⑤ 顶部计数行 (v2.44): 左 成功/样本 : 右 成功/样本 —— 口径 = 数据文件 (成功 = error=0)
        assert hasattr(app, "label_hands")
        # 先验"全程累加 == 现扫同一份数据文件" (两处口径必须逐行一致: 落盘累加 vs 扫描函数)
        assert app.hand_counts == scan_hand_counts(OUT), (app.hand_counts, scan_hand_counts(OUT))
        l0, r0 = list(app.hand_counts['l']), list(app.hand_counts['r'])
        app.hand = "left"                               # 左手 ok 行 → 左 成功+1 样本+1
        app.code_strokes = ['sf']
        app.st = StrokeTrial(['sf'])
        app.st.press('s', 0.0); app.st.press('f', 0.03)
        app.st.release('s', 0.15); app.st.release('f', 0.16)
        app._record(ok=True)
        assert app.hand_counts['l'] == [l0[0] + 1, l0[1] + 1], app.hand_counts
        app.st = StrokeTrial(['sf'])                    # 左手错误行 → 只加样本
        app.st.press('q', 0.0)
        app.st.release('q', 0.05)
        app._record(ok=False)
        assert app.hand_counts['l'] == [l0[0] + 1, l0[1] + 2], \
            "错误行只加样本、不加成功: " + str(app.hand_counts)
        app.hand = "right"                              # 右手 ok 行 → 右 成功+1 样本+1
        app.code_strokes = ['ui']
        app.st = StrokeTrial(['ui'])
        app.st.press('u', 0.0); app.st.press('i', 0.03)
        app.st.release('u', 0.10); app.st.release('i', 0.11)
        app._record(ok=True)
        assert app.hand_counts['r'] == [r0[0] + 1, r0[1] + 1], app.hand_counts
        assert app.label_hands.cget("text") == \
            f"左 {l0[0]+1}/{l0[1]+2} : 右 {r0[0]+1}/{r0[1]+1}", app.label_hands.cget("text")
        assert app.hand_counts == scan_hand_counts(OUT), "三次落盘后与扫描口径不一致"
        assert scan_hand_counts(Path(str(OUT) + "_不存在")) == {'l': [0, 0], 'r': [0, 0]}
        app._cancel_next()
        # ── v2.38 看门狗 + 击序可见性 (2026-10-11 用户实测"快打时偶发卡住") ──
        # ① 错误捕获态不会永久卡住: 只要"还有键没松", 旧版永远不落盘也不推进 (界面像卡死);
        #    现在静默 CAPTURE_STUCK_S 后自动收尾 (错误行照常落盘)
        app.hand = "left"
        app.code_strokes = ['x', 'ab']
        app.st = StrokeTrial(['x', 'ab'])
        app.phase = "typing"
        app._paint_targets()
        rec1 = app.recorded
        app.down.clear()
        app.on_key_down('q', 0.0)                             # 错键 → R1 捕获态 (held={q})
        app.on_key_down('x', 0.05)                            # 抢在松开前按下一键 (滚动打法)
        app.on_key_up('q', 0.10)                              # 松开 q, x 还按着 ⇒ 捕获态继续
        assert app.st.error and app.st.capturing and app.st.held, (app.st.error, app.st.held)
        assert "全部松开即继续" in app._err_text(), app._err_text()
        app._last_key_ts -= (CAPTURE_STUCK_S + 1.0)           # 模拟"静默超时"
        app._stuck_guard()
        assert app.recorded == rec1 + 1, "错误行超时后应照常落盘"
        last = Path(OUT).read_text(encoding="utf-8").strip().split("\n")[-1].split("\t")
        assert last[17] == "1" and last[18].startswith("R1"), last[17:19]
        app._cancel_next()
        # ② 正常试次漏收"松开"事件也不会永久卡住 (20s 后按全放收尾)
        app.down.clear()                                      # 清掉上一块留下的按下集
        app.hand = "left"
        app.code_strokes = ['x', 'ab']
        app.st = StrokeTrial(['x', 'ab'])
        app.phase = "typing"
        app._paint_targets()
        app.on_key_down('x', 0.0)                             # 击1 成形后"松开丢了"
        assert app.st.held, app.st.held
        rec2 = app.recorded
        app._last_key_ts -= (TRIAL_STUCK_S + 1.0)
        app._stuck_guard()
        assert app.recorded == rec2 + 1, "漏收松开 → 超时应自动收尾"
        app._cancel_next()
        # ③ 试次间隔里按键必须**说出来** (快打抢拍 ⇒ 静默丢键会造成"击序错位"错觉)
        app.down.clear()
        app.phase = "blocked"
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.on_key_down('s', 0.0)
        assert "没有被记录" in app.label_info.cget("text"), app.label_info.cget("text")
        app.on_key_up('s', 0.02)                              # 清掉按下集 (blocked 里也跟踪)
        app._cancel_next()
        # ④ v2.41: **不再提示击次** —— 图例恒不加粗、边框恒为中性, 打完第 1 击画面**没有变化**;
        #    唯一遗留的击次信息 = 试次行只写 Trial N (也不含"第几击"字样)
        app.down.clear()
        app.hand = "left"
        app.code_strokes = ['sf', 'xc']
        app.st = StrokeTrial(['sf', 'xc'])
        app.phase = "typing"
        app._paint_targets(); app._update_kb()
        assert app.label_block.cget("text") == f"Trial {app._trial_num()}", \
            app.label_block.cget("text")
        app.on_key_down('s', 0.0); app.on_key_down('f', 0.03)
        app.on_key_up('s', 0.10); app.on_key_up('f', 0.11)     # 击1 完成 → 当前击 = 2
        assert app.kb.cget("highlightbackground") == KEY_FRAME, "边框不得随击次变化"
        assert int(app.kb.cget("highlightthickness")) >= 3
        app._cancel_next()
        # 练习模式: 单击目标 (同样随机抽边) —— 合并图只有圈 (v2.45: 无图例, 无淡出档)
        app3 = ChordSpeedTest(practice=True, root=root)
        assert len(app3.code_strokes) == 1 and app3.kb.targets == set(app3.code_strokes[0])
        assert all(mk(app3.kb, k) == "圈" for k in app3.kb.targets), "练习 (1 击) 只画圈"
        assert app3._read_manual().startswith("# 并击当量采集器")   # 说明书两种模式都在
        assert app3.hand in ("left", "right")
        # ── v2.48 `--no-ime` 排障开关: 关掉输入层 = 回到修复前 (一点不碰输入法) ──
        # 用**计数打桩**替换模块级 `ime_detach` 断言"做了什么", 不靠读代码猜 (改完即还原)
        ime_calls = []
        real_detach = globals()["ime_detach"]

        def _count_detach(r):
            ime_calls.append(r)
            return 1                            # 模拟"摘掉了 1 个窗口"

        globals()["ime_detach"] = _count_detach
        try:
            app_off = ChordSpeedTest(root=root, ime=False)     # --no-ime: 一次都不许摘
            assert app_off._ime is False
            assert ime_calls == [], f"ime=False 时不得摘除 IME, 实际摘了 {len(ime_calls)} 次"
            assert app_off._running, "看门狗等周期任务与输入层无关, 仍要起"
            app_off._on_focus_in()                             # 激活重摘路径: 必须被关掉
            app_off._ime_guard()                               # 周期重摘函数: 手动调也不得摘 (自身也受控)
            assert len(ime_calls) == 0, "ime=False 时三条路径都不许摘"
            app_on = ChordSpeedTest(root=root, ime=True)       # 默认: 必须摘
            # 构造时恰好两次: 装入输入层一次 + 周期重摘链的**首摘**一次 (`_ime_guard` 立摘再排)
            assert app_on._ime is True and len(ime_calls) == 2, len(ime_calls)
            app_on._on_focus_in()
            assert len(ime_calls) == 3, "ime=True 时激活要重摘"
        finally:
            globals()["ime_detach"] = real_detach
        app_off.stop_guards(); app_on.stop_guards()
        # --split 回退 (旧两图布局, 2026-09-29): 两块键盘上下排列 (协议对照/回滚用);
        # v2.40: 上块 = 第 1 击 (圈) / 下块 = 第 2 击 (**stroke=1 ⇒ 画叉**)
        app2 = ChordSpeedTest(root=root, merge=False)
        assert app2.merge is False and not hasattr(app2, "kb")
        assert len(app2.kb1.circles) == len(app2.kb2.circles) == 30
        root.update_idletasks()
        g1, g2 = app2.kb1.grid_info(), app2.kb2.grid_info()
        assert g1["column"] == g2["column"] == 0 and g2["row"] > g1["row"], (g1, g2)
        assert app2.kb2.winfo_y() >= app2.kb1.winfo_y() + app2.kb1.winfo_height(), \
            (app2.kb1.winfo_y(), app2.kb2.winfo_y(), app2.kb1.winfo_height())
        assert app2.kb1.winfo_x() == app2.kb2.winfo_x()
        app2.hand = "left"                            # 组合取左手 (半边显示才有键可看)
        app2.code_strokes = ['sf', 'xc']
        app2._paint_targets()
        assert app2.kb1.targets == set('sf') and app2.kb2.targets == set('xc')
        assert all(mk(app2.kb1, k) == '圈' for k in 'sf'), "上块 = 第 1 击 ⇒ 圈"
        assert all(mk(app2.kb2, k) == '叉' for k in 'xc'), "下块 = 第 2 击 ⇒ 叉 (stroke=1)"
        h2 = 'l' if app2.hand == "left" else 'r'     # --split 两图同样只画采集手那一半
        assert app2.kb1.hand == h2 and app2.kb2.hand == h2
        assert not app2.kb1.shown('y' if h2 == 'l' else 'q')
        # 1 击试次的 --split: 下块无目标 (空图), 上块仍是圈
        app2.code_strokes = ['sf']
        app2._paint_targets()
        assert app2.kb2.targets == set() and mk(app2.kb1, 's') == '圈'
        app.stop_guards(); app2.stop_guards(); app3.stop_guards()
        assert not any(hasattr(a, "hook") for a in (app, app2, app3))   # v2.47: 无钩子可卸
        root.destroy()
        print("GUI 冒烟通过: 键位图(图形区分击序 —— 第 1 击=圈 / 第 2 击=叉(长=圈直径, 端点落在圈上) / "
              "共有=圈里一个叉; 标记统一白色; 按下=加粗高亮、松开恢复; 非目标键=骨架圈(按下则亮圈); "
              "半边键盘=只画采集手; 默认两击合并 / --split 两图(下块 stroke=1 画叉); "
              "界面只剩两行文字 (含 `?` 说明书; v2.45)) / "
              "非目标手禁用(忽略不产生R1) / 1击+2击混采 / 记录列 / "
              "完成提示只显示时间(1击 xxms; 2击 xx+xx+xx=xxms 且算式自洽) / "
              "错误捕获(完整组合落盘) / 随机单手(两手都抽到, 无固定开关) / "
              "输入层(只剩摘窗口 IME · 无钩子属性/无 --no-hook · tkinter 事件路径承载按键与"
              "归一化; v2.47 · `--no-ime` 关整层=A/B 对照: 关掉时三条摘除路径一次都不摘; v2.48) / 练习模式单击 / "
              "静默失联防护(按键处理异常隔离 · 落盘失败可见不卡死 · 调度异常不永停 blocked; v2.37) / "
              "收不了尾看门狗(错误捕获态静默 5s 自动收尾落盘 · 漏收松开 20s 收尾 · "
              "错误提示'全部松开即继续' · 试次间隔按键明示未记录; v2.38) / "
              "闪红回归(试次首笔≡后续状态 不闪; v2.39) / "
              "图形口径: 2 击试次首笔即见第 2 击的叉 · 1 击试次全程无叉 (v2.40) / "
              "不提示击次(无边框色/无图例加粗/试次行只写 Trial N, 推进击序画面不变; v2.41) / "
              "界面精简(无采集手说明行/标题平衡行/计数行/操作提示行, 只剩图例+键盘+Trial N; "
              "焦点与超时不再上屏, 但看门狗与真问题告警仍在; v2.43) / "
              "顶部计数行(左 成功/样本 : 右 成功/样本; 口径 = 数据文件, 错误行只加样本, "
              "累加值 ≡ 现扫同一文件; v2.44) / "
              "`?` 说明书(独立文档 采集器说明书.md · 默认收起 · 点开渲染 Markdown 标题/列表 · "
              "缺文件明说路径 · 无图例行; v2.45)")
    finally:
        if tmp_out:
            Path(OUT).unlink(missing_ok=True)
            OUT = real_out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    # --hand 已于 v2.23 移除 (采集手不再是可选项): 保留参数只为给出明确报错, 不改变行为
    ap.add_argument("--hand", nargs="?", default=None, const="auto", metavar="MODE",
                    help="已移除 (v2.23): 采集手固定为『左右 1:1 随机单手』, 无固定单手模式")
    ap.add_argument("--practice", "--drill", action="store_true", dest="practice",
                    help="练习模式 (热身; 别名 --drill)")
    # --no-hook 已于 v2.47 移除 (键盘钩子层整体删除 ⇒ "关掉钩子"不再是可选项):
    # 保留参数只为给出明确报错 (与 --hand 同法), 不改变行为
    ap.add_argument("--no-hook", action="store_true",
                    help="已移除 (v2.47): 键盘钩子层已删, 输入层只剩『摘窗口 IME』")
    ap.add_argument("--split", action="store_true",
                    help="键位图回到旧布局: 两击上下两块图 (v2.26 前; 默认 = 两击合并成一张图)")
    ap.add_argument("--no-ime", action="store_true",
                    help="排障: 不摘除窗口输入法上下文 (回到修复前 —— 中文输入法态下可能收不到按键)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if args.hand is not None:
        ap.error("--hand 已于 v2.23 移除: 采集手固定为『左右 1:1 随机单手』"
                 " (方案要求左右对称 + 双手交集剔除要求两手有同期数据)")
    if args.no_hook:
        ap.error("--no-hook 已于 v2.47 移除: 键盘钩子层整体删除, 现在唯一模式就是"
                 "『摘除窗口 IME + tkinter 事件』(该开关已无对象)")
    if args.selftest:
        selftest()
    elif args.smoke:
        smoke()
    else:
        ChordSpeedTest(practice=args.practice, merge=not args.split,
                       ime=not args.no_ime).run()
