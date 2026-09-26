# 最短运行流程

以下步骤用于环境 smoke test，不用于大规模生成。开始前完成[环境安装](environment_setup.md)和[数据安装](data_setup.md)。

## 1. 转换一个模板

```bash
.venv/bin/dexrun op=tmpl hand=shadow debug_name=1_Large_Diameter n_worker=1
```

预期在 `assets/hand/shadow/init_tmpl` 生成对应 NPY。检查日志中是否有接触点远离网格或身体名称不一致。

## 2. 小规模初始化

```bash
.venv/bin/dexrun op=init hand=shadow exp_name=smoke tmpl_name=1_Large_Diameter 'init_gpu=[0]' n_worker=1 op.object.n_cfg=1 op.object.batch_size=1 op.epoch=1
```

该命令会使用 GPU 0。运行前确认 GPU 可用且没有占用冲突。

## 3. 抓取与评估

```bash
.venv/bin/dexrun op=grasp hand=shadow exp_name=smoke n_worker=1
.venv/bin/dexrun op=eval hand=shadow exp_name=smoke n_worker=1
```

检查 `output/smoke_shadow/grasp_data` 和 `succ_grasp`。目录有文件只说明阶段产生输出；评估成功结果才位于成功目录。

## 4. 导出一个样本

```bash
.venv/bin/dexrun op=v3d hand=shadow exp_name=smoke op.data=succ_grasp op.n_max=1 n_worker=1
```

输出位于实验目录下的 `vis_3d`。当前机器尚未实际完成上述 smoke test，第一次运行时应记录命令、环境和结果。
