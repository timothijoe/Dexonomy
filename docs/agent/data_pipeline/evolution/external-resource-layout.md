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
