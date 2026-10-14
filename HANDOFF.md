# Dexonomy 项目交接（更新于 2026-10-14）

## 当前顺序：先提交第三版，再开发旋转查看

用户确认第三版整体效果，并要求按旧版 roll/pitch/yaw 控件增加旋转查看，随后明确先写 Markdown 并 commit，再开发。已完成的第三版与后续范围记录在[版本快照及旋转计划](docs/design/shadow-wuji-thumb-v3-rotation-plan.md)。当前第三版仍是固定视角页面；旋转功能只完成旧实现阅读，尚未开发。下一步在当前版本提交后按计划实施独立的离线多视角导出与同步控件，继续使用本次 Wuji 一代姿态。

## 最新完成：拇指第三版与非反折可行域

用户授权按实际方向、相邻指节弯曲和反折约束实施。第三版从第二版选用姿态继续，末端两关节按真实连杆夹角限制非反折及组合弯曲，根部对掌关节仍保持原范围；原始手模型、第一/二版和首轮输出只读保留。实际指段方向与弯曲目标继续参考 Shadow，负弯曲目标的可行域投影另行记录。这是机器人几何迁移约定，不是人体活动范围认证。

首轮 172 次、失败子集一次修复 60 次，恢复 39 个首轮失败。最终 59 资产 / 236 条目 / 172 来源：136 个第三版通过、15 个合格第二版保留、21 个待修正，对应 205 / 31 个覆盖条目通过/待修正。全部选用姿态末端无反折，最大有向夹角约 180°、最大组合弯曲约 120.55°；全部资产至少一个通过候选，53 个资产至少三个。相比第二版有两个旧几何候选（电池大直径握法、肥皂三指棱柱握法）因动作误差转为待修正，没有放宽旧门槛。

最终审查入口 `output/shadow_wuji_v3/all_matched_thumb_v3_final/index.html`，离线包 `review_v3_bundle.zip`；支持逐阶段夹角对照及首轮/修复试验。64 项回归、全部来源/矩阵/限位/实际几何角、两份试验收据及 599 张图片核对通过。Chromium 检查 59 个资产、236 张卡片、两模式 472 次图片解码，过滤/放大/Esc/移动端均通过。下一步用户统一审查手型及剩余 21 例；仍没有动力学成功或原 Bench2Dex 完整任务验证。

文档：[第三版记录](docs/design/shadow-wuji-thumb-v3.md)、[教程](tutorials/shadow_wuji_thumb_v3.md)。入口 `tools/batch_shadow_thumb_v3.py`、`tools/finalize_shadow_thumb_v3.py`、`tools/check_shadow_thumb_v3.py`、`tools/review_shadow_thumb_v3.py`。

## 复核记录：第二版拇指反折约束缺失

用户指出拇指超过伸直 180° 的视觉反折。只读审计第二版最终 172 例三阶段：没有机械限位违例，但抓取 j3/j4 有符号几何转角 <−5° 分别有 57/19 例，−5° 只是诊断阈值。笔 Stick 样本末端按伸直为 180° 的有向夹角约 207.45°；已采用第二版的网球样本也仍有 j3 反向弯曲。第二版最小二乘没有自然屈伸/关节组合硬约束，静态通过不能视为自然性通过。新增 `tools/audit_shadow_thumb_angles.py` 并全批运行，逐姿态校验几何转角变化与 hinge q 一致。记录在[反折与优化函数复核](docs/design/shadow-wuji-thumb-angle-audit.md)，数值在 `output/shadow_wuji_v2/thumb_angle_audit_2026-10-14.json`。该只读复核本身未改模型或旧输出；后续已据此实施第三版，见上。

## 已完成：拇指第二版与第一版对照

用户授权自行权衡继续优化/重新优化，并实施拇指第二版。代表样本显示两种初始化结果接近，决定以第一版优化姿态继续。新增掌心相对位置、对掌、指段/参考指腹朝向、局部接触区域及软限位余量；先拇指后全手有限修正。主配置未通过保护检查时，最多试一次保守配置，仍不适合则保留第一版。旧模型、硬限位、来源/尺度与质量门槛保持，第一版结果只读。

批次目录 `output/shadow_wuji_v2/all_matched_thumb_v2/`，59 个资产 / 236 个覆盖条目 / 172 个独立来源全部完成；132 例采用第二版，40 例保留第一版，实际配置尝试 222 次。153 个静态候选、19 个仍需调整，原通过状态零退化。拇指综合误差均值下降约 11.6%，抓取阶段贴近限位的案例由 122 降到 37；参考指腹角度改善较小，不能称作完全自然。对照入口 `index.html` 表示 Shadow / 第一版 / 本次选用，离线包 `review_v2_bundle.zip` 保留未采用提案。50 项回归、全批成对身份/数值校验、684 张图片及全部 59 个资产的浏览器检查通过。原手模型及第一版代码未改，原输出未覆盖。

文档：[第二版记录](docs/design/shadow-wuji-thumb-v2.md)、[教程](tutorials/shadow_wuji_thumb_v2.md)。当前改善为静态姿态代理指标，指腹参考并非硬件标定，动力学仍未验证。

## 已完成：全部当前匹配资产，每资产四种握法静态迁移

用户要求暂不补缺口，先完成所有已有来源的 Shadow→Wuji 一代迁移并统一检查，明确每资产 3–4 种握法。本轮已完成 59 个资产、每个四种、236 个覆盖条目、172 个独立来源优化，使用原始 Wuji 一代右手。151 个独立来源通过静态筛选、21 个需调整；按目标覆盖计为 205 / 31。所有来源均有三阶段姿态和双模式图，零输入/执行/渲染错误。44 项回归、整批来源/输出/限位校验与全部 59 个资产的浏览器图片检查通过。

当前目录 `output/shadow_wuji_v1/all_matched_batch_v1/`，计划/结果为 `plan.json` / `summary.json`，查看入口为 `index.html`，离线包为 `review_bundle.zip`。每例有双模式图片、三阶段 NPZ、指标与校验收据。详见[本轮记录](docs/design/shadow-wuji-matched-assets-batch-v1.md)与[教程](tutorials/shadow_wuji_matched_batch.md)。这批结果仍使用对应 Dexonomy 来源几何/尺度，尚无本批原 Bench2Dex USD 上的真实控制验证。18 个缺口延期，不启动补充。下一步先与用户统一检查已有结果，不自动扩大资产范围。

## 当前迁移方向：Shadow 到 Wuji 一代

用户先建议 Allegro 来源，随后明确改为五指 Shadow 优先，目标是尽量保留手型与阶段动作，再联合优化接触与稳定性。已实现[Bench2Dex 相关资产筛选与首批迁移](docs/design/bench2dex-dexonomy-asset-transfer-v1.md)：17 个同 YCB 身份线索、33 个类别候选、27 个未匹配目录；8 个目标条目提取为固定开发清单并完成三阶段静态迁移，6 个来源物体/72 个资源文件另行校验提取。最大静态穿透约 0.53–0.59 mm，6 个数值求解到达迭代上限，全部只标为静态候选。本路线的物理成功样本尚未实现，尚未把姿态换到 Bench2Dex 原始 USD 上执行。

复现用 `benchmarks/shadow_wuji_bench2dex_v1.json`，工具为 `tools/match_bench2dex_dexonomy.py`、`tools/retarget_shadow_wuji_v1.py`、`tools/stage_shadow_transfer_assets.py`。实际输出在 `output/shadow_wuji_v1/asset_selection_v2/`、`selected_assets/`、`retarget_selected_v2/`；操作见[教程](tutorials/shadow_wuji_asset_transfer.md)。目标继续使用 Bench2Dex 原始 Wuji 一代，仅做 MuJoCo。Allegro 方案留作候选对照，旧 Wuji2 迁移结果不作为本次完成证据。

最新资产补查扩展至 59/77 个目录有候选（17 同 YCB 身份线索 + 42 类别/家族），18 个目录仍有缺口，厨房组合另有部分组件来源。v3 清单在 `output/shadow_wuji_v1/asset_selection_v3/`，详见[剩余缺口与证据层级](docs/design/bench2dex-dexonomy-asset-gaps.md)。首批八条迁移来源不变，尚未新增动态验证；玩具冰箱、整钢琴与其他拼图模型不代表功能部件或任务动作已适配。

## 最新：MuJoCo 四球双侧局部闭环

用户明确本次只做 MuJoCo，Isaac 由独立 RTX 机器承接。已实现碰撞面抓取候选、开手/收紧优化、桌面与接近检查、实际闭手/抬起/保持/六方向扰动、逐步轨迹、固定预算续跑、真实指令重放与相对路径结果包。20 次声明的开发覆盖尝试取得 8 个通过样本，覆盖四种目标球的左右手全部 8 个单元；全部通过样本的命令物理重放误差为 0。不是总体成功率或完整任务成绩。

当前权威事实：[MuJoCo 第一版](docs/design/wuji-mujoco-grasp-v1.md)、[增量开发记录](docs/design/wuji-bench2dex-v1-progress.md)、[操作教程](tutorials/bench2dex_mujoco.md)。M0 跨模拟器、机械臂可达性、双手完整任务与策略训练仍待完成。下方“尚无新增抓取”是先前阶段的交接状态，以上述最新记录为准。

用户质疑抬升图后进行了[实际接触力复核](docs/design/wuji-mujoco-lift-audit.md)：原图样本确实由三指接触支撑，保持时向上力等于球重且无桌面支撑。全过程约 172 mm 上升包含闭手时约 103 mm，单独 lift 约 69 mm。实际接触包含指节，不能继承请求的 Precision Sphere 类别为验收标签；后续应完善执行后接触组检查和闭手路径质量。已有带高度/力文字的 GIF、MP4 和透明承力点近景；总计 35 项检查通过。

## 2026-10-13 第一版实现与当前进入条件

已实现 `tools/bench2dex.py` 与 `dexonomy/integrations/bench2dex/`：官方固定资源校验、资产/模型检查、左右手转换与 URDF/MuJoCo 固定姿态对照、HDF5 校验、ACT 独立副本准备、运行时 FK 文件对照和姿态预览。

任务 27 所需原始资产与一条原演示/对应 RGB 重放已选择性下载到仓库外，204 个文件官方哈希校验通过；左右手四组姿态 FK 对照通过。原演示准备后 907 帧可用于训练，Bench2Dex 原 ACT Dataset/归一化函数实际读取通过。运行证据、输出路径与命令见[开发记录](docs/design/wuji-bench2dex-v1-progress.md)和[教程](tutorials/bench2dex_v1.md)。

M0 仍未验收：缺少 Isaac Lab / Isaac Sim 运行时对照，原始 USD 独立解析警告和碰撞/惯性/驱动差异待核实。新增抓取、完整任务扩增、ACT 策略训练及 A/B/C 评测尚未完成。下节的“资产缺失、功能尚未实现”是需求定义时的状态，以上述开发记录为当前状态。

## 2026年10月13日新增实现目标

后续目标改为 Bench2Dex 实际评测的 Wuji 一代，先做任务 27 球类装箱，再做任务 21 调味品装箱。用户要求先写需求文档，再在 Dexonomy 中实现；当前交付为[Wuji 一代数据集与 Bench2Dex 任务迁移需求](docs/design/wuji-bench2dex-requirements.md)，新功能尚未实现。

第一步为 M0 模型与资产检查。Bench2Dex 默认机器人与物体资产、原演示目录尚缺；本机旧 `wujihand-v1.0.2` 模型与 Bench2Dex 描述的限位存在差异，不能直接视为已确认的评测模型。下文 Wuji2 内容是保留的历史实现与实验记录，不作为新目标模型或新实验结果。

## 两个独立的 Wuji2 结果版本

用户要求将“与物体交互的优化”和“仅手型的优化”分开展示。现有 `output/wuji2_comparison/` 是前者，新增 `output/wuji2_hand_only_viewer/` 是后者：源手与只按手部动作拟合的 Wuji2 两栏、三阶段、离线可旋转视角和 GLB，不显示物体。复现与同一端口访问两个页面的命令见[操作教程](tutorials/visualize_wuji2_hand_only.md)，解释和限制见[设计文档](docs/design/wuji2-hand-only-viewer.md)。纯手型拟合不是可抓取姿态。

## 手部动作对应补充

新增[独立手部动作对应设计](docs/design/wuji2-hand-action-correspondence.md)：按各手掌心解剖坐标、逐指中性指长归一化，区分形状、相对中性手型的动作、收拢与阶段动作；提供 16 例报告和单独关节拟合。动作拟合把平均动作误差从 0.530 降至 0.083，但抓取阶段世界指尖误差从 1.73 mm 增到 55.45 mm。下一步应联合物体和动作目标，继续约束碰撞与稳定性；单独手部拟合不是成功抓取。

## Wuji2 三阶段对照可视化补充

`tools/export_wuji2_comparison.py` 已为 16 条开发样本生成 `output/wuji2_comparison`：每条三阶段、原手/Wuji2、同物体/纯手型，共 11,520 张 WebP（含 12 水平 × 5 俯仰的离线视角网格）和 192 个 GLB。纯手型按掌心和指根方向对齐，网页同时显示同物体指尖误差和对齐后的指尖距离。无法使用 WebGL 时页面自动进入离线多视角，三排滑条分别控制水平、俯仰和滚转，拖动一格也可同步旋转四格；实时 3D 按钮明确标为不可用。支持 WebGL 的浏览器仍可选择实时 3D。禁用 WebGL 的 Chrome 已验证三个滑条、画面拖动、角度同步和阶段切换。复现与访问见[操作教程](tutorials/visualize_wuji2_comparison.md)，对齐定义和结果限制见[设计说明](docs/design/wuji2-comparison.md)。这仍是运动学对照，16 例六方向评估均未通过。

## 后续 Wuji2 开发样本补充

已建立 [`benchmarks/wuji2_retarget_v1.json`](benchmarks/wuji2_retarget_v1.json) 的 16 条 Shadow/Allegro 样本及 `tools/run_wuji2_benchmark.py` 批量入口。Shadow 覆盖 5 个抓取类别；Allegro 覆盖 DGN、Objaverse 和两种指尖模板，开发/保留按对象隔离。16/16 可运行运动学迁移，但最大手物穿透普遍较大，六方向评估 0/16 通过。放松腕部先验虽降低指尖误差，却未显著降低穿透，因此保留基线参数。实际数字和复现命令见[开发样本文档](docs/design/wuji2-benchmark.md)。下文单例状态描述为扩展前的历史结果。

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
