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

- `skip_done=True` 会根据已有输出或路径日志跳过处理。
- `debug_name` 是路径包含过滤，不是精确对象 ID 参数。空字符串会匹配全部路径。
- `debug_view=True` 使用 GUI，并强制部分操作走串行路径。
- `debug_render=True` 保存调试图像；headless 环境通常需要 `MUJOCO_GL=egl`。
- 完整流水线可能持续重试，首次运行不应直接使用默认大规模配置。
