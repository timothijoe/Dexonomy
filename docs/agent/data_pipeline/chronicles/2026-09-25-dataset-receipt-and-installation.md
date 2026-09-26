# 2026-09-25：数据接收与安装

## 目标

接收交接包，在 `/data/robotic_data` 下建立正式 Dexonomy 数据根目录，并为项目创建稳定资源入口。

## 实际完成

- 阅读 `HANDOFF.md`、清单、许可说明和解压脚本。
- 对七个数据归档、Wuji2 归档和复现文件执行 SHA-256 校验，全部通过。
- 创建 `/data/robotic_data/ztDexonomy`。
- 解压对象、视觉、Shadow/Allegro 抓取数据、学习权重和 Wuji2 模型。
- 创建 `assets/object` 和 `assets/wuji-description` 软链接。
- 将两个外部资源入口加入 Git 忽略规则。

## 验证证据

关键目录和文件均可读，包括 DGN、Objaverse、Shadow 抓取、Allegro 抓取、normalizing-flow 权重和 Wuji2 右手 MJCF。解压后正式资源约 47 GB，当时 `/data` 尚余约 746 GB。

## 当时限制

没有删除原始交接归档；没有运行数据生成、训练、渲染或 Wuji2 物理验证。

## 后续影响

资源的当前权威布局维护在[外部资源布局](../evolution/external-resource-layout.md)。
