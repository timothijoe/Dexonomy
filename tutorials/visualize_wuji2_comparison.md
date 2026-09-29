# 查看 Wuji2 迁移对照

这是**手与物体交互版本**。只优化手部动作、去掉物体的第二个版本见[纯手型可视化教程](visualize_wuji2_hand_only.md)。两个页面可通过同一 `output` 目录的 HTTP 服务访问并互相跳转。

先确保[开发样本](../docs/design/wuji2-benchmark.md)的基线结果存在。在仓库根目录依次执行：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/run_wuji2_benchmark.py --profile baseline --split all --eval
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/export_wuji2_comparison.py
.viz-env/bin/python -m http.server 8767 --bind 0.0.0.0 --directory output/wuji2_comparison
```

同机浏览器打开 `http://127.0.0.1:8767/`；同一局域网中的其他电脑打开 `http://服务器IP:8767/`。跨网络浏览时，可在浏览器所在机器运行 `ssh -L 8767:127.0.0.1:8767 USER@SERVER` 后打开本机地址。也可以直接打开生成的 `output/wuji2_comparison/index.html` 查看静态图和离线多视角：样本索引已经嵌入页面，视角图片从同目录下的 `orbit/` 读取。实时 3D 组件需通过 HTTP 地址加载。若页面空白，先确认访问的是端口 8767 的根路径 `/`，且浏览器能够读取同目录的 `app.js`、`assets/` 与 `orbit/`。

左侧选择来源手型与样本，右上切换预抓取、抓取、收紧。上排比较同一物体的两手姿态，下排比较去掉物体并对齐掌心和指根后的手型。「多视角旋转」提供 12 个水平角度 × 5 个俯仰角度；下方分成「水平环绕」「上下俯仰」「画面滚转」三个滑条，也可拖动任一格同步切换四格。浏览器无法使用 WebGL 时会自动进入此模式，并把「实时 3D」明确标为不可用。画面滚转是图片平面旋转，水平和俯仰则是重新渲染的相机角度。支持 WebGL 的浏览器可用「实时 3D」加载 GLB，拖动时同步四格观察方向，滚轮缩放当前格；模型载入或画面检查失败会回到离线多视角。点击「返回图片」可切回两个基准角度。每张图右上可下载当前 GLB。页面下部列出当前阶段的指尖误差、穿透和评估状态；这批结果均为运动学原型，不代表稳定抓取。

只导出两个样本做快速检查时，可使用 `--ids sh_tripod_obj al_small_dgn --output output/wuji2_comparison_smoke`。完整生成目录为 `output/wuji2_comparison`，不纳入 Git。生成逻辑和手型对齐方式见[设计说明](../docs/design/wuji2-comparison.md)。
