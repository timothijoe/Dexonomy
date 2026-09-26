# 项目能力总表

| 能力 | 当前入口 | 状态 | 证据与限制 |
| --- | --- | --- | --- |
| 人工标注转模板 | `dexrun op=tmpl` | 代码已确认 | 校验接触点与身体名称；当前环境尚未运行 |
| 对象位姿初始化 | `dexrun op=init` | 代码已确认 | Warp、Torch、GPU/CPU 路径存在；当前环境尚未运行 |
| 原始抓取优化 | `dexrun op=grasp` | 代码已确认 | MuJoCo CPU 多进程；当前环境缺少完整依赖 |
| ADMM 抓取优化 | `dexrun op=grasp_admm` | 代码已确认 | CPU 路径为默认，含可微 QP 与失败回退；尚未复验 |
| 抓取评估 | `dexrun op=eval` | 代码已确认 | 以物体平移与旋转阈值判定；尚未复验 |
| 完整流水线 | `dexsyn`、`dexsyn_admm` | 代码已确认 | 通过日志文本判断阶段完成，存在无限重试风险 |
| OBJ 导出 | `dexrun op=v3d` | 代码已确认 | 可导出手、物体、接触与骨架；尚未运行 |
| USD 导出 | `dexrun op=vusd` | 代码已确认 | 支持多个姿态序列；缺少分类导航与网页浏览 |
| 统计计算 | `dexrun op=stat` | 代码已确认 | 读取结果目录并计算覆盖、多样性等指标；尚未运行 |
| 31 类 Shadow 抓取数据 | 外部数据根目录 | 数据已安装 | 约 150 万个 NPY 文件；缺少分类 19 和 21 |
| DGN/Objaverse 对象与视觉数据 | `assets/object` | 数据已安装 | 归档校验通过，解压后可读 |
| Wuji Hand 2 模型 | `assets/wuji-description` | 模型已安装 | 固定版本模型可读；仅交接样例曾做运动学映射 |
| Shadow 网页图鉴 | `tools/export_taxonomy_preview.py` | 静态首屏获用户确认 | 已生成 3 类 × 3 样本 × 3 阶段，共 27 个 GLB 和 27 张真实场景 PNG；用户侧 3D 尚未验收 |
| Wuji2 抓取迁移 | 官方 Beta 2 模型与交接样例 | 方案阶段 | 单样本指尖运动学拟合已有交接证据；碰撞约束优化和动力学抓取尚未完成 |

## 当前数据分类

Shadow 成功抓取数据包含 31 类：编号 1–18、20、22–33。原始标注目录还包含 `19_Distal` 和 `21_Tripod_Variation`，但交付的成功抓取数据中没有这两类。
