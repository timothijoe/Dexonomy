# 本地资源布局

## 可移植契约

代码通过仓库相对路径访问资源：

- `assets/hand/`：随 Git 管理的小型手模型配置、标注和部分模型文件。
- `assets/object/`：仓库外对象、场景、抓取、视觉和权重数据入口。
- `assets/wuji-description/`：仓库外 Wuji2 模型入口。
- `third_party/mujoco_menagerie/`：固定 Git 子模块。
- `third_party/BODex/`：可选轨迹生成子模块。

代码和配置不得写死当前机器的 `/data/...` 路径。部署层负责把入口连接到实际资源根目录。

## 当前机器

当前部署使用：

```text
assets/object -> /data/robotic_data/ztDexonomy/datasets/object
assets/wuji-description -> /data/robotic_data/ztDexonomy/robot_assets/wuji-description
```

原始交接归档位于 `/data/robotic_data/transfer_data/dexonomy_2026-09-25`。该绝对路径只是当前部署事实，不是代码接口。

## 检查命令

```bash
readlink -f assets/object
readlink -f assets/wuji-description
test -d assets/object/DGN_5k/processed_data
test -f assets/wuji-description/hand2/hand2_beta2/body/mjcf/right.xml
git check-ignore -v assets/object assets/wuji-description
```
