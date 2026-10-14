# Bench2Dex 相关资产筛选与 Shadow→Wuji 一代姿态迁移

在仓库根目录使用 `.viz-env`。此流程生成静态三阶段候选，真实控制下的动力学验证需后续执行；范围与实际结果见[开发记录](../docs/design/bench2dex-dexonomy-asset-transfer-v1.md)。输出目录禁止覆盖，复跑使用新名字。

先生成本地资产匹配与八个来源姿态的提取清单：

```bash
.viz-env/bin/python tools/match_bench2dex_dexonomy.py \
  --catalog output/bench2dex_mujoco/catalog/catalog.json \
  --output output/shadow_wuji_v1/selection_new
```

输入目录可通过 `--object-root` 修改；分类规则与初始目标在 `configs/bench2dex/dexonomy_asset_matching.yaml`。只搜索本地恢复的网格和 Shadow 数据，不自动下载全部资产。名称/类别匹配不自动判定网格相同。

本次固定八个来源的精确文件、索引与 SHA 已保存在仓库清单中，可直接复现首批姿态迁移：

```bash
export MUJOCO_GL=egl
.viz-env/bin/python tools/retarget_shadow_wuji_v1.py \
  --selection benchmarks/shadow_wuji_bench2dex_v1.json \
  --output output/shadow_wuji_v1/retarget_new
```

仅运行网球：

```bash
.viz-env/bin/python tools/retarget_shadow_wuji_v1.py \
  --selection benchmarks/shadow_wuji_bench2dex_v1.json \
  --assets 056_tennis_ball --max-cases 1 \
  --output output/shadow_wuji_v1/tennis_new
```

目标模型默认为 `output/bench2dex_v1/models/right/hand.xml`，可以用 `--target-model` 指定经过原 URDF 转换的 Wuji 一代模型。配置在 `configs/bench2dex/shadow_retarget.yaml`，超时与数值迭代预算均有限，失败也写入 `summary.json` 和逐例记录；不会无限重试。

把来源物体、选定场景和抓取文件整理成独立子集：

```bash
.viz-env/bin/python tools/stage_shadow_transfer_assets.py \
  --selection output/shadow_wuji_v1/asset_selection_v2/matches.json \
  --output output/shadow_wuji_v1/assets_new
```

输出中的 `assets/object/` 保持原布局，复制后逐文件比较 SHA-256，`resources.json` 记录清单。该子集不是完整模拟器包。

从已生成姿态绘制纯手型对照，按各自解剖掌心坐标对齐，保留原手尺寸：

```bash
.viz-env/bin/python tools/render_shadow_wuji_hand_only.py \
  --result output/shadow_wuji_v1/retarget_selected_v2/056_tennis_ball__13_Precision_Sphere \
  --output output/shadow_wuji_v1/hand_only_new
```

本次已经可看：

- `output/shadow_wuji_v1/asset_selection_v2/matches.md`：77 个任务资产的匹配分层与首批来源。
- `output/shadow_wuji_v1/selected_assets/resources.json`：6 个来源物体、72 个复制文件的校验清单。
- `output/shadow_wuji_v1/retarget_selected_v2/summary.md`：8 个静态候选、穿透和手型/动作指标。
- `output/shadow_wuji_v1/retarget_selected_v2/056_tennis_ball__13_Precision_Sphere/comparison.png`：三阶段带物体对照。
- `output/shadow_wuji_v1/retarget_selected_v2/tennis_hand_only/comparison.png`：纯手型对照。

39 项回归检查命令：`.viz-env/bin/python -m unittest discover -s tests -q`。
