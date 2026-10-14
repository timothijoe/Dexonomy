# 外部资源清单

本目录只保存大型资源的元数据和恢复说明，不保存数据本体。

- [Dexonomy 资源清单](dexonomy-resources.yaml)
- [Bench2Dex 固定版本选择性资源清单](bench2dex-resources.json)：262 个 Wuji / 任务 27/21 资产文件、两条任务 27 原始与 RGB 重放演示；264 项来源哈希已复核，未声明完整数据集安装。

字段含义：

- `name`：稳定资源名称。
- `purpose`：用途。
- `source`：上游来源。
- `license`：上游声明许可。
- `archive` / `sha256`：接收归档及校验值。
- `target`：相对正式资源根目录的目标。
- `required`：核心流程是否必需。
- `restore`：恢复方式。

当前机器的正式资源根目录是部署信息，记录在接口文档中；manifest 的目标路径保持相对。
