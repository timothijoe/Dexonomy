# Wuji 一代 / Bench2Dex 第一版检查与数据准备

当前版完成原始资源检查、左右手 URDF→MuJoCo 转换、固定姿态 FK 对照、原演示校验与 ACT 存储准备。尚无新增抓取或自动任务成功。阶段与证据见[开发记录](../docs/design/wuji-bench2dex-v1-progress.md)。

可编辑安装支持 `bench2dex` 命令；非可编辑安装需用 `--config /path/to/Dexonomy/configs/bench2dex/default.yaml` 指定仓库配置与语义文件。教程使用仓库内脚本，避免安装路径影响默认配置定位。

## 环境与路径

从 Dexonomy 根目录运行。MuJoCo 检查环境需要 Python 3.10、NumPy、SciPy、PyYAML、MuJoCo 3.3.3、h5py、Pillow；USD 深度检查另需 usd-core。当前 `.viz-env` 已安装这些依赖。

```bash
export BENCH_ASSETS=/data/robotic_data/ztDexonomy/integrations/bench2dex/assets
export BENCH_DEMOS=/data/robotic_data/ztDexonomy/integrations/bench2dex/teleopdata
export BENCH_EPISODE="$BENCH_DEMOS/dataset/27_ball_box_loading/replay-generalization/episode_000000.hdf5"
```

这些是本机部署路径。迁移到别的机器时替换变量或通过 `--config` 指定配置；配置内相对路径相对于 YAML 文件目录。无需把 MuJoCo、Isaac Lab 与训练依赖安装进同一环境。

## 官方资源恢复

本机已经恢复下列固定版本的选择性资源：202 个资产文件与两条 HDF5 文件，总计约 381 MB；只包含任务 27 所需球、箱子和 Wuji，不包含场景背景、所有干扰物或任务 21。

```bash
# hf download 若受本机 socks:// 代理影响，可为本条命令清空 ALL_PROXY/all_proxy。
.viz-env/bin/hf download Bench2Dex/Assets --type dataset \
  --revision bf65215f844d1fca30750e4cc70d7266650abf0a \
  --include 'Robots_p/ur5+wuji/**' \
  --include 'Objects/053_mini_soccer_ball/**' \
  --include 'Objects/056_tennis_ball/**' \
  --include 'Objects/058_golf_ball/**' \
  --include 'Objects/144_table-tennis/**' \
  --include 'Objects/154_wooden_box/**' \
  --local-dir "$BENCH_ASSETS" --max-workers 4

.viz-env/bin/hf download Bench2Dex/teleopdata \
  dataset/27_ball_box_loading/origin-generalization/episode_000000.hdf5 \
  dataset/27_ball_box_loading/replay-generalization/episode_000000.hdf5 \
  --type dataset --revision dbfb05dfc5b636e5c83925bc28c3041e3d5492a8 \
  --local-dir "$BENCH_DEMOS" --max-workers 2
```

[固定资源清单](../manifests/bench2dex-resources.json)记录官方 revision、LFS SHA-256 或普通 Git 文件的 blob SHA-1。验证不依赖路径名称：

```bash
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" --demo-root "$BENCH_DEMOS" \
  verify-resources --output output/bench2dex_v1/verified_resources.json

.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" --demo-root "$BENCH_DEMOS" \
  inspect-assets --output output/bench2dex_v1/audit

.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" \
  convert-hands --output output/bench2dex_v1/models
```

`inspect-assets` 输出 JSON 与 Markdown，文件存在、未确认和缺失分别记录。`--require-ready` 在 M0 尚未验收时退出码为 2。当前左右手转换通过 URDF/MuJoCo FK 对照，但未进行 Isaac Lab 固定姿态及碰撞、质量惯性和驱动对照。

## HDF5 校验与 ACT 准备

```bash
.viz-env/bin/python tools/bench2dex.py validate-episode "$BENCH_EPISODE" \
  --output output/bench2dex_v1/episode_inspection.json

.viz-env/bin/python tools/bench2dex.py prepare-act "$BENCH_EPISODE" \
  --output output/bench2dex_v1/act_ready/episode_000000.hdf5 --check-only

.viz-env/bin/python tools/bench2dex.py prepare-act "$BENCH_EPISODE" \
  --output output/bench2dex_v1/act_ready/episode_000000.hdf5 --resume

.viz-env/bin/python tools/bench2dex.py validate-episode \
  output/bench2dex_v1/act_ready/episode_000000.hdf5 --require-act \
  --output output/bench2dex_v1/act_validation.json
```

准备操作创建独立副本，保留真实发送动作、回位段和 `meta/homing_start_sim_step`。若存在无动作初始观测，仅删这一行；各列始终使用相同的源帧索引，不移动动作时间。动作列按显式名称重排到状态列顺序。原 RGB 数组转换为 JPEG，已有 JPEG 字节保持不变。内部无效帧、缺少成功声明、错误机器人/关节、回位边界异常和续跑身份不一致均拒绝，不以状态填补动作。

校验默认只检查训练边界 JPEG；`--require-act` 解码全部训练 RGB 帧。结构检查不证明动作一帧偏移或实际任务成功。来源回位标签是否真实仍由原采集器执行证据负责。

实际测试原 ACT 读取器使用另一个 Torch 环境：

```bash
.venv/bench2dex-act-smoke/bin/python tools/check_bench2dex_act.py \
  --bench2dex-root ../Bench2Dex \
  --episode output/bench2dex_v1/act_ready/episode_000000.hdf5 \
  --output output/bench2dex_v1/act_reader_report.json
```

本机环境通过 `uv venv --python /home/linux/anaconda3/bin/python --system-site-packages .venv/bench2dex-act-smoke` 创建，复用 Torch 2.5.1，再安装 NumPy 2.2.6、h5py 3.16、opencv-python-headless 和 einops。新机器请使用已有 ACT 环境；本命令只验证 Dataset 和归一化，不训练策略、不下载权重。

## 姿态诊断预览

```bash
MUJOCO_GL=egl .viz-env/bin/python tools/bench2dex.py preview-hands "$BENCH_EPISODE" \
  --models output/bench2dex_v1/models --frame 400 --output output/bench2dex_v1/preview
```

`comparison.png` 为原 Wuji 左右手在真实记录关节姿态下的离线渲染；`preview_report.json` 保留模型、演示哈希与源帧。它不包含抓取执行或成功判定。

## Isaac Lab 运行时对照接口

尚未在本机执行。已有 Bench2Dex 环境可在其机器人 reset/update 后调用 `dexonomy.integrations.bench2dex.runtime.capture_pose`，按 `model_report.json` 的 neutral / quarter / middle / three_quarters 诊断姿态保存四条记录。诊断允许设置关节状态，必须明确区别于真实控制执行。快照外层字段：

```json
{
  "schema_version": 1,
  "simulator": "isaaclab",
  "robot_key": "multi_ur5_wuji_with_flange",
  "bench2dex_commit": "实际运行代码提交",
  "robot_usd_sha256": "实际加载原始机器人USD的SHA-256",
  "frames": []
}
```

每条记录包含 `posture_name`、全部 52 个 `joint_names`、`qpos_rad`、命名掌心/指尖的 `body_poses_world_wxyz` 与 `capture_mode=kinematic_diagnostic`。该读取适配器只读取运行时状态，不启动模拟器、不控制机器人。文件对照命令为：

```bash
.viz-env/bin/python tools/bench2dex.py --asset-root "$BENCH_ASSETS" \
  compare-runtime isaac_fixed_postures.json --models output/bench2dex_v1/models \
  --output output/bench2dex_v1/runtime_comparison.json
```

即使 FK 通过，M0 仍需单独验收法兰、碰撞表面和动力学参数。此接口不授予抓取成功标签。

## 回归检查

```bash
.viz-env/bin/python -m unittest discover -s tests -v
python -m compileall -q dexonomy/integrations tools/bench2dex.py tools/check_bench2dex_act.py tests
git diff --check
```

所有运行输出、模型转换产物、下载、虚拟环境与图片均不进入 Git。
