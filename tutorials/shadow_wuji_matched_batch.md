# 当前全部匹配资产的 Shadow→Wuji 一代多握法迁移

范围与结果见[本轮开发记录](../docs/design/shadow-wuji-matched-assets-batch-v1.md)。用户明确每种资产 3–4 种握法，本轮固定 59 个有来源目录，每个 4 种；缺少来源的 18 个目录延期。本轮目标为 Wuji 一代右手三阶段静态姿态。

在仓库根目录使用 `.viz-env`。先固定计划：

```bash
.viz-env/bin/python tools/batch_shadow_wuji_assets.py \
  --matches output/shadow_wuji_v1/asset_selection_v3/matches.json \
  --output output/shadow_wuji_v1/batch_new --prepare-only
```

然后执行固定计划，最多 4 个 CPU worker：

```bash
.viz-env/bin/python tools/batch_shadow_wuji_assets.py \
  --output output/shadow_wuji_v1/batch_new --resume --workers 4
```

已有终态样本会先校验来源身份和所有结果文件哈希，再复用；来源/模型/代码/配置改变会拒绝续跑。存在未完成目录时不会静默覆盖。失败也有终态记录，不自动无限重试。相同源文件、索引和类别只优化一次，保留对应的全部目标资产。

源握法配置是 `configs/bench2dex/shadow_asset_batch.yaml`，优化配置是 `configs/bench2dex/shadow_retarget_batch.yaml`。选择类别不足时记录实际缺口。源文件及四元数/维度会在建立计划时实际校验。

建立或刷新统一查看入口：

```bash
.viz-env/bin/python tools/review_shadow_wuji_batch.py \
  --batch output/shadow_wuji_v1/batch_new
```

打开输出目录的 `index.html`。无需联网读取结果，页面内已有指标数据，图片和姿态链接采用相对路径。可以按资产、状态或名称过滤，切换带物体/纯手型图，并单击图片放大。

图的顶行是 Shadow 来源，中行是 Wuji 初值，底行是联合优化；列为 pregrasp / grasp / squeeze。纯手型图按各自解剖掌心坐标对齐，原模型尺寸不变。静态候选、几何/动作不合格及输入/执行错误分别显示；数值收敛、迭代预算和时间预算检查点也分别记录。

本次固定计划保存在 `output/shadow_wuji_v1/all_matched_batch_v1/plan.json`，实际结果与查看入口位于同一目录。每例在 `samples/<case_id>/`，包含 `postures.npz`、`result.json`、`comparison.png`、`hand_only/comparison.png` 和 `receipt.json`。

当前候选使用对应 Dexonomy 来源几何与尺度，没有将类别候选替换成原 Bench2Dex USD 执行结果。真实控制、抬升/保持、机械臂可达性和完整任务仍待下一阶段验证。
