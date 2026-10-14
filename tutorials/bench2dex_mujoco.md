# Wuji 一代 MuJoCo 局部抓取操作

使用本机 `.viz-env`；依赖 NumPy、SciPy、MuJoCo 3.3.3、Trimesh、Pillow、PyYAML、usd-core。只需 MuJoCo 环境，不启动 Isaac。结果和限制见[设计/验证记录](../docs/design/wuji-mujoco-grasp-v1.md)。

在 Dexonomy 根目录设置本机资源路径，迁移机器时替换变量：

```bash
export BENCH_ASSETS=/data/robotic_data/ztDexonomy/integrations/bench2dex/assets
export MUJOCO_GL=egl
```

建立/检查模型与角色清单：

```bash
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" \
  convert-hands --output output/bench2dex_v1/models
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" \
  catalog-assets --output output/bench2dex_mujoco/catalog
```

单个真实网球，明确使用近距离预抓取配置（5 mm 初始腕偏移），先仅检查，再生成并真实执行：

```bash
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" generate-grasp \
  --models output/bench2dex_v1/models --grasp-config configs/bench2dex/mujoco_grasp_near.yaml \
  --asset a056_tennis_ball --side right --category 13_Precision_Sphere --seed 0 \
  --output output/bench2dex_mujoco/run_tennis_right --check-only

.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" generate-grasp \
  --models output/bench2dex_v1/models --grasp-config configs/bench2dex/mujoco_grasp_near.yaml \
  --asset a056_tennis_ball --side right --category 13_Precision_Sphere --seed 0 \
  --output output/bench2dex_mujoco/run_tennis_right --execute --resume
```

`--execute` 才运行物理验证；几何通过不自动升级为动力学通过。失败退出码为 2，原因和轨迹保存。输出禁止覆盖；源码、继承配置、输入模型或输出身份变化后应使用新目录，不能冒用续跑。

固定预算、单 worker 的四球双侧批次：

```bash
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" batch-grasps \
  --models output/bench2dex_v1/models --grasp-config configs/bench2dex/mujoco_grasp_near.yaml \
  --side both --seeds 1 --max-cases 8 --output output/bench2dex_mujoco/run_balls --execute --resume
```

针对缺口追加 seeds 1–3（每次尝试均记录，不无限重试）：

```bash
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" batch-grasps \
  --models output/bench2dex_v1/models --grasp-config configs/bench2dex/mujoco_grasp_near.yaml \
  --assets a053_mini_soccer_ball --side right --categories 11_Power_Sphere \
  --start-seed 1 --seeds 3 --max-cases 3 --output output/bench2dex_mujoco/run_gap --execute
```

完整配置的默认接近偏移为 60 mm，近距离配置为 5 mm；二者是不同的开发设置。已有 8 单元覆盖证据采用近距离配置，不能解释为从 Bench2Dex 整机 home 状态的接近成功。

完整默认配置的网球右手单样本也已实际通过，保存在 `output/bench2dex_mujoco/final_single_sample/`；使用时省略 `--grasp-config` 即可。全目录角色清单仍不代表全部资产的生成能力。

真实物理指令重放与可搬运结果包：

```bash
.viz-env/bin/python tools/bench2dex.py replay-physics output/bench2dex_mujoco/run_tennis_right \
  --output output/bench2dex_mujoco/replay_report.json
.viz-env/bin/python tools/bench2dex.py export-grasp output/bench2dex_mujoco/run_tennis_right \
  --output output/bench2dex_mujoco/bundles/run_tennis_right
```

重放从记录的初始状态开始，每步施加实际指令和外力后积分；发生状态偏差或超时会明确报告失败。导出目录和同名 ZIP 均禁止覆盖。包内网格路径是相对路径，原始模型版本与接触参数均保留。包可用于 RTX 机器上的诊断、对照和接口适配，不直接代表 Isaac 的成功演示。

检查“是否由手接触真正承力”，并生成固定世界视角的动画与近景图：

```bash
.viz-env/bin/python tools/audit_bench2dex_grasp.py \
  --sample output/bench2dex_mujoco/tennis_right_friction_solver \
  --output output/bench2dex_mujoco/audits/tennis_preview --render
```

该工具仅初始化一次后逐步重放物理指令；排除不参与求解及零力接触，分别统计闭手和抬升阶段高度。报告与动画写入独立目录，原样本不变。`--render` 需要 Pillow、OpenCV 和可用的 MuJoCo 渲染后端；省略时仅做数值复核。已有结果及握法类别偏差见[复核记录](../docs/design/wuji-mujoco-lift-audit.md)。

可直接查看本次已有的结果：

- `output/bench2dex_mujoco/success_manifest.json`：8 个通过样本、8 个物体/手侧单元。
- `output/bench2dex_mujoco/balls_v2/summary.md`：首次固定 8 例结果，含失败。
- `output/bench2dex_mujoco/preview/execution.png`：真实网球右手四阶段执行图。
- `output/bench2dex_mujoco/bundles/tennis_right_seed0.zip`：代表样本的可搬运包。

运行回归检查：

```bash
.viz-env/bin/python -m unittest discover -s tests -q
python -m compileall -q dexonomy/integrations tools/bench2dex.py tests
git diff --check
```
