# 命令行接口

## 安装后入口

| 命令 | Python 入口 | 用途 |
| --- | --- | --- |
| `dexrun` | `dexonomy.main:main` | 运行一个操作 |
| `dexsyn` | `dexonomy.script:main` | 原始算法完整流水线 |
| `dexsyn_admm` | `dexonomy.script_admm:main` | ADMM 完整流水线 |
| `dexkill` | `dexonomy.kill:main` | 按当前实验配置终止进程 |

等价模块入口为 `python -m dexonomy.main`、`python -m dexonomy.script` 等。教程优先使用安装后的命令，以保持路径解析一致。

## 单操作选择

`dexrun` 通过 Hydra 配置组 `op=...` 选择操作：

- `tmpl`：模板转换。
- `init`：对象位姿初始化。
- `grasp`：原始手姿态优化。
- `grasp_admm`：ADMM 手姿态优化。
- `eval`：仿真评估。
- `stat`：统计。
- `v3d`：OBJ 导出。
- `vusd`：USD 导出。
- `traj`：轨迹生成；依赖 BODex。

## 配置覆盖

全局配置直接覆盖，例如：

```bash
dexrun op=grasp hand=shadow exp_name=smoke n_worker=1 debug_name=OBJECT_ID
```

完整流水线使用 `+init.`、`+grasp.`、`+grasp_admm.`、`+eval.`、`+traj.` 将参数转交给具体阶段：

```bash
dexsyn hand=shadow exp_name=smoke 'tmpl_name=[1_Large_Diameter]' 'init_gpu=[0]' +init.object.n_cfg=1
```

## 运行语义

Wuji 一代新增入口为 `python tools/bench2dex.py`（或可编辑安装后的 `bench2dex`），使用 argparse，独立于原 Hydra 操作。子命令包括 `verify-resources`、`inspect-assets`、`convert-hands`、`compare-runtime`、`validate-episode`、`prepare-act`、`preview-hands`。全局路径参数放在子命令前；非法数据和未通过的验证退出码为 2。`prepare-act` 支持 `--check-only` 与基于来源/配置/输出哈希的 `--resume`，禁止覆盖原演示。入口、依赖与命令见[教程](../../../tutorials/bench2dex_v1.md)。

Shadow 来源迁移另提供 `tools/match_bench2dex_dexonomy.py`、`tools/stage_shadow_transfer_assets.py`、`tools/retarget_shadow_wuji_v1.py` 和 `tools/render_shadow_wuji_hand_only.py`。分别负责匹配/来源提取、资源子集复制校验、有限预算三阶段静态优化、掌心对齐纯手型渲染。全部禁止覆盖已有输出目录，迁移的逐例停止原因写入报告；本批不包含真实动力学控制或完整任务。命令见[迁移教程](../../../tutorials/shadow_wuji_asset_transfer.md)。

`tools/batch_shadow_wuji_assets.py` 新增固定多握法资产计划、最多四个 CPU worker 与来源/结果校验续跑；`--prepare-only` 保存计划，`--resume` 只复用通过哈希检查的终态样本。`tools/review_shadow_wuji_batch.py` 根据实际逐样本结果生成统一离线页面及 Markdown 索引。当前完整批次 59 个资产每个四种已完成，命令见[批量教程](../../../tutorials/shadow_wuji_matched_batch.md)。

拇指第二版另用 `tools/refine_shadow_thumb_v2.py` / `tools/batch_shadow_thumb_v2.py`，只读第一版姿态继续优化，保留原质量检查并保存最多两个已声明配置提案。`tools/review_shadow_thumb_v2.py` 展示 Source / V1 / 选用结果与未采用提案；`tools/check_shadow_thumb_v2.py` 校验结果并生成成对拇指指标。入口及边界见[第二版教程](../../../tutorials/shadow_wuji_thumb_v2.md)。

拇指第三版用 `tools/refine_shadow_thumb_v3.py` / `tools/batch_shadow_thumb_v3.py`，从第二版选用姿态继续，加入末端非反折和组合弯曲可行域以及朝向发布检查。`tools/check_shadow_thumb_v3.py` 独立测量几何角并检查全批来源/结果，`tools/review_shadow_thumb_v3.py` 展示 Source / V2 / 本次选用。只有满足新检查的旧姿态可保留，新旧皆不合格时明确待修正。入口及边界见[第三版教程](../../../tutorials/shadow_wuji_thumb_v3.md)。

MuJoCo 局部部分增加 `catalog-assets`、`generate-grasp`、`batch-grasps`、`replay-physics`、`export-grasp`。生成支持固定种子、校验续跑与只检查；批量为单 worker、显式 max-cases / seed 范围，失败保存而不无限重试。结果区分几何、MuJoCo 局部动力学及未验证的 Isaac/完整任务层级。详见[局部生成教程](../../../tutorials/bench2dex_mujoco.md)。

- `skip_done=True` 会根据已有输出或路径日志跳过处理。
- `debug_name` 是路径包含过滤，不是精确对象 ID 参数。空字符串会匹配全部路径。
- `debug_view=True` 使用 GUI，并强制部分操作走串行路径。
- `debug_render=True` 保存调试图像；headless 环境通常需要 `MUJOCO_GL=egl`。
- 完整流水线可能持续重试，首次运行不应直接使用默认大规模配置。
