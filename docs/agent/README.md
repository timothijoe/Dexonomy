# Agent 知识库

本目录为维护者和自动化 Agent 提供当前代码事实、长期边界与可追溯历史。操作人员应优先阅读 [教程](../../tutorials/README.md)。

## 推荐顺序

1. [抓取生成](grasp_synthesis/README.md)
2. [数据与资源](data_pipeline/README.md)
3. [仿真与可视化](simulation_visualization/README.md)
4. [接口总览](interfaces/README.md)

## 领域职责

- `grasp_synthesis/`：模板转换、对象初始化、抓取优化、ADMM、评估及流水线编排。
- `data_pipeline/`：对象、抓取、视觉、权重和机器人模型的布局与数据格式。
- `simulation_visualization/`：MuJoCo 环境、运动学、物理评估及 OBJ/USD/规划中的 GLB 导出。
- `interfaces/`：CLI、NPY/YAML、资源路径和外部依赖的稳定边界。

## 维护规则

- `current.md` 只做摘要与导航；详细当前事实写入 `evolution/`。
- `chronicles/` 只追加已发生且有证据的事件；发现错误时新增勘误。
- 未实际运行的功能不得写成运行通过。
- 外部数据、环境和生成结果不进入 Git。
- 未经本次对话明确授权，不执行 Git push、真机动作或外部发布。

## 当前暂缓

- BODex 轨迹生成环境与子模块恢复。
- 全量抓取生成和评估复验。
- Wuji2 碰撞约束映射、动力学抓取和真机验证。
- 31 类交互式图鉴的批量导出；当前已有 3 类、9 个样本的可用原型。
