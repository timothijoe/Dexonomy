# 第三版旋转查看：水平、俯仰与滚转

静态第三版及旋转计划先提交为 `6fc28ee`，随后新增本教程所述查看方式。优化姿态和检查状态沿用第三版，不重新生成抓取。

## 查看

打开 `output/shadow_wuji_v3/all_matched_thumb_v3_final/index.html`，点击顶部“打开可旋转对照”或任一握法下方“旋转查看”。也可直接打开 `rotation/index.html`，无需服务端或 WebGL。

当前总览 `index.html` 也直接显示 Yaw / Pitch / Roll 三组按钮和滑条，同步更新当前显示的握法与三阶段画面。单击画面放大后，放大窗口顶部也有三轴控件；不必先找独立旋转页。总览复用 `rotation/frames/`，因此移动文件时需要保留旋转目录；仅含固定图的 `review_v3_bundle.zip` 会明确提示缺少旋转帧，完整旋转包为 `review_v3_rotatable_bundle.zip`。

选择资产、握法和阶段，默认两列为原 Shadow、最终选用 Wuji。选择“三个阶段”同时显示六格；展开“显示历史对照（V2）”增加中间的历史 V2 列，三阶段时显示九格。最终列会注明沿用 V2 或待修正的情况，验证状态单独显示。可以切换带物体和纯手型；从总览的纯手型模式进入时保持该模式。展开/收起历史对照保留当前资产、握法、阶段、模式和角度，全部可见列同步旋转。

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

只更新查看方式时运行两个 `review_*.py` 即可，不需要重新导出旋转帧。静态总览的脚本嵌入生成 HTML，旋转页的脚本为 `rotation/app.js`；移动离线文件时一起保留原图片和这些页面文件。
