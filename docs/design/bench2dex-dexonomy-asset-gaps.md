# Bench2Dex 与 Dexonomy 资产候选覆盖和剩余缺口

2026-10-15 状态说明：下文“首批八条”属于当时阶段。既有同范围批次已完成 59 个目标目录 / 172 个来源的静态迁移，实际共享 41 个不同来源几何。另已运行三个新 Dexonomy 来源模型、每模型三种握法的独立试验，7/9 通过当前静态门槛；这不代表补齐 Bench2Dex 原网格或减少下述 18 个缺口。最新资源核对与限制见[边缘再优化与扩展记录](shadow-wuji-edge-refinement-expansion.md)。

日期：2026-10-13。触发：用户询问大多数 Bench2Dex 相关物体是否已有，以及还有哪些没有。范围为 26 正式任务引用的 77 个资产目录，不是全部 297 个编号资源目录或干扰物池。

## 最新覆盖

补查第一轮未匹配的 27 项后，确认其中 9 项已有本地 DGN 网格及 Shadow 来源，只是初始规则未覆盖。已扩展类别配置并实际生成 `output/shadow_wuji_v1/asset_selection_v3/matches.json` / `matches.md`，当前为：

| 层级 | 数量 | 含义 |
| --- | ---: | --- |
| 同 YCB 编号与完整名称 | 17 | 同身份线索，未确认处理后的网格等价 |
| 同名类别 | 22 | 类别候选，尚未验证几何和功能区域 |
| 相近几何家族 | 20 | 候选初始化来源，不是同一资产证明 |
| 当前仍有缺口 | 18 | 其中厨房组合已有部分组件类别，其他尚未找到合适本地候选 |

因此 59/77，约 76.6%，有同物体身份线索或相关类别来源。这个比例只描述资产候选覆盖，不是迁移成功率。特别是玩具冰箱、整钢琴模型和其他拼图模型只能表示类别/外形候选，不能代替真实把手、按键、关节与装配片数据。

新增九项：键盘、鼠标、冰箱模型、垃圾桶、电钻、面包篮、香皂、钢琴模型、拼图模型。逐项来源示例：

| Bench2Dex | 本地 Dexonomy 示例 | Shadow 类别目录数 | 限制 |
| --- | --- | ---: | --- |
| 098_keyboard | mujoco_Razer_BlackWidow_Stealth_2014_Keyboard_07VFzIVabgh | 30 | 整物抓取不等于按键 |
| 105_mouse | mujoco_Razer_Abyssus_Ambidextrous_Gaming_Mouse | 31 | 动作/功能接触待查 |
| 111_refrigerator | mujoco_3D_Dollhouse_Refrigerator | 28 | 微缩模型，门关节和把手动作未确认 |
| 122_trashcan | mujoco_Hefty_Waste_Basket_Decorative_Bronze_85_liter | 26 | 桶形候选，非同模型 |
| 147_drill | ddg_gd_drill_poisson_000 | 31 | 工具握持区域待查 |
| 183_breadbasket | mujoco_Squirt_Strain_Fruit_Basket | 25 | 篮形候选，非同模型 |
| 209_soap | sem_SoapBar_351dec75ac0619b1827473663798726a | 28 | 香皂类别，非 soap dish |
| 325_digital_piano | sem_Piano_14755c2ee8e693aba508f621166382b0 | 31 | 整体网格不包含可用弹奏动作证明 |
| 326_jigsaw_puzzle | mujoco_Melissa_Doug_Chunky_Puzzle_Vehicles | 27 | 其他玩具拼图，未匹配真实装配片几何 |

原 v2 匹配结果及首批八条迁移输出保留。已验证 v3 的首批八条源文件 SHA、索引与场景倍率均与 v2 相同；此次补查没有重新运行或扩大姿态/动力学验证。当前迁移结果仍是八条静态开发候选。

## 18 项剩余缺口

| 分类 | Bench2Dex 资产 |
| --- | --- |
| 餐具/工具，4 项 | 030_fork 叉子；031_spoon 勺子；033_spatula 锅铲；042_adjustable_wrench 活动扳手 |
| 设备/支撑，6 项 | 094_faucet 水龙头；104_microwave 微波炉；121_toilet 马桶；201_screen 显示器；332_gas_stove 燃气灶；333_portable_stove 便携炉 |
| 食品，4 项 | 127_french-fries 薯条；128_hamburg 汉堡；163_baguette 法棍；182_bread 面包 |
| 其他，3 项 | 143_pet-collar 宠物项圈；341_banana_peel 香蕉皮；349_paper_low 平纸张 |
| 组合资产，1 项 | 330_kitchen_pack，含碗、汤勺和锅，需按组件继续匹配 |

330_kitchen_pack 的碗已有 DGN bowl 类别；锅可用 `ddg_gd_saucepan_poisson_000` 或 `ddg_kit_HotPot` 作类别候选，分别有 28 / 27 个 Shadow 类别目录；其汤勺仍未找到合适来源。因此不能把组合资产简单视作全部没有，也不能因有锅碗就将整个组合标为已覆盖。

补查拒绝几个误匹配：`Spoon_Rest` 是勺托，不是勺子；`ToiletPaper` 是卫生纸，不是马桶；`HamburgerSauce` 是酱料，不是汉堡；`Soap_Dish` 是皂盒，不是香皂；纸袋和游戏盒不能充当平纸张。当前缺口只基于本地资源和可核查名称线索，不证明完整 Objaverse 或其他上游资源不存在合适对象。

## 三种不同的“有”

1. Dexonomy 中找到相关模型及来源抓取：当前 59 个目录有候选，厨房组合另有部分组件。
2. Bench2Dex 原始资产已恢复到本机：当前任务清单中仍为 8 个目录，不能将候选覆盖数当作本机已下载的原模型数。
3. Wuji 迁移或实际执行已验证：本路线仍只有首批 8 条三阶段静态候选，尚无这些新候选的原 Bench2Dex USD 抬升/保持执行证据。

优先推进尺寸接近且来源明确的网球，随后扩展水果、球和常见瓶罐；特殊工具、食品或功能部件的缺口再单独补模板或恢复资产。设备任务需按把手、按键与约束运动建数据，不能整机套用抬升抓取。
