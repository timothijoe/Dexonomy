# 拇指第二版：从第一版继续优化与逐项比较

固定来源沿用第一版 59 个资产、每个四种握法、172 个独立案例，目标仍是原始 Wuji 一代右手。新约束、开发比较和最终结果见[第二版记录](../docs/design/shadow-wuji-thumb-v2.md)。

单案例开发入口：

```bash
.viz-env/bin/python tools/refine_shadow_thumb_v2.py \
  --baseline output/shadow_wuji_v1/all_matched_batch_v1/samples/case_0077__13_Precision_Sphere \
  --output output/shadow_wuji_v2/tennis_new
```

该入口运行指定配置的一次提案，输出第一版、初始化、第二版提案及最终选用姿态。是否替换由原静态判据与拇指改善检查决定。它不覆盖第一版，也不执行真实抓取。

批量先固定输入：

```bash
.viz-env/bin/python tools/batch_shadow_thumb_v2.py \
  --baseline output/shadow_wuji_v1/all_matched_batch_v1 \
  --output output/shadow_wuji_v2/batch_new --prepare-only
.viz-env/bin/python tools/batch_shadow_thumb_v2.py \
  --output output/shadow_wuji_v2/batch_new --resume --workers 4
```

`--resume` 校验第一版模型/来源、第一版结果收据、第二版主/保守配置及代码身份。当前配置主要从第一版优化姿态继续；只有主提案未采用时，才最多追加一次保守配置尝试。试验与未采用提案都保留，不无限重试、不改限位。

建立统一比较页：

```bash
.viz-env/bin/python tools/review_shadow_thumb_v2.py \
  --batch output/shadow_wuji_v2/batch_new
```

打开 `index.html`，可按资产、状态、采用第二版/保留第一版过滤，切换带物体与纯手型，单击图片放大。九格图顶行为 Shadow 来源，中行为第一版优化结果，底行为本次选用结果；底行保留第一版的情况会明确标注。未采用提案有单独链接。

输出文件：

- `plan.json` / `summary.json`：固定来源、输入身份和逐案例终态。
- `samples/<case_id>/postures.npz`：`source_qpos`、`wuji_v1_qpos`、`wuji_v2_initialized_qpos`、`wuji_v2_proposed_qpos`、`wuji_selected_qpos`。
- `result.json`：掌心相对位置、对掌、指段方向、参考指腹朝向，以及选择原因/原几何判据。
- `primary_trial/` / `fallback_trial/`：仅在追加保守尝试时保存，两份提案分开。
- `receipt.json`：结果文件身份，支持校验续跑。

指腹参考是依据 Shadow 人工标注与 Wuji 碰撞几何建立的代理，未完成硬件接触区标定。评分改善是静态几何指标改善，不等于人工确认自然、真实握持稳定或原 Bench2Dex 任务通过。
