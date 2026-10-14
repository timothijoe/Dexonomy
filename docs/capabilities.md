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
| Wuji2 三阶段对照 | `tools/export_wuji2_comparison.py`、[可视化设计](design/wuji2-comparison.md) | 本机离线导出与浏览器检查通过 | 16 例 × 3 阶段，手物与掌心对齐纯手型各两手、两角度；无 WebGL 可看图片，GLB 可下载，不能证明抓取成功 |
| Bench2Dex / Dexonomy 资产匹配与提取 | `tools/match_bench2dex_dexonomy.py`、`tools/stage_shadow_transfer_assets.py` | 本地筛选与复制校验已运行 | 77 个任务目录，17 个同 YCB 身份线索、33 个类别候选；6 个来源物体/72 个复制文件；尚未确认网格等价 |
| Shadow→Wuji 一代三阶段迁移 | `tools/retarget_shadow_wuji_v1.py`、[首批记录](design/bench2dex-dexonomy-asset-transfer-v1.md) | 8 个静态候选已运行 | 联合手型/动作/接触/碰撞；使用匹配的 Dexonomy 来源网格，尚无这些新候选的动力学或 Bench2Dex 原网格执行结果 |
| 全匹配资产多握法迁移与统一审查 | `tools/batch_shadow_wuji_assets.py`、`tools/review_shadow_wuji_batch.py` | 59 个资产每个四种已完成 | 236 个覆盖条目 / 172 个独立来源；151 个静态候选、21 个待调整，全部有双模式图和三阶段姿态；缺口延期，尚无本批真实控制验证 |
| 拇指第二版继续优化与成对比较 | `tools/batch_shadow_thumb_v2.py`、`tools/review_shadow_thumb_v2.py` | 同范围第二版已完成 | 132 来源采用新解、40 保留旧解；综合拇指代理误差下降约 11.6%，原静态通过零退化；几何指腹参考非硬件标定，无真实控制验收 |
| 拇指第三版几何弯曲约束与成对比较 | `tools/batch_shadow_thumb_v3.py`、`tools/finalize_shadow_thumb_v3.py`、[第三版记录](design/shadow-wuji-thumb-v3.md) | 同范围第三版及有限修复已完成 | 172 例均无末端反折；136 新版通过、15 合格旧版保留、21 待修正；两个旧几何候选因动作误差降为待修正；64 项回归及全批/浏览器核对通过，仍无动力学标签 |

## 当前数据分类

最新新增：MuJoCo 单手抓取生成、物理执行、固定预算批量、命令重放与结果包。四球双侧 8 个开发覆盖单元均取得本地通过候选，所有通过样本可用记录指令重放；模型与控制器/接触差异详见[MuJoCo 设计与证据](design/wuji-mujoco-grasp-v1.md)。尚无完整任务生成或 Isaac 验收。

2026-10-13 新增 Wuji 一代 / Bench2Dex 检查工具：`tools/bench2dex.py` 提供官方资源校验、资产检查、左右手转换、运行时快照对照、HDF5 校验、ACT 副本准备及姿态预览。官方 204 个选择性文件校验、左右手 URDF/MuJoCo 固定姿态对照与原 ACT Dataset 读取已运行通过。M0 尚未验收，尚无新增抓取或完整任务扩增。复现见[教程](../tutorials/bench2dex_v1.md)，证据见[开发记录](design/wuji-bench2dex-v1-progress.md)。

Shadow 成功抓取数据包含 31 类：编号 1–18、20、22–33。原始标注目录还包含 `19_Distal` 和 `21_Tripod_Variation`，但交付的成功抓取数据中没有这两类。
