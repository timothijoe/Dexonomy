# Dexonomy 项目交接（2026-09-26）

## 当前目标和结论

用户希望先看到 Shadow Hand 与物体的抓取交互，优先 3D，可用 2D 兜底；随后计划把手换成 Wuji Hand 2 Beta 2 并重新优化抓取。

Shadow 图鉴首屏显示真实场景的 2D PNG，只有点击“切换到 3D”才载入交互模型；三个阶段分别有对应图片和 GLB。当前仅覆盖 `1_Large_Diameter`、`14_Tripod`、`24_Tip_Pinch`，每类三个样本，总计 9 条记录、27 个 GLB 和 27 张 PNG。用户曾反馈自动切换 3D 时画面闪现后消失，因此取消了自动切换。用户随后确认“现在至少可以看了”，但又反馈 3D 似乎无法显示。静态首屏在用户访问路径上已可见；3D 交互仍未获用户确认。

## 文件和运行

- `tools/export_taxonomy_preview.py`：读取可信 Shadow NPY，使用 MuJoCo 和 Trimesh 导出 GLB、PNG、JSON。
- `tools/taxonomy_preview.html`、`tools/taxonomy_preview.js`：浏览器界面与交互代码。
- `tools/vendor/model-viewer.min.js`：本地 3D 组件。
- `output/taxonomy_preview`：当前生成产物，已被 Git 忽略。重新运行导出器会同步网页副本和三阶段资产。
- `tutorials/visualize_taxonomy.md`：运行与远程访问命令。
- `docs/design/wuji2-retargeting.md`：Wuji2 换手及重新优化方案。

在仓库根目录：

```bash
MUJOCO_GL=egl PYTHONPATH=. .viz-env/bin/python tools/export_taxonomy_preview.py
.viz-env/bin/python -m http.server 8765 --bind 127.0.0.1 --directory output/taxonomy_preview
```

同一台机器打开 `http://127.0.0.1:8765/`。跨机器访问时，需在浏览器所在机器建立 `ssh -L 8765:127.0.0.1:8765 USER@SERVER` 转发。

## 已做的本机检查

- 重新导出 9 条记录，检查 27 个 PNG、27 个 GLB 均存在，且同一样本的三阶段 PNG 内容不同。
- 根据抓取文件逐条 `scene_scale` 调整活动物体尺度；此前忽略倍率曾造成部分画面手物分离。
- Chrome headless 截图可见蓝色手、灰色物体；静态首屏图片 `naturalWidth=960` 且 3D 层隐藏。
- 浏览器脚本检查了阶段、类别、样本切换，3D 模型加载与可见，模拟 3D 错误后静态预览恢复。
- 针对用户反馈取消了自动进入 3D，并改成点击时才导入 3D 组件；本机 Chrome 在打开后第 1 秒和第 24 秒均保持图片可见，3D 组件未加载。手动进入 3D 和返回静态也已检查。
- 针对用户侧 3D 问题加入 WebGL 检查、模型渲染帧检查和当前 GLB 下载入口；本机检查了正常渲染、禁用 WebGL、模拟空白帧和多个样本切换。用户侧仍需复测。
- 运行了 `node --check`、Python `compileall`、`git diff --check`，并核对模板与输出副本。

自动检查仅覆盖本机浏览器。用户已在自己的访问路径确认静态画面可见；不能据此推断 3D 在用户浏览器中可用。

## Wuji2 边界

官方 Beta 2 右手 MJCF 在 `assets/wuji-description/hand2/hand2_beta2/body/mjcf/right.xml`，含 20 个驱动关节及五个指尖 site。Shadow 数据为 7 维腕加 22 个关节，不能直接换模型重放。交接包 `reproduction/retarget_shadow_wuji2_demo.py` 曾完成一条样本的指尖位置拟合，但存在源姿态穿透和未做动力学验证的问题。下一步先复现并校准单样本，再做碰撞约束优化、MuJoCo 评估；详细步骤见方案文档。

## 后续工作

1. 在用户浏览器中确认手动 3D 切换、旋转和阶段切换；若 3D 仍为空白，保留静态模式并收集浏览器与控制台信息。
2. 评估样本代表性、静态图构图和不同浏览器的兼容性。
3. 按 Wuji2 方案完成单样本迁移、约束优化和动力学评估，再考虑批量覆盖 31 类。

没有运行完整抓取生成或 Wuji2 动力学实验。提交状态以当前 Git 记录为准。
