# 常见问题

## `ModuleNotFoundError: mujoco` 或 `omegaconf`

当前 shell 使用的不是项目环境。执行：

```bash
.venv/bin/python -c "import mujoco, omegaconf, hydra"
```

如果失败，重新按[环境安装](environment_setup.md)安装依赖。

## Shadow 网格找不到

`assets/hand/shadow/right.xml` 引用 `third_party/mujoco_menagerie/shadow_hand/assets`。执行：

```bash
git submodule update --init third_party/mujoco_menagerie
```

## 对象场景或网格找不到

检查 `assets/object` 是否为有效入口，并确认场景配置中的相对路径可解析：

```bash
readlink -f assets/object
test -d assets/object/DGN_5k/scene_cfg
test -d assets/object/objaverse_5k/processed_data
```

## OpenGL 或无显示错误

保存 headless 调试图像时尝试 `export MUJOCO_GL=egl`。无桌面环境不要启用 `debug_view=True`。

## 完整流水线一直不退出

`dexsyn` 根据日志固定文本判断完成并会重试。检查各阶段 `main.log`、磁盘、GPU、上游输出和异常堆栈。必要时先停止流水线，改为逐个运行 `dexrun` 定位问题。

## 进程或内存过多

首次运行设置 `n_worker=1`。评估默认创建 `3 * n_worker` 个进程；不要在资源未知时使用默认 32。

## 数据中的 19 和 21 类在哪里

原始 Shadow 标注有 `19_Distal` 和 `21_Tripod_Variation`，交付的成功抓取数据没有对应目录。它们不能被报告为已有成功数据。

## 图鉴页面直接双击后没有加载模型

浏览器通常禁止本地文件页面通过 `fetch` 读取 `index.json`。不要直接打开 `index.html`，应在 `output/taxonomy_preview` 中运行 Python HTTP 服务，再访问 `http://127.0.0.1:8000/`。
