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
