# 2026-09-25：仓库与数据审计

## 目标

阅读当前分支代码、Markdown、交接文件与外部数据，建立后续算法和可视化工作的可信起点。

## 实际完成

- 确认 `dexrun`、`dexsyn`、`dexsyn_admm` 的真实入口。
- 阅读模板、初始化、原始抓取、ADMM、评估、统计和可视化模块。
- 确认当前分支为 `dev-sep-25-branch`。
- 执行 `python -m compileall -q dexonomy`，返回成功。
- 未运行 GPU 初始化、MuJoCo 抓取、评估或完整流水线。

## 当时限制

默认 Python 环境缺少 MuJoCo、Hydra 和项目依赖；BODex 子模块未初始化。MuJoCo Menagerie 子模块随后在同日恢复到仓库固定提交。

## 后续影响

所有运行级结论必须在独立 Python 3.10 环境中重新验证。生成流水线的长期当前事实维护在[生成流水线纪传体](../evolution/generation-pipeline.md)。
