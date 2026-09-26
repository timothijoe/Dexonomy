# 环境安装

## 推荐环境

- Ubuntu/Linux。
- Python 3.10。
- 生成阶段需要与 Torch、Warp 兼容的 NVIDIA 驱动。
- 只做离线数据检查不要求 GPU。

## 初始化代码依赖

```bash
git submodule update --init --recursive
python3.10 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

如果只运行抓取与可视化、暂不生成机械臂轨迹，可以不安装 BODex，并保持 `skip_traj=True`。

## 验证

```bash
.venv/bin/python -c "import mujoco, torch, warp, trimesh, hydra; print('imports OK')"
.venv/bin/python -m compileall -q dexonomy
.venv/bin/dexrun --help
```

导入成功只证明环境可加载，不代表仿真和 GPU 已运行通过。

## Headless 渲染

服务器上保存调试图像时可先设置：

```bash
export MUJOCO_GL=egl
```

GUI 查看需要有效显示环境，不应在无桌面的机器上启用 `debug_view=True`。
