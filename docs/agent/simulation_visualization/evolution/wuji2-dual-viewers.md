# Wuji2 手物与纯手型双版本对照

## 当前能力

Wuji Hand 2 Beta 2 的迁移结果有两个**独立姿态版本**，共用 16 条固定样本（Shadow 8、Allegro 8）和 `pregrasp/grasp/squeeze` 三阶段：

| 版本 | Wuji2 姿态来源 | 页面 | 画面 |
| --- | --- | --- | --- |
| 手物交互 | 物体场景中的世界指尖拟合，并尝试局部接触细化；页面展示原迁移姿态 | `output/wuji2_comparison/` | 原手/Wuji2 与物体，以及原迁移姿态去掉物体的诊断图 |
| 纯手型动作 | 单独拟合 Wuji2 的 20 个手指关节，目标为手部动作、归一化指尖形状和轻度关节先验 | `output/wuji2_hand_only_viewer/` | 原手与独立优化的 Wuji2；没有物体 |

第二个页面不是把第一个页面下排的物体隐藏：Wuji2 手指关节姿态来自另一组优化结果。手部动作对应在 [`benchmarks/hand_action_correspondence_v1.json`](../../../../benchmarks/hand_action_correspondence_v1.json) 单独声明。Shadow 五指一一对应；Allegro 只有拇、食、中、无名指，Wuji2 小指列为未映射。各手自身掌心坐标去除全局位姿，并以各自中性指长归一化指根到指尖向量；详细定义和局限见[手部动作对应设计](../../../design/wuji2-hand-action-correspondence.md)。

两个页面均有样本筛选、三阶段切换、GLB 下载。纯手型页的两手使用同一相机和取景范围；按各自掌心与三根指根的解剖轴对齐，并将抓取阶段的对齐变换保持到前后阶段。页面默认图片，提供 12 水平 × 5 俯仰离线视角，以及水平、俯仰、画面滚转三个滑条；拖动一张图同步切换两张图。无 WebGL 时自动进入离线模式；支持 WebGL 时可手动载入 GLB 并同步相机。滚转是图片平面旋转，不提供新的遮挡信息。

## 生成链路

`tools/analyze_wuji2_hand_action.py` 从固定清单、基线迁移结果和手模型生成逐例动作报告及可选的独立关节拟合；`tools/export_wuji2_hand_only.py` 读取拟合后的三阶段 Wuji2 `qpos`，输出两手 WebP、GLB、JSON 索引和静态网页。原手指尖采用基线结果中保存的视觉网格校准点，Wuji2 使用模型 tip site。导出器校验源文件 SHA-256、手型、样本索引和结果身份。详情、参数与启动顺序见[纯手型操作教程](../../../../tutorials/visualize_wuji2_hand_only.md)。

手物交互页由 `tools/export_wuji2_comparison.py` 生成。两页可在 `output` 根目录的 HTTP 服务下分别访问 `/wuji2_comparison/` 和 `/wuji2_hand_only_viewer/`，顶部互相跳转。手物页另支持 `--index-only`，无需重渲染图片即可刷新页面外壳；纯手型页也支持该参数。生成目录均被 Git 忽略。

## 本机验证与数值

- 纯手型页完整导出 16 例、48 个阶段，每阶段两手：5,760 张 WebP、96 个仅含手部的 GLB，约 148 MB。索引中 6,048 个文件引用均存在；抽样 Wuji2 GLB 重新载入只见 `wuji_hand` 几何。
- 纯手型页在实际本地 HTTP 地址通过禁用 WebGL 的 Chrome headless 加载，默认显示 `sh_tripod_obj`，实时 3D 标为不可用。浏览器实际点击水平、俯仰、滚转控件后，两张图片同时切到 `p03_y01` 对应视角，滚转显示 30°。本轮未对纯手型页的实时 WebGL 模式做浏览器渲染验收。
- 手物交互页的 16 例、11,520 张 WebP、192 个 GLB 已在此前导出并做浏览器检查；本轮重新检查两个页面在同一 HTTP 服务下返回 200，并验证旧 `8767` 页面可跳到新 `8768` 纯手型页。手物页此前的浏览器证据见[三滑条编年记录](../chronicles/2026-09-29-wuji2-three-bar-comparison.md)。
- 16 例平均归一化动作误差由物体版本的 0.530 降至纯手型版本的 0.083；抓取阶段世界指尖均距则从 1.73 mm 升至 55.45 mm。48 个阶段中 42 个求解器报告收敛；960 个关节位置中 76 个距限位小于 0.001 rad。原报告可在忽略的 `output/wuji2_hand_action_v1/` 重建。

## 边界

纯手型优化不使用物体接触、碰撞或动力学目标；页面的“若放回物体”指尖距离只是诊断值，不是抓取评价。手物交互版本的固定基线六方向 MuJoCo 评估 0/16 通过。两版均不能称为稳定抓取。当前手部动作指标只表达归一化指根到指尖几何变化，未覆盖关节协同、指腹朝向、接触力。跨两个目标的联合优化和物理评估仍待开发。

形成过程见[2026-09-29 编年记录](../chronicles/2026-09-29-wuji2-hand-only-version.md)，两版的页面结构分别见[手物交互设计](../../../design/wuji2-comparison.md)与[纯手型设计](../../../design/wuji2-hand-only-viewer.md)。
