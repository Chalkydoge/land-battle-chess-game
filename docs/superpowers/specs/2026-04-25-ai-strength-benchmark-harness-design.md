# AI 强度量化基准 Harness — 设计

**日期**：2026-04-25
**对象**：本仓库的"明棋 AI"（`algorithms.py`，`fast` / `strong` profile）
**版本**：v1（仅含 harness，不含任何 AI 实质改动）

---

## 1. 背景与动机

`algorithms.py` 已经实现了完整的 αβ + 迭代加深 + TT + NMP + LMR + 窄窗口 + 静态搜索 + Zobrist + 历史/杀手启发，evaluation 也带相变分阶段加权和铁路远程威胁感知。引擎层的"显而易见的优化"已经基本到位。

但仓库**没有任何自动化对局基准**：所有调参都靠"看着觉得变强了"。这意味着：

- 任何评估权重、参数、新启发的改动，**无法判断是变强、变弱还是无差**。
- 回退风险高：手感判断容易把"开局更激进"误判为"棋力变强"。
- 加新功能的优先级没有数据支撑。

继续靠手感调引擎的边际收益已经接近零。**先建量化，再谈加强**。

## 2. 目标与成功标准

### 2.1 唯一要回答的问题

> 把当前 `algorithms.py` 改成 X 之后，**X 是否在统计上比改之前更强？**

### 2.2 成功标准

1. 一条命令产出三件事：W/D/L 计数、Elo 估计 ± 误差、SPRT 接受/拒绝/未决。
   ```
   python -m bench.cli match --baseline v1 --candidate HEAD --tc 0.2
   ```
2. 在多进程下（`cpu_count()-1` 个 worker），一次完整 A/B 实验（max 600 局）应在约 30 分钟内出结论。
3. **Sanity check**：`v1 vs v1` 跑出来的 Elo 应落在 0 ± 误差内。这是 harness 自身正确性的回归保护。
4. 现有 web 游戏 (`run-local.bat`) 行为不变，`/api/move` 路径不受影响。

### 2.3 显式范围外

1. **不做任何 AI 实质改动**——harness 只负责测量。
2. **不集成 cutechess / UCI 协议**——军棋规则不兼容标准协议。
3. **不做自动调参**（SPSA / Texel）——后续独立 spec。
4. **不做对人评测、不接入 web UI**——纯 CLI。
5. **不存完整对局棋谱**——只存结果 + 聚合指标；后续若要复盘再加。

## 3. 整体架构

```
bench/
├── __init__.py
├── cli.py              # 命令行入口（freeze / match / summary 子命令）
├── engine.py           # 用 importlib 加载快照，返回引擎对象
├── snapshot.py         # 把当前 algorithms.py + pieceClasses.py 拷到 snapshots/<tag>/
├── layout.py           # 种子化布阵（共享给 app.py 和 bench）
├── game.py             # 单局对局循环，不依赖 Flask
├── match.py            # 比赛调度：多进程池 + 配对开局 + 结果聚合
├── stats.py            # Elo / SPRT 计算
├── snapshots/
│   ├── v1/             # 第一份冻结的 algorithms.py + pieceClasses.py
│   └── HEAD/           # 当前工作区拷贝
└── results/
    └── 2026-04-25-v1-vs-HEAD.json
```

### 3.1 关键设计决策

1. **快照 = 文件副本**，不是 git ref。`bench freeze <tag>` 在执行时把当前的
   `algorithms.py + pieceClasses.py` 复制到 `bench/snapshots/<tag>/`。基线和工作区彻底解耦——工作区改一次就能直接和已冻结的 v1 对打，不需要 git checkout 来回切。
2. **引擎加载用 `importlib.util.spec_from_file_location`**：每个版本独立模块名（如 `engine_v1`、`engine_HEAD`）。两个版本能在同一进程共存，各自有独立的 `TRANSPOSITION_TABLE` / `ZOBRIST_HASH` / `HISTORY_TABLE` 全局状态——它们都是模块级变量，不会相互污染。
3. **每场对局独立子进程**：`multiprocessing.Pool`，每个 worker 进程跑一局完整对局后退出（或下一个任务）。游戏间没有状态泄漏，TT 自然清零。worker 数默认 `cpu_count() - 1`。
4. **共享 `pieceClasses`**：两个引擎都引用同一个 `pieceClasses` 模块。这是有意的——`Piece` / `Post` 是数据容器，没有版本差异，且让两个引擎在同一棋盘对象上交替走子成为可能。如果未来 `pieceClasses` 也需要冻结（罕见），加进 snapshot 即可。

## 4. 单局对局循环（`bench/game.py`）

### 4.1 接口

```python
def play_one_game(
    engine_paths: dict[str, Path], # {"candidate": .../algorithms.py, "baseline": ...}
    sideA_owner: str,              # "candidate" 或 "baseline" — 决定哪边执 A
    layout_seed: int,              # 决定初始布阵（同一 seed 双方共用 → 配对开局）
    tc: float,                     # 每手时控（秒）
    max_plies: int = 300,
) -> GameResult: ...
```

`game.py` 内部用通用的 `"candidate"` / `"baseline"` 标签，不出现 `engine_a` / `engine_b` 这种容易和"side A/B"混淆的命名。

### 4.2 循环骨架

```
1. 用 layout_seed 构造一份固定布阵（同一 seed 双方共用，仅颜色互换）
2. side = "A"; prev_move = None; ply = 0
3. while not terminal and ply < max_plies:
4.     owner = sideA_owner if side == "A" else other(sideA_owner)
5.     engine = loaded_engines[owner]
6.     move, _ = engine._root_search(
7.         board, side, max_depth=999,
8.         alpha=-INF, beta=INF,
9.         prev_move=prev_move,
10.        time_limit_override=tc,
11.    )
12.    engine.applyMove(board, *move)
13.    if move 吃到军旗: 返回 owner 胜
14.    side = swap(side); prev_move = move; ply += 1
15. 超 max_plies 或 isOver() → DRAW
```

### 4.3 GameResult 数据结构

```python
@dataclass
class GameResult:
    winner: str                    # "candidate" / "baseline" / "draw"
    plies: int
    layout_seed: int
    sideA_owner: str               # "candidate" / "baseline"
    per_engine: dict[str, dict]    # {"candidate": {"nodes": ..., "avg_depth": ..., ...}}
```

## 5. 对 `algorithms.py` 的"外科手术"

仅两处改动，限定在 `algorithms.py`，不动 `app.py` 的 web 路径。

### 5.1 给 `_root_search` 加可选时控覆盖

第 1292 行附近：

```python
def _root_search(board, side, maxDepth, alpha, beta,
                 prev_move=None, time_limit_override=None):
    ...
    tl = time_limit_override if time_limit_override is not None \
         else _profile_value("time_limit")
    SEARCH_DEADLINE = time.perf_counter() + tl
```

`AIMove` / `PlayerMove` 调用方不传该参数则行为不变。

### 5.2 抽出种子化布阵

`app.random_layout_for_side` 当前依赖全局 `random`，无 seed 入口。把布阵函数提到一个新的 `layout.py`，签名加上 `rng: random.Random` 参数。`app.py` 改成传一个新建的 `random.Random()`，bench 传 `random.Random(layout_seed)`。

两处都是几行改动，不会影响现有 `/api/move`。

## 6. 比赛调度（`bench/match.py`）

### 6.1 配对开局（paired openings）

消除布阵随机性带来的方差。每个 `layout_seed` 跑两局，引擎执子方互换：

```
seed=42, sideA=candidate, sideB=baseline   →  game 1
seed=42, sideA=baseline,  sideB=candidate  →  game 2
```

算 Elo 时把这两局视为一个 paired sample。这是计算机国际象棋的标准做法（cutechess 也这么干）。

### 6.2 调度循环

```python
games_done = 0
while games_done < max_games:
    # 一批 = workers 个 seed，每个 seed 跑两局（颜色互换），共 2*workers 局
    seeds = [next_seed() for _ in range(workers)]
    jobs = [(seed, sideA_owner) for seed in seeds for sideA_owner
            in ("candidate", "baseline")]
    results = pool.map(play_one_game, jobs)
    for r in results:
        tally.update(r)
    sprt = stats.sprt(tally, elo0=0, elo1=10, alpha=0.05, beta=0.05)
    if sprt.decision != "未决":
        break
    games_done += len(results)
print_summary(tally, sprt)
```

## 7. 统计判定（`bench/stats.py`）

### 7.1 SPRT（Sequential Probability Ratio Test）

```
H0: 候选人 Elo = baseline （无效改动）
H1: 候选人 Elo = baseline + 10 （实质变强）
α = β = 0.05
LLR 阈值: ±log((1-β)/α) ≈ ±2.94
```

每批游戏后更新 LLR；越界即早停。

### 7.2 Elo 估计

```
score = (W + D/2) / N
elo   = -400 * log10(1/score - 1)
err   ≈ 400 * sqrt(W*L + (W+L)*D/4)
        / (N * ln(10) * score * (1-score))
```

### 7.3 典型场景的体感时间（6 worker × tc=0.2s）

| 真实 Elo 差 | 局数 | 墙钟时间 |
|---|---|---|
| ≥ +30 | 60–150 局早停 | ≈ 5–15 分钟 |
| ≈ 0（无效） | 跑满 600 局 | ≈ 30 分钟 |
| ≤ -10（变弱）| 早停拒绝 | ≈ 5–15 分钟 |

## 8. 每局采集的指标

轻量、不影响搜索。每局结束时从两个引擎的全局变量读：

| 指标 | 来源 | 用途 |
|---|---|---|
| `nodes_searched` | 引擎 `NODE_COUNT` 累加 | 搜索效率对比 |
| `avg_depth_completed` | `LAST_COMPLETED_DEPTH` 均值 | 时控压力是否合理 |
| `time_per_move_p50/p95` | 计时 | 时控是否经常打满 |
| `flag_capture` | applyMove 时检测 | 终局原因归因 |
| `mar_lost` | 棋子统计 | 早期溃败信号 |

这些**不进 SPRT**，仅事后归因用。

## 9. 输出格式

`bench/results/2026-04-25-v1-vs-HEAD.json`：

```json
{
  "config": {
    "baseline": "v1",
    "candidate": "HEAD",
    "tc": 0.2,
    "max_plies": 300,
    "workers": 6,
    "elo_bounds": [0, 10]
  },
  "games": [
    {"winner": "candidate", "plies": 142, "seed": 42, "sideA_owner": "candidate", ...},
    ...
  ],
  "summary": {
    "W": 87, "D": 12, "L": 73,
    "elo": 8.4, "elo_err": 14.2,
    "sprt": "未决",
    "wall_clock_seconds": 1820
  }
}
```

## 10. CLI（`bench/cli.py`）

```
python -m bench.cli freeze v1
        # 把当前 algorithms.py + pieceClasses.py 冻结到 bench/snapshots/v1/

python -m bench.cli match \
        --baseline v1 --candidate HEAD \
        --tc 0.2 --max-games 600 --workers 6
        # 跑配对对局，写 results/<日期>-v1-vs-HEAD.json，控制台打印汇总

python -m bench.cli summary bench/results/2026-04-25-v1-vs-HEAD.json
        # 重新打印汇总（不重跑）
```

### 10.1 `--candidate HEAD` 的特殊语义

`HEAD` 是保留名：每次 `match` 启动时**自动**把当前工作区的
`algorithms.py + pieceClasses.py` 重新拷贝到 `bench/snapshots/HEAD/`，覆盖上次。
这让"改代码 → 直接跑 match"无需中间显式 freeze。

任何其他 tag（如 `v1`、`v2_eval_tweak`）必须先 `bench freeze <tag>` 显式冻结，否则报错。这条边界把"我想保留这个版本"和"我刚改完想测一下"分清楚。

**默认值**：`tc=0.2s`、`max_plies=300`、`workers=cpu_count()-1`、`max_games=600`、`elo_bounds=(0,10)`。

## 11. 验证步骤（实现完成后必跑）

1. `bench freeze v1`
2. `bench match --baseline v1 --candidate v1 --tc 0.2 --max-games 200`
   → 期望 Elo 落在 0 ± 30 内（双方代码完全一致，差异仅来自布阵随机）
3. 启 `python app.py`，玩一局，确认 web 路径未受影响。
4. 临时把 `_piece_score` 里所有棋子价值乘 0.5（明显变弱），freeze 成 `v1_weak`，跑 `bench match --baseline v1 --candidate v1_weak`，预期 SPRT 拒绝 H1（Elo 显著为负）。
5. 还原步骤 4 的改动。

通过以上四步，证明 harness 自身的正确性。

## 12. 下一步

本 spec 不包含任何 AI 改进。harness 落地后，每个 AI 改动都将作为独立 spec → 独立实现 → 跑 harness → 看结果接受或回滚。
