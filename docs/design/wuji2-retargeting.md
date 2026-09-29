# 用 Shadow 抓取初始化 Wuji Hand 2 Beta 2

## 目标与边界

目标是让已有的 Wuji2 右手模型在同一个物体上形成与 Shadow 抓取**功能相近**的 `pregrasp → grasp → squeeze` 姿态，并检验接触和稳定性。Wuji2 的几何模型已经存在；此工作要生成的是它自己的手腕位姿、20 个关节角和抓取数据。最终姿态无需逐关节模仿 Shadow，因为两只手的运动学和接触表面不同。

先完成一个物体、一个抓取样本的可复现闭环，再扩展到其他样本和抓取类别。运动学拟合、碰撞合格、动力学抓取成功是三个不同的验收层级；可视化图像本身不能证明抓取成功。

## 已核实的本地输入

| 项目 | 当前事实 |
| --- | --- |
| Wuji2 模型 | `assets/wuji-description/hand2/hand2_beta2/body/mjcf/right.xml` 能由 MuJoCo 读取；独立模型有 20 个关节、20 个执行器和 5 个指尖 site。装入 Dexonomy 自由手腕环境后，手姿态为 7 + 20 = 27 维。 |
| Shadow 数据 | `assets/object/Dexonomy_GRASP_shadow/succ_collect` 中抽查的文件有 `pregrasp_qpos`、`grasp_qpos`、`squeeze_qpos`，各姿态为 7 + 22 = 29 维，并有 `scene_path`、`scene_scale`。抽查文件没有 `hand_cbody`、`hand_cpn_w`、`obj_cpn_w`、`required_cbody`。 |
| 仿真装配 | `MuJoCo_VisEnv` 和 `MuJoCo_OptEnv` 均可装入 Wuji2。已用 `14_Tripod` 的一个真实物体场景编译 Wuji2 优化环境，但尚未运行 Wuji2 逆运动学或抓取优化。 |
| 可选起点 | 当前图鉴索引中的 `14_Tripod` 样本 01、文件内索引 1，经 `scene_scale` 重建后，在 Shadow 抓取姿态下观察到 5 个手物接触、0 个自接触，最小手物接触距离约 0.55 mm。这只是源姿态筛选线索，不是 Wuji2 成功证据。 |
| 旧演示 | 早期交接说明提到 `reproduction/retarget_shadow_wuji2_demo.py` 及指尖拟合误差，但该脚本在当前工作区不存在；误差数字不能作为当前可复现结果。 |

Wuji2 模型的指尖 site 是运动学查询点，接触优化必须使用实际碰撞身体和碰撞网格。Beta2 指尖传感垫有独立身体，应在接触映射时检查。模型版本和网格路径在实验记录中固定。

## 推荐实现：从 Shadow 目标到 Wuji2 优化

### 1. 重建并检查源场景

从图鉴 `output/taxonomy_preview/index.json` 或直接从成功抓取 NPY 选取源文件与文件内索引。读取 `scene_path`，将该条抓取的 `scene_scale` 乘到活动刚体的场景尺度；沿用同一物体位姿重建 Shadow 与 Wuji2 环境。先在 Shadow 的三个阶段记录手物接触、自碰撞和最大穿透。明显穿透的样本不能直接当作接触真值。

### 2. 生成 27 维 Wuji2 初值

以 Shadow 手腕位姿和五指指尖世界坐标作为**目标**，利用 Wuji2 五个指尖 site 优化 7 维自由腕与 20 维关节。Shadow 当前 XML 没有对应的五个命名指尖 site，须先在远端指节定义一致的局部标记或根据指腹网格求目标点，并记录该定义；不能把旧演示里的近似指尖偏移当作已校准真值。两只手的腕坐标系也应先对齐。目标函数至少包含指尖/掌心位置误差、关节限位、偏离自然初始姿态的代价以及相邻阶段的连续性；必要时加入指尖方向或指腹朝向约束。先拟合 `grasp`，再用它初始化 `pregrasp` 与 `squeeze`。不要把 Shadow 的 22 个关节角截断或按数组位置复制给 Wuji2。

记录优化前后五指误差、关节限位余量、阶段间位姿差，并导出三阶段图像或 GLB。到这一步的结果只标为“运动学迁移”。

### 3. 重建 Wuji2 接触目标并细化

现有 `succ_collect` 文件没有 `grasp`/ADMM 优化器要求的接触输入。需要从 Shadow 源姿态与物体表面提取候选接触区域，再把目标接触点投影到 Wuji2 的实际指腹/碰撞网格，建立 Wuji2 的 `hand_cbody`、手局部接触点、物体世界接触点和必要接触组。不能沿用 Shadow 的身体名称或把指尖 site 当作物理接触点。

先在单样本脚本中调用 `MuJoCo_OptEnv` 做接触力驱动的局部细化，检查穿透、接触身体和关节限制。确认输入模式可靠后，再整理成 Dexonomy `init_data` 结构，复用 `dexonomy/op/gen_grasp.py`；`dexonomy/op/gen_grasp_admm.py` 可作为后续对照。`op=init` 使用**同一只手的模板**匹配物体，不能直接把 Shadow 模板换一个 XML 用作 Wuji2 初始化。若要运行完整流水线，还需 Wuji2 的 Hydra 手配置、`body_group.yaml`、`skeleton.yaml`、必要的 `keypoint.yaml` 与初始模板。

### 4. 动力学评估与展示

用 Wuji2 的质量、执行器与碰撞几何重放三阶段轨迹，检查手物穿透、目标接触是否保持、关节与控制范围、物体位姿变化，以及受扰动后的保持能力。只有通过对应 `eval` 判据的样本才可标为“Wuji2 成功抓取”。把 Wuji2 的三阶段 PNG/GLB 与 Shadow 并排展示，并标明“运动学迁移 / 接触优化 / 评估通过”的状态。

## 与当前代码的衔接

- `tools/export_taxonomy_preview.py` 示范了 `scene_scale`、三阶段样本索引、GLB 和图片的导出方式；它目前固定 Shadow 数据与模型，Wuji2 结果应使用独立输出目录和清晰的手型标识。
- `dexonomy/sim/mujoco_env.py` 提供手模型装配、正向运动学、接触查询、局部接触力优化和仿真评估入口。
- `dexonomy/op/gen_grasp.py` 要求已经准备好的 Wuji2 接触身体和目标接触点；`dexonomy/op/gen_grasp_admm.py` 同样依赖这些输入，并存在 QP 失败后的回退路径，实验记录要区分 ADMM 实际执行和回退。
- `dexonomy/op/gen_init.py` 与 `dexonomy/data/hand_loader.py` 基于手型专属模板和骨架配置；它们适合在单样本迁移成熟后用于批量生成。

## 单样本交付与验收

新 agent 首个交付应包含：可复现脚本、固定的源 NPY 路径与索引、模型版本、场景尺度、三阶段 27 维 Wuji2 姿态、逐指误差、接触/穿透/限位统计、评估结果，以及 Shadow/Wuji2 对照图。先完成可运行的运动学迁移，再依次加入接触细化和动力学评估；各层结果分别命名，避免把视觉相似误称为稳定抓取。

## 2026-09-29 单样本运行结果

已新增 `tools/retarget_wuji2_sample.py`。在仓库根目录运行：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/retarget_wuji2_sample.py
```

脚本固定使用 `14_Tripod/0004e882b42844eda8b4ab7379cb04c8/floating/scale005.npy` 的索引 1，读取 `scene_path`，把逐条 `scene_scale=2.26930633187294` 乘到活动刚体尺度。它按 Shadow 远端视觉网格局部 +Z 最末 10% 顶点的均值定义五个指尖目标；Wuji2 目标点使用模型中的五个 `*_tip` site。两只手的腕初始轴向以局部 X 轴 180° 对齐。脚本保存源标记局部坐标、模型 XML SHA-256、三阶段 27 维姿态、逐指误差、限位与接触统计于 `output/wuji2_single_sample/result.json`，并输出 `comparison.png`。生成目录由 Git 忽略。

抓取阶段五指标记点误差依次为拇指 0.37、食指 3.48、中指 1.84、无名指 2.62、小指 1.54 mm。三个阶段的 Wuji2 关节都在限位内，最小余量约 0.001 rad；预抓取到抓取的腕平移为 26.94 mm，抓取到收紧为 13.29 mm。源 Shadow 抓取阶段在 1 mm 范围内有 5 个手物近接触，但按零接触裕量没有真实穿透接触；源收紧阶段本身有 11.76 mm 最大穿透。Wuji2 运动学姿态三个阶段的最大手物穿透分别为 19.51、15.63、13.02 mm，并有约 1.2–1.3 mm 的自碰撞。因此这些姿态仅是**运动学迁移原型**，尚未达到碰撞合格。

针对成功文件缺失的接触字段，脚本在 1 mm 接触裕量下从源抓取姿态取得拇指、食指、中指候选，再投影到 Wuji2 的真实传感垫碰撞网格，构造 `hand_cbody`、`hand_cpn_w`、`hand_cpn_b`、`obj_cpn_w` 和 `required_cbody`。初始接触点间隙分别为 12.02、0.59、1.34 mm。短程运行 `MuJoCo_OptEnv.apply_contact_forces` 后间隙增至 23.44、28.23、16.13 mm，故候选被拒绝，没有作为优化后的抓取输出。当前尚未把这些字段写成完整 `init_data`，也未运行 `op=grasp` 或 ADMM。

随后用原运动学三阶段轨迹调用 `MuJoCo_EvalEnv.eval_fc` 的六方向评估，结果未通过。该检查不构成抓取成功。下一步应先降低食指/中指近节与物体的穿透，处理源收紧姿态穿透，再重建几何合理的接触法向与掌侧目标，并在碰撞合格后接入完整过滤器和 `op=grasp`。旧 `reproduction` 演示脚本仍不在工作区，其历史数字未用于本次结果。
