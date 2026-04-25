# LMR 阈值微调实验 — 设计

**日期**：2026-04-25
**对象**：`algorithms.py` 中 `_alpha_beta` 的 LMR（Late Move Reduction）起步阈值
**版本**：v1（首次用 harness 跑完整流程的 AI 改动）

---

## 1. 背景与动机

`bench/` harness 已经落地并通过自检（sanity 通过、负控 SPRT `accept_H0`）。下一步要用一个真实的 AI 改动跑完整流程，验证 harness 能检出"变强"，而不只是"变弱"。

LMR 阈值是最适合首次试手的参数：
- 单文件、两处一行改动，不改评估函数也不改任何接口
- 方向有研究背书（计算机国际象棋的成熟引擎普遍比当前更激进）
- 如果 hypothesis 错了，回滚成本极低（一行 git checkout）
- 结果不论正负，都能给 harness 提供有意义的信号

## 2. 目标与成功标准

### 2.1 唯一要回答的问题

> 把 LMR 阈值从 `i >= 4` 改成 `i >= 3` 之后，是否在统计上变强？

### 2.2 成功标准

1. **SPRT `accept_H1`** → 改动有效，保留并 commit。
2. **SPRT `accept_H0`** → 改动变弱，`git checkout -- algorithms.py` 回滚，commit 失败结果作为负面记录。
3. **SPRT `undecided` 且 `total >= 600`** → 信号不足；按当前数据 Elo 符号判断；用户决定。
4. 不论结果如何，**流程本身必须跑通**：spec → plan → 改动 → match → 决策；这是本次实验的 meta 目标。
5. 现有测试套件全过；web AI 单步 smoke 不变。

### 2.3 显式范围外

1. 不调任何其他参数（aspiration window、NMP reduction、futility margin、qdepth）
2. 不改 `PROFILE_SETTINGS`
3. 不动评估函数（`getBoardScore`、`_piece_score`、phase multipliers）
4. 不改 harness 本身
5. 不引入新启发或新代码路径

## 3. 改动

`algorithms.py` 两处一行改动：

| 位置 | 改动前 | 改动后 |
|---|---|---|
| 第 1111 行（A 方 maximizer） | `if (i >= 4 and not is_capture and depth_left >= 3` | `if (i >= 3 and not is_capture and depth_left >= 3` |
| 第 1155 行（B 方 minimizer） | `if (i >= 4 and not is_capture and depth_left >= 3` | `if (i >= 3 and not is_capture and depth_left >= 3` |

`reduction = 1` 的减深量保持不变。

### 3.1 为什么是这个方向

当前走法排序逻辑（`_ordered_moves` 第 925 行）按以下优先级：
1. TT 推荐走法（+200,000）
2. 吃子（+80,000，吃军旗 +180,000）
3. 杀手走法（+15,000 / +9,000）
4. 历史启发分数
5. 推进 / 占据要点

排序前 2-3 名通常是"质量明显的好走法"。第 4 名往往已经是"次优 / 平庸"。把 LMR 起步从第 4 提到第 3，意味着对第 3 名也开始减深 1。

计算机国际象棋的现代引擎普遍比这激进得多——Stockfish 在第 2 名之后就开始减深，并且减深量随移动序号增加。本次只动一格，是非常保守的尝试。

### 3.2 风险

第 3 名走法偶尔是真正的最佳。减深搜索后会触发 fail-high 重搜；如果重搜过于频繁，净节点节省可能为负，搜索深度反而下降。

LMR 的内置重搜机制保证**正确性**——任何减深搜索如果分数超出窗口，必定会用全深度重搜。这意味着：
- 改动不会引入棋力 bug
- 最坏情况是搜索效率下降 → 同时间内深度变浅 → Elo 略负

风险已被 harness 兜底：SPRT 会拒绝变弱的改动。

## 4. 验证流程

### 4.1 步骤

1. **复用 v1 baseline**：`bench/snapshots/v1/` 在 harness 自检阶段已经 freeze（与当前 `algorithms.py` 内容一致——LMR 阈值=4 是 v1 的状态）。如果不存在，运行 `python -m bench.cli freeze v1`。
2. **改动 `algorithms.py`**：将第 1111 行和第 1155 行的 `i >= 4` 改为 `i >= 3`。
3. **跑 match**：
   ```
   python -m bench.cli match \
       --baseline v1 --candidate HEAD \
       --tc 0.1 --max-plies 200 --max-games 600 --workers 4 \
       --out bench/results/lmr3-v1-vs-HEAD.json
   ```
   预算：约 30-40 分钟墙钟时间。
4. **读取结果**：从控制台输出读 `SPRT` 字段。
5. **决策与处置**：
   - `accept_H1`：commit 改动 + 结果 JSON（force-add，因为 `bench/results/*.json` 默认 gitignored）
   - `accept_H0`：`git checkout -- algorithms.py` 回滚；commit 结果 JSON 作为反例记录
   - `undecided` & `total >= 600`：根据 Elo 符号决定；用户介入。
6. **回归保护**：
   - `cd bench && pytest` — 全部测试还过
   - web AI 单步 smoke：`.venv/Scripts/python -c "import algorithms, app, time; b=app.init_board(randomize=True); algorithms.set_search_profile('fast'); t=time.perf_counter(); m,s=algorithms.AIMove(b,6); assert m is not None; print(f'ok {time.perf_counter()-t:.2f}s')"`

### 4.2 SPRT 配置

沿用 harness 默认值：
- `H0`: candidate Elo = 0
- `H1`: candidate Elo = +10
- `α = β = 0.05`
- `LLR` 阈值 ≈ ±2.94

如果改动真实 Elo 差在 +10..+30 之间（LMR 微调的典型量级），600 局内 SPRT 应该能给出 `accept_H1`。如果是 +5 或更小，可能 `undecided`。

## 5. 决策记录

无论结果如何，都把以下内容附加到本 spec 文件作为最终记录（实施阶段补充）：
- W / D / L
- Elo ± 误差
- SPRT 决策
- 墙钟时间
- 节点数对比（per-engine `nodes` 中位数，看 LMR 提前是否真的减少了 visited nodes）
- 平均完成深度对比（看是否真的搜得更深了）

这条记录让以后查"我们试过什么"时，不需要再翻 git log。

## 6. Decision Record

**Run date:** 2026-04-25
**Result file:** `bench/results/lmr3-v1-vs-HEAD.json`

| 指标 | 数值 |
|---|---|
| Games | 600（W=196，D=214，L=190） |
| Elo | +3.5 ± 278.7 |
| SPRT | `undecided`（LLR=-0.08） |
| 墙钟 | 2671 秒（44.5 分钟，4 worker） |
| Baseline 节点数中位数（每局） | 38,024 |
| Candidate 节点数中位数（每局） | 37,680（-1%） |
| Baseline 平均完成深度 | 1.88 |
| Candidate 平均完成深度 | 1.89 |

**Decision:** 回滚。`algorithms.py` 还原为 `i >= 4`。

**Notes:**
- Elo 估计 (+3.5) 完全在误差 (±278.7) 之内，统计上无信号。
- 候选确实少访问了 ~1% 的节点（与 LMR 提前一格的预期一致），但平均完成深度只多了 0.01——说明在 tc=0.1 这种极短快棋下，搜索深度的瓶颈不是节点效率，而是时间本身。少访问的节点没转化成更深的搜索。
- 36% 的高和率（214/600）进一步稀释了任何 Elo 信号。
- 改动有可能在更深的搜索（tc=0.5s+，能搜到 4-6 层）下发挥作用——LMR 的边际收益随深度增长。但本次没测。如果以后想重测，应该在 tc=0.3+ 或 max-plies=400+ 的设定下跑。

**Meta**：这次实验的主要价值是**验证了 harness 的"无信号"识别能力**——它正确地报告 `undecided` 而非误判 `accept_H1`，避免了把噪声当成棋力提升来固化。负面结果同样是合理结果。
