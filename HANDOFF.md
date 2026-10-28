# Dexonomy 项目交接（更新于 2026-10-28）

## 本次提交归档（2026-10-28）

用户要求先 commit。本次一并归档此前已完成的已有 44 模型全部握法类别迁移、来源覆盖统计、507 个必需手指接触偏移修复，以及审查界面、验证工具、测试和 Markdown。数值结果仍为 1164 类代表、997 个静态候选、167 个原静态拒绝；接触修复采纳 433 个、74 个保留原版。生成数据、模型、图片、旋转帧和本地环境继续保留在 Git 忽略目录中。本轮只复核并提交，不启动新的优化、动力学或模型扩展；提交后以 Git 记录为准。

## 最新完成：当前类别的必需手指原区域偏移修复

用户要求修正当前批次，已在独立目录 `output/shadow_wuji_contact_repair/current44_2026-10-16/` 完成原 997 个静态候选中的 507 个偏移候选数值修复及独立检查。采纳 433 个、74 个保留原版，44 个模型均有采纳；769 个原偏移参考距离中位数 7.819→0.268 mm，最大修复后 1.992 mm。原 167 个静态拒绝未改变。

入口 `tools/repair_current_shadow_contacts.py`，数值 `progress.json` 已 finished；旋转及浏览器后处理全部完成（`finalize_retry.log` 结尾 `FINALIZED`）。新 182520 帧的哈希/尺寸/网格/姿态绑定、3042 张三列代表帧解码检查通过。浏览器覆盖 1164 类总览/2328 次双模式、74 个代表的 444 个阶段模式组合、全部 507 个提案的 3042 次阶段模式比较，筛选/标签/链接/三轴/放大/历史/移动端均通过、无页面错误；87 项回归通过。

**最新查看入口** `output/shadow_wuji_contact_repair/current44_2026-10-16/review/index.html`，默认原 Shadow / 最终选用两列、直接三轴控件，完整 1164 类；`review/repair_proposals/index.html` 查看全部 507 个修复前后提案，未采纳明确标记。正式选用报告在新 `selected/`，汇总 `results.json` / `results.md`，后处理入口 `tools/review_current_contact_repairs.py`。数值及后处理已结束，源码/Markdown 纳入 2026-10-28 提交归档。

新增引擎按阶段修复、保持预抓取/无偏移阶段不变，保护其他已贴近接触，并在提案上重新做接触审计，禁止新增必需手指诊断标记。原 1164 类数组/报告不覆盖，167 个原静态拒绝不借此改标签；无全批重力验证。记录见[本轮修复](docs/design/shadow-wuji-current-contact-repair.md)。

## 修复前基线：已有 44 模型全部握法类别，不扩展新物体

**全批已完成**：1164 个已有模型×类别组合均有三阶段代表，997 个通过现有静态检查、167 个待修正；其中复用 151 类、新做/重试 1013 类，V3 首轮 736 个合格、277 项一次修复恢复 110。14 个模型全部已有类别静态通过。全部 419040 个旋转帧及收据/姿态哈希检查通过，44 模型/1164 类双模式和 74 个代表条目的 444 个阶段/模式浏览器检查通过，82 项回归通过。

**修复前边界**：997 个静态候选中有 507 类被几何审计标记为必需手指原接触区域偏移；最新修复采纳 433 个，剩余 74 个，见上方新目录。原基线卡片保留橙色标记和接触筛选，不能称为全部接触对应或承重合格。当前无新增全批动力学标签。原总览 `output/shadow_wuji_all_types/current44_2026-10-16/review/index.html`，完整数值 `results.md` / `results.json`。完整记录见[全类别迁移](docs/design/shadow-wuji-current-models-all-grasp-types.md)。数值与后处理进程已结束，旧 V3/模型未覆盖；源码、工具和文档纳入本次归档。

用户将优先级改为当前已有物体尽量覆盖全部握法，已停止推进新 20 模型。固定 44 来源模型、31 类握法、1164 个模型×类别组合；已有 173 个组合有试验，其中 151 个至少有一个合格 V3 可复用，其余 1013 个补做/重试。每类先选一个完整三阶段代表，尚不是穷举 55235 条尺度/姿态记录。

批次为 `output/shadow_wuji_all_types/current44_2026-10-16/`，`coverage_plan.json` 固定全部范围和复用来源，`progress.json` 当前为 `complete`；`run.log` 和各阶段目录记录执行及检查。编排入口 `tools/batch_current_shadow_grasp_types.py --resume --workers 8`；本次使用本机 16 逻辑 CPU / 47 GiB 内存上的有界 8-worker 池，数值引擎/约束/模型不变。复现或续跑前先核对实际进程及日志，避免同目录重复运行；有未完成样本目录时先检查，不盲目覆盖。

审查页 `review/index.html` 由 `tools/review_current_shadow_grasp_types.py` 构建，保留已完成结果并明确标注待处理，不把 V1/V2 初始化算作正式 V3。过程记录见[全部握法类别迁移](docs/design/shadow-wuji-current-models-all-grasp-types.md)。原批次及重力标签不覆盖，新结果未获得动力学成功标签。此前计数工具和统计 Markdown 修改仍在工作区，不要丢弃。

## 最新：边缘再优化与更多模型的独立试验

2026-10-16 补充数量统计：原 41 来源 + 新 3 来源共 44 模型，占本机 5699 个带 Shadow 网格模型约 0.772%。读取全部 6532 个相关 NPY 后，原始完整抓取记录共 55235 条（原批次 50416、新三模型 4819），含 31 类握法、1164 个物体×握法类别组合；当前实际迁移 181 条来源，约占这些记录 0.328%。三阶段不重复算三种握法，Bench2Dex 59/77≈76.6% 是另一覆盖口径。明细见本轮设计记录及 `output/shadow_wuji_v4/coverage_counts_2026-10-16/`，统计工具为 `tools/count_shadow_mapping_coverage.py`。

用户授权继续检查边缘手型并评估更多物体映射。新增内侧→边缘漂移条件找到 15 个来源/25 条观测（10 个原静态候选）。四例多区域修复中肉罐头和杯子通过静态及已有接触保护，盘子/拼图提案不通过并保留原版；两例合格提案与原版的 8 次原力矩悬空重力比较均未通过。来源质量约 0.975 / 3.612 kg，杯子来源直径约 238 mm，后续需校准目标尺度/质量，不能将几何修复等同于承重改善。

本地网格+Shadow 来源 5699 个，原批次仅用了 41 个不同来源，尚有 5658 个资源候选（未全部验证场景/尺度）。已新增罐、瓶、盒三个来源模型，各三种握法，V3 首轮及一次原配置修复后 7/9 通过当前静态门槛；2 条动作偏差待修正，新增模型未做动力学。接触审计仍有原区域漂移诊断，不能视作全链路合格。新增来源不减少 Bench2Dex 18 个原资产缺口。

统一审查入口 `output/shadow_wuji_v4/index.html`；四例修复和新增三模型均有默认两列/历史展开、直接三轴控件的旋转页。77 项回归、新模型数值/角度/资源及 3240 帧检查、两组浏览器检查通过。仅准备下一批 20 模型候选，未启动全量。2026-10-16 按用户要求先完善 Markdown，再将本轮代码、测试和文档独立提交；生成数据继续留在 Git 之外，原 V3/物理标签未覆盖。提交后停止开发，等待后续讨论。详见[本轮记录](docs/design/shadow-wuji-edge-refinement-expansion.md)。

## 最新：最终结果优先显示，历史 V2 按需展开

2026-10-15 用户要求先写 Markdown 再 commit，本轮独立记录见[审查界面调整与提交记录](docs/design/shadow-wuji-review-ui-2026-10-15.md)。将此前完成的默认两列、历史 V2 展开、总览/放大窗口三轴控件、页面检查与教程一起提交；生成数据及离线包继续留在 Git 之外。提交后停止开发，等待后续讨论。

用户确认 V2 作为基线/初值/候选保留，但主界面无需持续显示，已授权修正。原第三版总览及旋转页现默认原 Shadow / 最终 Wuji 两列，三阶段六格；“显示历史对照（V2）”展开后增加中间列，恢复九格，保留当前资产/握法/阶段/模式/角度及同步旋转。最终沿用 V2 时注明来源与当前静态约束通过，待修正提案、动力学未验证状态仍明确显示。原九格图归入历史文件，姿态与检查结果未改。两份离线包及教程同步更新。

用户随后反馈找不到 Roll / Pitch / Yaw，复查是总览/放大窗口原先只有固定图、三轴操作放在独立页。现总览工具栏及放大窗口直接增加三轴按钮/滑条，复用原旋转帧同步更新三阶段；只含固定图的离线包明确提示需要完整旋转包。

总览 Chromium 覆盖 59 资产、236 条目、472 次双模式加载；旋转页禁用 WebGL 覆盖 236 条目、1416 个阶段/模式组合。默认列、历史开合、来源与验证标注、放大/Esc、筛选、三轴/拖动/重置、异步及移动端检查通过，无页面错误。记录见[可视化开发记录](docs/design/shadow-wuji-thumb-v3-rotation.md)。本次仅修正显示，不扩大优化或动力学试验范围。

## 最新：接触区域审计、代表修复与悬空承重结论

用户要求找到原手触边而目标偏离的样本，随后授权继续测试/优化再给结论。已完成[接触与重力复核](docs/design/shadow-wuji-contact-gravity-audit.md)：172 个来源中，12 个锐边代理未保留候选（5 个原静态通过）、46 个指段替换候选（41 个原静态通过）。类型重叠且属诊断标记，不自动改写原状态。输出页 `output/shadow_wuji_v3/contact_region_audit_2026-10-14/index.html` 有筛选、CSV、原/修复对照及旋转链接。

三个独立提案恢复杯子拇指、碗无名指及杯子掌心的原表面参考位置，收紧偏离从 10.30 / 10.52 / 8.83 mm 到 0.12 / 0.23 / 0.16 mm，并通过原静态几何及拇指策略；未覆盖原 V3。当前静态模型核对为 Nu=0、condim=1、重力禁用，因此另建开启重力、自由物体、固定腕、20 个驱动的诊断模型。采用原 URDF 力矩约 0.147–0.649 Nm、PD 20/0.2，摩擦 0.5/1.0、压力 0/0.025 rad，共 24 次原/修复比较，没有使用 800 Nm 覆盖。

两种杯子在这些质量/驱动/接触设置下均掉落；碗仅摩擦 1.0 满足此次 1.2 s 悬空保持门槛，两版/两压力合计 4/24 次条件通过。碗在摩擦 0.5、无额外压力时，修复减少位移 5.98→3.13 mm、转动 17.27→11.48°，仍未通过 10° 门槛。当前质量是 DGN 密度/凸分解估计，不是确认的真实参数。

72 项回归通过，自由落体负对照、初始 FK 一致、碗通过控制重放零误差及实际承重接触合力约等于重量均复核。结论是：接触区域约束遗漏可以修复，但位置修复不保证承重；后续还需受限力/力矩平衡、参数口径与动力学筛选。本次没有桌面闭手/抬升/扰动验证，也没有把诊断结果写回原 172 例的 `physical_passed`。本轮按用户要求将审计、修复、重力诊断代码、测试及文档独立提交；生成结果仍保留在忽略的 `output/` 目录。记录并提交后停止开发，等待后续讨论。原静态/旋转基线提交为 `6fc28ee` / `92cdd31`。

## 当前状态：旋转完成，记录重力验证边界并提交

用户确认第三版整体效果，并要求按旧版 roll/pitch/yaw 控件增加旋转查看，随后明确先写 Markdown 并 commit，再开发。已按顺序提交静态版本及计划为 `6fc28ee`，提交时工作区干净，再实施后续旋转。快照见[版本计划](docs/design/shadow-wuji-thumb-v3-rotation-plan.md)，实际完成记录见[旋转开发记录](docs/design/shadow-wuji-thumb-v3-rotation.md)。本轮按用户要求，将旋转实现、教程、测试和重力验证边界整理为后续独立提交；完成后停止开发，等待讨论。

重力边界已复核并记入[第三版记录](docs/design/shadow-wuji-thumb-v3.md)：本批 172 个迁移来源尚未执行开启重力的闭手、抬升、保持或扰动。当前用 `MuJoCo_VisEnv` / `mj_fwdPosition` 作静态运动学，环境默认禁用重力，`physical_passed` / `full_task_passed` 均为 null。此前四球双侧 8 个动力学通过样本属于独立批次，不能覆盖这些迁移姿态。本轮只记录与提交，不启动新的动力学实验。

旋转已完整覆盖原 172 个来源 / 236 个条目：61,920 张三版本比较帧，12 水平 × 5 俯仰，Roll 每 30° 一档，全部比较格同步。原总览顶部及逐握法新增入口，直接页面为 `output/shadow_wuji_v3/all_matched_thumb_v3_final/rotation/index.html`；静态九格及姿态数组未改。全部图片 SHA/尺寸、12,384 帧三格解码、来源姿态 SHA 核查通过。禁用 WebGL 实测全部条目的 1416 个阶段/模式组合，控件/拖动/循环/边界/异步加载/移动端均通过，66 项回归通过。入口为 `tools/export_shadow_thumb_v3_rotation.py` / `tools/review_shadow_thumb_v3_rotation.py`，使用 MuJoCo 预渲染及 Canvas 2D，仍无动力学成功标签。

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
