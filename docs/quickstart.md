# 开发快速开始

## 前提

- Ubuntu/Linux 环境。
- Python 3.10；上游说明以该版本为准。
- 完整运行需要 NVIDIA GPU、MuJoCo 和项目依赖。
- 当前仓库已经恢复 `third_party/mujoco_menagerie`；BODex 子模块仍未初始化。

## 安装

```bash
git submodule update --init --recursive
python3.10 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

安装后的稳定命令入口来自 `pyproject.toml`：

```bash
dexrun --help
dexsyn --help
dexsyn_admm --help
```

这些命令由 Hydra 解析，主要用法是覆盖配置，而不是传统子命令参数。

## 最短静态检查

```bash
python -m compileall -q dexonomy
git submodule status
test -d assets/object/DGN_5k
test -f assets/hand/shadow/right.xml
```

## 首次运行建议

先按[数据安装教程](../tutorials/data_setup.md)确认资源，再从单个模板、少量对象和单 worker 开始。不要直接启动全部数据集生成。当前仓库尚未在这台机器上完成运行级复验。
