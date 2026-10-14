# Dexonomy 操作教程

推荐顺序：

1. [环境安装](environment_setup.md)
2. [数据与模型安装](data_setup.md)
3. [最短运行流程](quickstart.md)
4. [31 类抓取数据可视化](visualize_taxonomy.md)
5. [Wuji2 迁移对照可视化](visualize_wuji2_comparison.md)
6. [Wuji2 纯手型动作优化可视化](visualize_wuji2_hand_only.md)
7. [常见问题](troubleshooting.md)

Wuji 一代新增流程见[Bench2Dex 第一版检查与 ACT 数据准备](bench2dex_v1.md)。

最新已运行的单手局部抓取生成与验证见[MuJoCo 操作教程](bench2dex_mujoco.md)。

用户选定的 Shadow 来源路线已实现资产筛选与三阶段静态迁移，见[Shadow→Wuji 相关资产迁移教程](shadow_wuji_asset_transfer.md)；这批新候选尚未完成动力学验证。

全部当前匹配资产、每资产 3–4 种握法的批量执行与统一查看，见[全匹配资产批次教程](shadow_wuji_matched_batch.md)。

拇指位置/方向的第二版继续优化、保留机制和逐项对比，见[拇指第二版教程](shadow_wuji_thumb_v2.md)。

拇指实际指节方向、非反折可行域及合格旧解保留，见[拇指第三版教程](shadow_wuji_thumb_v3.md)。

第三版 roll/pitch/yaw 按钮、滑条与离线旋转查看，见[旋转查看教程](shadow_wuji_thumb_v3_rotation.md)。

上游已有的人工标注细节保留在 `getting_started/1_annotation_tutorial.md`，完整生成参数示例保留在 `getting_started/2_running_tutorial.md`。本目录以当前仓库和当前资源布局为准。
