# 外部系统与依赖

## MuJoCo

项目固定依赖 `mujoco==3.3.3`。MuJoCo 用于模型装配、正向运动学、接触优化、评估和可视化。GUI 与 headless 渲染属于不同运行路径。

## NVIDIA Warp 与 Torch

初始化阶段使用 Warp 做网格碰撞查询，使用 Torch 做批量优化和 QP。GPU ID 由 `init_gpu` 配置。

## USD

`usd-core` 用于 USD 导出。USD 文件需要 usdview、Omniverse 或其他支持工具打开；它不是浏览器原生格式。

## BODex/cuRobo

BODex 是可选轨迹生成依赖。只有 `skip_traj=False` 时需要。当前子模块未初始化，轨迹功能未在本机验证。

## 数据来源

Dexonomy 数据来自官方 Hugging Face 数据集，项目声明为 CC BY-NC 4.0。Wuji Hand 2 模型来自固定 Git 提交，采用 MIT。详细版本见[资源 manifest](../../../manifests/dexonomy-resources.yaml)。

## 真机边界

当前仓库没有经过本机确认的 Wuji2 真机控制链路。交接样例只做 Shadow 到 Wuji2 的运动学拟合，不得作为真机目标或抓取成功证据。
