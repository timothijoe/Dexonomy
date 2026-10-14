# 第三版旋转查看：水平、俯仰与滚转

静态第三版及旋转计划先提交为 `6fc28ee`，随后新增本教程所述查看方式。优化姿态和检查状态沿用第三版，不重新生成抓取。

## 查看

打开 `output/shadow_wuji_v3/all_matched_thumb_v3_final/index.html`，点击顶部“打开可旋转对照”或任一握法下方“旋转查看”。也可直接打开 `rotation/index.html`，无需服务端或 WebGL。

选择资产、握法和阶段，三格分别为 Shadow 来源、第二版最终选用和本次最终选用。选择“三个阶段”同时显示九格。最后一格会注明第三版待修正或保留第二版的情况。可以切换带物体和纯手型；从总览的纯手型模式进入时保持该模式。

- 水平环绕：12 档，每次 30°，左右按钮循环切换。
- 上下俯仰：−65°、−45°、−25°、−5°、15° 五档，到边界停止。
- 画面滚转：12 档，每次 30°，顺/逆时针按钮循环切换；只旋转模型画面，标题保持正常。
- 拖动画面同步改变全部比较格的水平/俯仰；“重置视角”恢复 135° 水平、−25° 俯仰和 0° 滚转，保持资产、阶段及模式。

水平和俯仰是实际渲染的相机视角，滚转是二维画面旋转。纯手型使用原尺寸和逐阶段掌心对齐。已生成旋转帧不代表实际控制已经握住；通过/待修正状态仍以静态第三版报告为准。

## 重新导出

代表样本先使用新目录：

```bash
.viz-env/bin/python tools/export_shadow_thumb_v3_rotation.py \
  --ids case_0077__13_Precision_Sphere \
  --output output/shadow_wuji_v3/rotation_new --workers 1
.viz-env/bin/python tools/review_shadow_thumb_v3_rotation.py \
  --output output/shadow_wuji_v3/rotation_new
```

不传 `--ids` 则处理完整 172 个来源。默认每格 480×360、WebP 质量 76；每例三阶段×两模式×五俯仰×十二水平，共 360 张横向三版本比较帧。`--prepare-only` 固定计划，`--resume` 校验来源姿态、代码及已完成图片后续跑；已有不完整目录不隐式覆盖。

默认全批目录在第三版最终目录的 `rotation/` 下，完成后刷新旋转页及总览入口：

```bash
.viz-env/bin/python tools/review_shadow_thumb_v3_rotation.py
.viz-env/bin/python tools/review_shadow_thumb_v3.py
.viz-env/bin/python tools/check_shadow_thumb_v3_rotation.py
.viz-env/bin/python tools/check_shadow_thumb_v3_rotation_browser.py
```

导出器/查看器不修改第三版 NPZ、原模型或已有九格图。`rotation/plan.json` 固定输入和相机网格，`summary.json` 记录完成范围，逐例 `receipt.json` 保存全部帧哈希；`export_check.json` 核查完整图片及姿态身份，`browser_check.json` 记录禁用 WebGL 后的控件与导航验证。
