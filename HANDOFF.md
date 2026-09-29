# Dexonomy 项目交接（更新于 2026-09-29）

## 2026-09-29 Wuji2 单样本补充

当前仓库已新增 `tools/retarget_wuji2_sample.py`，用 `.viz-env`、`MUJOCO_GL=egl PYTHONPATH=.` 在根目录运行即可生成 `output/wuji2_single_sample/result.json` 和 `comparison.png`。固定 `14_Tripod` 源文件索引 1，应用 `scene_scale`，拟合三阶段 27 维 Wuji2 姿态。抓取阶段五指误差为 0.37/3.48/1.84/2.62/1.54 mm，但 Wuji2 抓取姿态最大手物穿透 15.63 mm；接触力局部细化候选被拒绝，六方向评估未通过。因此**尚无 Wuji2 碰撞合格或稳定抓取**。逐阶段、逐指与候选细节见[迁移设计](docs/design/wuji2-retargeting.md)；下文早期“尚未运行”表述是本补充之前的交接状态。

新 agent 可先读本文，再读[Wuji2 迁移设计](docs/design/wuji2-retargeting.md)；实现细节按文中代码路径查阅。三方向图鉴已有独立[设计说明](docs/design/shadow-taxonomy-preview.md)，无需从旧对话重建。

## 当前目标和结论

用户希望先看到 Shadow Hand 与物体的抓取交互，优先 3D，可用 2D 兜底；随后计划把手换成 Wuji Hand 2 Beta 2 并重新优化抓取。

Shadow 图鉴首屏显示真实场景的 2D PNG，点击“切换到 3D”才载入交互模型；三个阶段分别有对应图片和 GLB。当前仅覆盖 `1_Large_Diameter`、`14_Tripod`、`24_Tip_Pinch`，每类三个样本，总计 9 条记录、27 个 GLB、27 张 PNG。用户确认静态图可见，但浏览器报告“无法创建 WebGL 画面”。因此增加预渲染多视角：WebGL 不可用时可以拖动或点击箭头切换角度。用户对三方向版本给予正面反馈，尚未记录逐项用户侧验收；此模式不是实时 3D。

2026-09-29 继续按用户要求将多视角模式扩展为三组左右箭头：水平环绕、上下俯仰、画面滚转。水平与俯仰来自 12 × 5 个离线相机视角，滚转在浏览器中旋转画面。27 个阶段共 1620 个视角引用均已导出并检查；用户给出正面反馈，逐项用户侧验收尚无记录。

## 文件和运行

- `tools/export_taxonomy_preview.py`：读取可信 Shadow NPY，使用 MuJoCo 和 Trimesh 导出 GLB、PNG、环绕视角 WebP、JSON。
- `tools/taxonomy_preview.html`、`tools/taxonomy_preview.js`：浏览器界面与交互代码。
- `tools/vendor/model-viewer.min.js`：本地 3D 组件。
- `output/taxonomy_preview`：当前生成产物，已被 Git 忽略。重新运行导出器会同步网页副本和三阶段资产。
- `tutorials/visualize_taxonomy.md`：运行与远程访问命令。
- `docs/design/shadow-taxonomy-preview.md`：图鉴模式、三方向视角、资产数据流和验证边界。
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
- 2026-09-29 增加 297 张 WebP 形成 27 组各 12 个环绕视角；禁用 WebGL 的 Chrome 中验证模式自动切换、箭头换角度、阶段切换和图片加载；正常 Chrome 中再次验证实时 3D 加载。
- 同日扩展到 12 × 5 相机视角并加入滚转控制；禁用 WebGL 的 Chrome 中逐组点三组箭头，验证图片和角度更新、阶段切换保留视角，并目视检查控件布局；正常 Chrome 中再次验证实时 3D。
- 运行了 `node --check`、Python `compileall`、`git diff --check`，并核对模板与输出副本。

自动检查仅覆盖本机浏览器。用户已在自己的访问路径确认静态画面可见；不能据此推断 3D 在用户浏览器中可用。

## 下一位 agent：Wuji2 单样本迁移

**当前优先目标**：用 Shadow 手型与物体接触关系初始化 Wuji2，做出一个可复现的 `pregrasp/grasp/squeeze` 对照样本；然后逐步加入接触优化和动力学评估。详细设计与分层验收见[Wuji2 迁移设计](docs/design/wuji2-retargeting.md)。

- Wuji2 右手 MJCF：`assets/wuji-description/hand2/hand2_beta2/body/mjcf/right.xml`。本地 MuJoCo 已确认独立模型有 20 个关节、20 个执行器、五个指尖 site；接入 Dexonomy 自由手腕后姿态为 27 维，并能和一个真实物体场景编译进 `MuJoCo_OptEnv`。这还不是 Wuji2 抓取实验。
- Shadow 成功抓取数据：`assets/object/Dexonomy_GRASP_shadow/succ_collect`；抽查文件的三阶段姿态为 29 维，只有 `scene_path`、`scene_scale` 等基础字段，没有优化器所需的接触身体/接触点字段。不能简单改 XML 或复制关节数组；必须先建立 Shadow 指尖/接触目标到 Wuji2 关节、碰撞身体的映射。
- 建议首个样本：`14_Tripod/0004e882b42844eda8b4ab7379cb04c8/floating/scale005.npy` 的索引 1。按 `scene_scale` 重建后，Shadow 的 `grasp` 姿态有 5 个手物接触、0 个自接触，最小手物接触距离约 0.55 mm；仍需复查三阶段穿透、目标接触及抓取质量。
- `dexonomy/op/gen_init.py` 依赖手型专属模板，不能直接复用 Shadow 模板；`dexonomy/op/gen_grasp.py` 和 `gen_grasp_admm.py` 要求 `hand_cbody`、`hand_cpn_w`、`obj_cpn_w` 等输入。先做独立的 27 维 Wuji2 逆运动学与接触目标构建，再接优化器。
- 旧文档曾引用 `reproduction/retarget_shadow_wuji2_demo.py` 和指尖误差，但该脚本**当前不在工作区**，不可把其数值作为本次可复现基线。

**建议顺序**：固定源样本和场景尺度 → 提取 Shadow 指尖/接触目标 → 拟合 Wuji2 三阶段 27 维姿态 → 把接触投影到 Wuji2 碰撞网格并局部优化 → MuJoCo 评估 → 导出 Shadow/Wuji2 对照。首个交付应保留源路径与索引、模型版本、逐指误差、限位和穿透统计、接触身体、物体位移及评估结果。运动学拟合只能称为姿态迁移，不能称为成功抓取。

图鉴继续工作时阅读[图鉴设计](docs/design/shadow-taxonomy-preview.md)、[纪传体当前能力](docs/agent/simulation_visualization/evolution/grasp-taxonomy-visualization.md)和[2026-09-29 编年记录](docs/agent/simulation_visualization/chronicles/2026-09-29-three-axis-controls.md)。当前 `output/taxonomy_preview` 是 Git 忽略的生成目录；重建命令见上文。完整抓取生成、Wuji2 接触优化和动力学实验尚未完成。提交状态以当前 Git 记录为准。
