# 查看 Wuji2 纯手型动作优化版本

在仓库根目录运行：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/analyze_wuji2_hand_action.py --fit-hand-only --max-nfev 160
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/export_wuji2_hand_only.py
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/export_wuji2_comparison.py --index-only
.viz-env/bin/python -m http.server 8768 --bind 0.0.0.0 --directory output
```

打开 `http://127.0.0.1:8768/wuji2_hand_only_viewer/` 查看**只有手型优化**的版本；打开 `http://127.0.0.1:8768/wuji2_comparison/` 查看**手与物体交互**的版本。其他电脑访问时，将地址中的 `127.0.0.1` 换成服务器 IP，或使用 SSH 端口转发。两页顶部可互相跳转。

纯手型页面左侧选样本，右上选三阶段；两个手模型的相机同步。浏览器没有 WebGL 时自动进入离线多视角，使用水平、俯仰、滚转三个滑条，或拖动任一手的图片。每张图可下载 GLB。两个输出目录都是生成资源，不纳入 Git；如果只需快速验证，导出器可加 `--ids sh_tripod_obj --output output/wuji2_hand_only_smoke`。
