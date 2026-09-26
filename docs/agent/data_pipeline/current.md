# 数据与资源当前总览

## 当前能力

- [外部资源布局](evolution/external-resource-layout.md)：正式根目录和项目链接已经建立。
- [Shadow 31 类数据](evolution/shadow-grasp-dataset.md)：分类、规模、字段和缺失类型已经核查。

## 当前证据

- 交接包的七个 Dexonomy 归档、Wuji2 归档及复现文件全部通过 SHA-256 校验。
- 全部七个数据归档已解压，正式数据根目录约 47 GB。
- `assets/object` 与 `assets/wuji-description` 链接可解析，关键文件检查通过。

## 已知限制

- 原始交接归档仍保留，占用约 15 GB，但可用于恢复和校验。
- 数据集内有大量小文件，遍历和全量统计成本较高。
- Shadow 成功抓取数据没有 19 和 21 两类，不能从现有成功数据展示完整 33 类。
- NPY 使用 Python pickle 对象格式，只应读取可信数据。

相关历史见[2026-09-25 数据接收与安装](chronicles/2026-09-25-dataset-receipt-and-installation.md)。
