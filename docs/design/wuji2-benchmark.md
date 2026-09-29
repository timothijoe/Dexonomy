# Wuji2 迁移开发样本 v1

## 样本与边界

固定清单为 [`benchmarks/wuji2_retarget_v1.json`](../../benchmarks/wuji2_retarget_v1.json)，共 16 条：Shadow 8 条、Allegro 8 条；各有 4 条开发样本和 4 条保留样本。Shadow 覆盖 `1_Large_Diameter`、`11_Power_Sphere`、`14_Tripod`、`16_Lateral`、`24_Tip_Pinch` 五类；Allegro 覆盖 DGN/Objaverse 两个对象数据集及 `fingertip_small`/`fingertip_mid` 两种模板。开发集与保留集使用不同对象 ID，避免同一物体跨集合调参。每条记录固定源路径、索引和源文件 SHA-256。

这是小型**开发基准**，用于暴露格式、尺度、姿态和碰撞问题，不代表上述类别或完整数据集的总体分布。Shadow 先按物体家族和抓取类别分层，再检查候选抓取的近接触和收紧阶段穿透；Allegro 按对象数据集和模板交叉选择。所有源 NPY 都来自本机已安装的可信数据，原始数据与运行输出不入 Git。

Allegro 成功文件使用旧 `rigid_mesh` 场景及 `DGN_obj_v2`/`objaverse` 路径；迁移脚本把路径映射到当前 `DGN_5k`/`objaverse_5k`，先进行路径归一化，再按当前 MuJoCo 接口装配。这些文件有旧命名的接触身体及世界接触点字段，姿态为 7+16=23 维。迁移时按拇指、食指、中指、无名指映射到 Wuji2 四指；小指没有来源目标，不纳入 Allegro 逐指误差。Shadow 数据为 7+22=29 维，仍须按每条 `scene_scale` 缩放物体，并从碰撞近接触重建接触目标。

## 复现命令

在仓库根目录运行：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/run_wuji2_benchmark.py --profile baseline --split all --eval
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/run_wuji2_benchmark.py --profile flexible_wrist --split dev
```

结果保存在被 Git 忽略的 `output/wuji2_benchmark/<profile>/`：每例 `result.json`，以及汇总 `summary.json`/`summary.csv`。单例脚本可加 `--source ... --source-hand allegro --output ...` 导出对照 PNG。示例图在 `output/wuji2_benchmark/examples/al_small_dgn/comparison.png`，原 Shadow 对照在 `output/wuji2_single_sample/comparison.png`。

## 本机验证与参数决定

使用 `.viz-env` 的 MuJoCo 3.3.3 完整运行基线 16 例，全部成功生成三阶段 Wuji2 27 维姿态并通过 JSON 输出检查。抓取阶段结果：

| 来源 | 例数 | 平均逐指位置误差 | 平均最大手物穿透 | 六方向评估通过 |
| --- | ---: | ---: | ---: | ---: |
| Shadow | 8 | 1.70 mm | 12.91 mm | 0 |
| Allegro | 8 | 1.77 mm | 11.66 mm | 0 |

全部 16 例的源手收紧阶段也有约 7–18 mm 穿透，所以源 `squeeze_qpos` 不能直接充当无碰撞监督。Wuji2 局部接触力优化在 2 例满足当前间隙、手物及自碰撞筛选，但这些候选仍未通过六方向评估；其余 14 例候选被拒绝。该筛选只是局部改进判定，不等同于稳定抓取。

在 8 条开发样本上，将掌心、手腕和关节先验权重从 `25/8/0.75` 降到 `10/3/0.25` 后，平均逐指误差从 1.59 降至 0.38 mm；平均最大手物穿透只从 13.69 降至 13.34 mm，且部分 Allegro 自碰撞加重。**因此保留 `baseline` 为后续物理开发基线**，不把更小的指尖误差当作抓取质量提升。保留集只用基线运行，没有用于这一参数选择。

下一步应在拟合目标中加入碰撞几何与指腹朝向约束，按源手分别校准腕坐标系，并把收紧阶段改为由 Wuji2 接触与物理约束生成。先在 16 例开发/保留划分上检查穿透和接触筛选，再扩大样本覆盖。
