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
| Wuji Hand 2 模型 | `assets/wuji-description` | 模型已安装 | Beta2 模型可读，已装入一个真实物体场景的 MuJoCo 优化环境；尚无 Wuji2 抓取结果 |
| Shadow 网页图鉴 | `tools/export_taxonomy_preview.py` | 静态首屏获用户确认 | 3 类 × 3 样本 × 3 阶段，27 个 GLB、27 张 PNG 和 1620 个预渲染视角引用；三方向模式获用户正面反馈，实时 3D 在用户浏览器不可用 |
| Wuji2 抓取迁移 | `tools/retarget_wuji2_sample.py`、[开发样本](design/wuji2-benchmark.md) | 16 例运动学原型已运行 | Shadow/Allegro 双来源、开发/保留集与批量报告；16 例均有物理缺陷，六方向评估 0/16 通过 |

## 当前数据分类

Shadow 成功抓取数据包含 31 类：编号 1–18、20、22–33。原始标注目录还包含 `19_Distal` 和 `21_Tripod_Variation`，但交付的成功抓取数据中没有这两类。
