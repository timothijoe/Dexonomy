# 数据与模型安装

## 当前交接包

当前机器的接收目录为：

```text
/data/robotic_data/transfer_data/dexonomy_2026-09-25
```

先校验，任何失败都不要继续解压：

```bash
cd /data/robotic_data/transfer_data/dexonomy_2026-09-25
./verify.sh
```

## 安装全部交付资源

```bash
resource_root=/data/robotic_data/ztDexonomy
bundle=/data/robotic_data/transfer_data/dexonomy_2026-09-25

mkdir -p "$resource_root/datasets/object" "$resource_root/robot_assets"
"$bundle/extract.sh" "$resource_root/datasets/object" all
"$bundle/extract_wuji2.sh" "$resource_root/robot_assets"
```

## 创建项目入口

先检查路径，已有未知目录时不要覆盖：

```bash
test ! -e assets/object && test ! -L assets/object
test ! -e assets/wuji-description && test ! -L assets/wuji-description

ln -s /data/robotic_data/ztDexonomy/datasets/object assets/object
ln -s /data/robotic_data/ztDexonomy/robot_assets/wuji-description assets/wuji-description
```

## 验证

```bash
test -d assets/object/DGN_5k/processed_data
test -d assets/object/objaverse_5k/processed_data
test -d assets/object/Dexonomy_GRASP_shadow/succ_collect
test -f assets/object/dexonomy_shadow_nflow_cond/ckpts/step_050000.pth
test -f assets/wuji-description/hand2/hand2_beta2/body/mjcf/right.xml
git check-ignore assets/object assets/wuji-description
```

当前安装保留原始压缩包作为恢复来源。删除交接包前应另外确认备份和恢复策略。
