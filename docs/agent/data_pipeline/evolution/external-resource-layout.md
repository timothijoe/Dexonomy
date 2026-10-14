# 外部资源布局

## 当前部署

当前机器使用 `/data/robotic_data/ztDexonomy` 作为正式资源根目录：

```text
/data/robotic_data/ztDexonomy/
├── datasets/object/
│   ├── DGN_5k/
│   ├── objaverse_5k/
│   ├── Dexonomy_GRASP_shadow/
│   ├── rss_DGN_allegro/
│   ├── rss_objaverse_allegro/
│   └── dexonomy_shadow_nflow_cond/
└── robot_assets/wuji-description/
```

仓库入口：

- `assets/object` → 正式对象和数据目录。
- `assets/wuji-description` → Wuji Hand 2 模型。

两个入口均由 `.gitignore` 忽略。代码中的 `asset_root=assets` 保持不变，因此运行配置无需写死当前机器的绝对路径。

## 恢复来源

接收归档位于 `/data/robotic_data/transfer_data/dexonomy_2026-09-25`，包含校验文件、解压脚本、许可说明和复现样例。恢复步骤见[数据安装教程](../../../../tutorials/data_setup.md)和[资源清单](../../../../manifests/dexonomy-resources.yaml)。

## 当前验证

所有交付文件校验通过；目标目录、关键模型、对象、抓取、视觉和权重文件均已检查。

## 2026-10-13：Dexonomy 与 YCB 的关系核查

Dexonomy 不是 YCB 的别名，而是使用多来源物体生成的灵巧抓取数据集。[Dexonomy 论文第 V 节](https://arxiv.org/html/2504.18829v1#S5)声明物体来自 DexGraspNet 的 5,697 个资产和额外从 Objaverse 抽取的 5,000 个资产，共 10,697 个物体，生成约 950 万条、31 类 Shadow 抓取。

DexGraspNet 本身也混合多个物体来源：[原论文 III-A](https://arxiv.org/html/2210.02697v2#S3.SS1)列出 ShapeNetCore、ShapeNetSem、YCB、BigBIRD、Grasp、KIT 与 Google Scanned Objects。因此 YCB 是上游来源之一，不能将全部 Dexonomy 物体称为 YCB，也不应将 DGN 子集全部称为 ShapeNet。

本机 `DGN_5k/valid_split/all.json` 确认有 5,697 个条目，其中 48 个名称包含 `ycb`，如 `ddg_ycb_015_peach`、`ddg_ycb_004_sugar_box`。`processed_data` 有 5,751 个目录，其中 49 个名称包含 `ycb`；目录总数与有效划分条目数不同，不能混用。这些名称统计是本地核查证据，不等同于逐网格完成上游身份匹配。

当前 Wuji 首版使用的四种球直接来自 Bench2Dex 任务 27 的原始 USD 资产；未从 Dexonomy/YCB 子集中替换物体。具体来源与版本见[任务资产覆盖记录](../../../design/bench2dex-object-action-coverage.md)与 Bench2Dex 资源清单。
