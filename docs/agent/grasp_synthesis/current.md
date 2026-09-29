# 抓取生成当前总览

## 当前能力

- [生成流水线](evolution/generation-pipeline.md)：模板、初始化、抓取、评估和模板演化入口均存在。
- [ADMM 优化](evolution/admm-optimization.md)：实现对象接触点和手部接触点的交替更新，以及可微 QP 抓取指标。

## 当前证据

- `dexonomy` 全部 Python 文件已于 2026-09-25 通过 `compileall`。
- CLI 入口、Hydra 配置和主要数据写入路径已通过代码检查确认。
- 当前机器尚未安装项目完整运行环境，因此没有本机生成或评估成功证据。

## 已知限制

- 流水线通过日志文本判断完成，并会重复调用阶段命令；异常条件下可能长期运行。
- 默认 `n_worker=32`，评估进程池使用 `3 * n_worker`，不适合作为首次验证配置。
- ADMM 中存在异常捕获后回退到原始优化的路径，运行统计应区分实际 ADMM 完成与回退。
- Wuji2 迁移已扩展到 16 条 Shadow/Allegro 开发和保留样本；接触目标与短程 MuJoCo 接触力优化已逐例尝试，仍有严重穿透，六方向评估 0/16 通过。尚未运行完整 `grasp`/ADMM；结果见[Wuji2 开发样本](../../design/wuji2-benchmark.md)。
- 教程和当前配置中的部分旧目录名需要后续统一。

相关历史见 [2026-09-25 接收与审计](chronicles/2026-09-25-repository-and-data-audit.md)。
