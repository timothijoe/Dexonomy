# 查看 Wuji2 迁移对照

先确保[开发样本](../docs/design/wuji2-benchmark.md)的基线结果存在。在仓库根目录依次执行：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/run_wuji2_benchmark.py --profile baseline --split all --eval
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/export_wuji2_comparison.py
.viz-env/bin/python -m http.server 8767 --bind 0.0.0.0 --directory output/wuji2_comparison
```

同机浏览器打开 `http://127.0.0.1:8767/`；同一局域网中的其他电脑打开 `http://服务器IP:8767/`。跨网络浏览时，可在浏览器所在机器运行 `ssh -L 8767:127.0.0.1:8767 USER@SERVER` 后打开本机地址。也可以直接打开生成的 `output/wuji2_comparison/index.html` 查看静态图片：样本索引已经嵌入页面，图片仍从同目录下的 `assets/` 读取。3D 组件需通过 HTTP 地址加载。若页面空白，先确认访问的是端口 8767 的根路径 `/`，且浏览器能够读取同目录的 `app.js` 与 `assets/`。

左侧选择来源手型与样本，右上切换预抓取、抓取、收紧，工具栏切换两个预渲染角度。上排比较同一物体的两手姿态，下排比较去掉物体并对齐掌心和指根后的手型。点击「开启 3D 旋转」后，四格会加载当前阶段的 GLB；在任一格拖动可旋转四格观察方向，滚轮可缩放当前格。点击「返回图片」可切回共用相机和尺度的静态图。浏览器 WebGL 不可用或模型画面未正常显示时，页面保留图片并给出提示。每张图右上可下载当前 GLB。页面下部列出当前阶段的指尖误差、穿透和评估状态；这批结果均为运动学原型，不代表稳定抓取。

只导出两个样本做快速检查时，可使用 `--ids sh_tripod_obj al_small_dgn --output output/wuji2_comparison_smoke`。完整生成目录为 `output/wuji2_comparison`，不纳入 Git。生成逻辑和手型对齐方式见[设计说明](../docs/design/wuji2-comparison.md)。
