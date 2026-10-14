# Python 模块边界

## 操作层

`dexonomy.op` 导出 `operate_tmpl/init/grasp/grasp_admm/eval/stat/vusd/v3d/traj`。这些函数接收完整 Hydra 配置，属于命令实现入口，不是稳定的细粒度库 API。

## 数据层

- `HandTemplateLoader`：异步维护初始与演化模板缓冲区。
- `ObjSampleDataset` / `get_object_dataloader`：读取场景配置并采样对象初始姿态。

## 仿真层

`MuJoCo_BaseEnv`、`MuJoCo_OptEnv`、`MuJoCo_EvalEnv`、`MuJoCo_VisEnv` 是核心环境类。构造时会加载模型和资源，不能视为无副作用对象。

## 数值层

- `ContactQP`：NumPy/SciPy/qpsolvers 接触力求解。
- `ContactQPTorch`：可微 Torch QP 接口。
- `get_qp_error_batched`：初始化阶段的批量 QP 误差。
- `np_util`、`torch_util`：姿态、四元数和插值工具。

对外新增稳定 Python API 时，应在本文件明确函数签名、单位、异常和版本兼容；当前主要公开界面仍是 CLI 和数据格式。

## Wuji 一代 / Bench2Dex 文件边界（schema v1）

新增模块 `dexonomy.integrations.bench2dex`，导入本身不启动模拟器。`coordinates` 按显式名称重排关节，以米/弧度/wxyz 处理位姿；`delta_pose(a,b)` 返回 `(translation_m, rotation_rad)`。非法维度、重复或缺失关节、非单位四元数均抛出 `ValueError`。

`asset_matching` 对任务资产与本地有效对象进行 YCB 编号/完整名称、类别及家族匹配，输出有来源哈希的 Shadow 姿态提取清单；不自动确认几何等价。`shadow_retarget` 用原始 Wuji 一代模型联合优化三阶段手型、动作和碰撞/接触，输出来源 29 维及目标 27 维姿态；当前为静态候选，`physical_passed=null`。配置、实际首批结果与工具命令见[相关资产迁移记录](../../design/bench2dex-dexonomy-asset-transfer-v1.md)。

`shadow_batch` 固定每资产多握法来源、按文件哈希/索引/类别去重、保存模型与网格输入身份，以有预算的进程池运行并写终态收据。`shadow_retarget.budgeted_solve` 在耗尽数值预算后保留有限且在限位内的已计算检查点；`minimum_surface_distance` 按包围球下界剪枝并保留实际接触深度。它们不执行真实控制或赋予动力学标签。完整批次及审查入口见[本轮记录](../../design/shadow-wuji-matched-assets-batch-v1.md)。

`shadow_thumb_v2` 独立实现拇指掌心相对位置、对掌、指段方向和几何推断的参考指腹方向约束，先拇指再全手有限优化。`choose_refinement` 保留原静态质量通过条件、比较专门指标并限制单项/逐阶段退化。`thumb_v2_batch` 固定第一版输入与两份配置，保存主/保守提案和最终选用结果；不会修改第一版、原关节硬限位或来源尺度。见[第二版记录](../../design/shadow-wuji-thumb-v2.md)。

`shadow_thumb_v3` 新增原始链段方向、按模型指腹侧校准的屈伸符号和几何弯曲目标。`BendDomain` 用两个规范化变量保证末端非反折及组合弯曲范围；`natural_quality` 为明确的机器人几何策略检查，不是人体活动范围认证。`select_candidate` 只允许符合新策略的旧姿态保留。`thumb_v3_batch` 校验第二版来源及全部复用代码身份，数值优化与模型不覆盖旧输出。`tools/finalize_shadow_thumb_v3.py` 提供一次几何修复子集与保留全部尝试的最终发布。见[第三版记录](../../design/shadow-wuji-thumb-v3.md)。

`episodes.validate_episode(path, expected_names, cameras, require_act=False)` 返回结构诊断字典；`prepare_episode(source, destination, expected_names, cameras, check_only=False, resume=False)` 写独立副本与旁置清单，错误和身份不一致抛出 `ValueError`。读取/写入需要 h5py，不能把结构通过解释为真实执行通过。

`runtime.capture_pose(robot, posture_name, semantics_path, env_index=0)` 读取已运行的 Isaac Lab articulation，输出全部关节和显式掌心/指尖记录；不控制机器人。`compare_runtime(snapshot, cfg, models_root)` 检查来源 USD/代码/转换模型身份和全部固定姿态，以掌心为参考比较 MuJoCo FK；该运行时适配器目前只有静态与文件边界检查，尚未在 Isaac Lab 环境中执行。
