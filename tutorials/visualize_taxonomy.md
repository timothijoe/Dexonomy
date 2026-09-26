# 浏览 Shadow Hand 抓取图鉴

当前原型展示三种抓取类型，每类三个物体样本，每个样本有 `pregrasp`、`grasp`、`squeeze` 三个阶段。网页默认显示真实场景离线渲染的图片。点击右下角“切换到 3D”后，页面才会加载可旋转和缩放的模型；3D 加载失败时会保留同一阶段的图片。

## 重新导出

在仓库根目录执行：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/export_taxonomy_preview.py
```

导出器读取可信的 Shadow 成功抓取 NPY 和场景模型，写入 `output/taxonomy_preview`。它会为每条记录生成三个 GLB、三张 PNG、`index.json`、网页和本地 `model-viewer` 组件。当前默认共生成 9 条记录、27 个 GLB、27 张 PNG。可用 `--classes` 和 `--samples-per-class` 调整范围；数据中共有 31 类成功抓取，19 和 21 不在其中。

## 打开网页

在仓库根目录启动服务：

```bash
.viz-env/bin/python -m http.server 8765 --bind 127.0.0.1 --directory output/taxonomy_preview
```

同一台机器打开 `http://127.0.0.1:8765/`。跨机器访问时，在浏览器所在机器建立 SSH 转发：

```bash
ssh -L 8765:127.0.0.1:8765 USER@SERVER
```

然后在浏览器所在机器打开同一地址。不要直接双击 HTML 文件；网页需要通过 HTTP 读取索引。页面代码和 3D 组件均为本地文件，不需要 CDN。

## 操作和范围

- 左侧切换类别与样本，底部切换或播放三个阶段。
- 静态图和 GLB 对应同一条源 NPY、同一数组索引、同一阶段。
- 点击右下角“切换到 3D”后，可拖动旋转、滚轮缩放，`R` 重置相机；同一按钮可返回静态图片。
- 当前样本是按对象目录选出的原型样本，并非全数据集中经过质量排序的类别代表；图片和模型只说明姿态的可视化，不证明物理抓取成功。

当前用户已确认静态画面可见；3D 在用户浏览器中尚未验收。如果页面仍出现旧的自动切换行为，请打开 `http://127.0.0.1:8765/?v=static-first-2` 刷新缓存。如果本机可见而你的浏览器不可见，先确认 SSH 转发或服务地址，再检查页面状态提示。
