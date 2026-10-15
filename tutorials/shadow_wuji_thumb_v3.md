# 拇指第三版：方向迁移、非反折约束与检查

使用第二版最终选用结果继续优化，固定原来的资产、来源、尺度和原始 Wuji 一代右手。实现说明和运行记录见[第三版设计文档](../docs/design/shadow-wuji-thumb-v3.md)。原始模型和第一/二版输出不覆盖。

## 单案例

```bash
.viz-env/bin/python tools/refine_shadow_thumb_v3.py \
  --baseline output/shadow_wuji_v2/all_matched_thumb_v2/samples/case_0158__29_Stick \
  --output output/shadow_wuji_v3/pen_new
```

每次指定新目录；`--no-render` 可仅输出姿态和指标。拇指先单独优化，再允许全手与腕部有限调整。

## 同范围批次

```bash
.viz-env/bin/python tools/batch_shadow_thumb_v3.py \
  --baseline output/shadow_wuji_v2/all_matched_thumb_v2 \
  --output output/shadow_wuji_v3/batch_new --prepare-only
.viz-env/bin/python tools/batch_shadow_thumb_v3.py \
  --output output/shadow_wuji_v3/batch_new --resume --workers 4
```

固定 59 个资产、236 个握法覆盖条目、172 个独立来源，最多四个 CPU worker。续跑会检查新配置/代码、第二版结果及第一版模型/来源身份，终态样本只有哈希校验通过才复用。本版每例只有一套配置和明确数值预算，失败保留诊断，不隐式反复重试。

当前整批交付另外对首轮未通过项执行一次已声明的几何修复配置，且单独保存首轮、修复和最终选用。复现此两次预算流程：

```bash
.viz-env/bin/python tools/finalize_shadow_thumb_v3.py prepare-repair
.viz-env/bin/python tools/batch_shadow_thumb_v3.py \
  --output output/shadow_wuji_v3/geometry_repair_trial --resume --workers 4
.viz-env/bin/python tools/finalize_shadow_thumb_v3.py publish
```

上述默认从首轮 `all_matched_thumb_v3/` 建立修复子集，发布到新目录 `all_matched_thumb_v3_final/`；要求父批次已全部完成。发布不会覆盖原结果，每例最多两套配置尝试。最终目录中被尝试修复的样本另含 `primary_trial/` 和 `geometry_repair_trial/`，可比较未采用的结果。

## 验证与查看

```bash
.viz-env/bin/python tools/check_shadow_thumb_v3.py \
  --batch output/shadow_wuji_v3/batch_new
.viz-env/bin/python tools/review_shadow_thumb_v3.py \
  --batch output/shadow_wuji_v3/batch_new
```

打开生成的 `index.html`。默认两列为原 Shadow、最终选用 Wuji，三阶段依次为预抓取、抓取、收紧；展开“显示历史对照（V2）”增加历史 V2 一列。沿用 V2 的结果直接放在最终列，注明来源及动力学未验证，待修正提案仍明确标记。可按资产、状态、结果来源过滤，切换带物体与纯手型，单击画面放大。每条显示最大末端有向夹角、组合弯曲、指段方向与指腹代理误差；原九格图及优化尝试放在“历史文件与优化尝试”内。

## 输出语义

- `kinematic_candidate`：原静态几何检查及新的弯曲/方向检查均通过。仍不代表物理抓取成功或人类自然性已认证。
- `kinematic_rejected`：至少一项检查失败，明确列出原因；不能用于宣称“已修复”。
- `v3`：采用满足新检查的第三版。
- `v2_retained`：第二版自身满足新检查，第三版没有足够收益或破坏检查，保留合格旧版。第二版不合格时不走这个分支。
- `v3_rejected`：新旧都不合格，输出第三版提案供定位问题，状态必须为待修正。

`postures.npz` 包含 `source_qpos`、`wuji_v1_qpos`、`wuji_v2_qpos`、`wuji_v3_feasible_start_qpos`、`wuji_v3_initialized_qpos`、`wuji_v3_proposed_qpos` 和 `wuji_selected_qpos`。旧姿态原样保留；可行初值单独保存，避免把初值投影当作优化改善。

`result.json` 包含模型屈伸符号与几何零位标定、源弯曲及投影目标、各阶段旧/新弯曲与朝向指标、几何检查、最终采用原因。`receipt.json` 保证结果身份，`paired_check.json` 为整批成对检查结果。

## 角度约定

只有拇指末端 joint3/joint4 设置几何非反折可行域，根部对掌关节仍可取原模型允许的负角。相邻连杆方向投影到 hinge 法平面后测量有符号弯曲，伸直为 0°；有向夹角记为 `180° - 弯曲角`。这不是 q 数值本身，也不是人体临床活动范围。

两关节组合弯曲上限参考 Shadow THJ2/THJ1 的正向机械范围，当前不超过 130°；指段和指腹误差不超过 90° 用于排除与来源相反的朝向。来源负弯曲投影到声明的目标可行范围，并完整记录。原方向目标继续保留，因此约束修复后旧的拇指代理评分也可能上升，不能要求所有相互冲突的目标同时改善。
