# 数据格式

## 人工标注 YAML

位于 `assets/hand/<hand>/raw_anno/*.yaml`。主要字段：

- `qpos`：手模型关节姿态，不包含自由手腕时由具体转换逻辑补充。
- `contact`：身体名称到接触标注。值可以是手坐标系 6D 点法向、身体关键点索引，或二者列表。
- `required_cbody`：可选的必要接触身体组；缺省时根据 `body_group.yaml` 推导。

6D 接触为 `[x, y, z, nx, ny, nz]`，位置单位为米。

## 初始模板 NPY

由 `op=tmpl` 生成，使用 `numpy.save(dict)`。主要字段包括：

- `hand_name`、`tmpl_name`。
- `grasp_qpos`。
- `hand_cpn_w`：世界坐标接触点和法向。
- `hand_cbody`、`required_cbody`。
- `n_evo`：模板演化次数。

## 初始化与抓取结果 NPY

初始化结果在模板字段之外包含 `obj_cpn_w`、`scene_path`、`obj_pose`、`obj_scale`、`ext_center` 和 `ext_wrench`。抓取结果进一步包含 `squeeze_qpos`、`pregrasp_qpos` 和 `ho_c`。

当前生成格式通常使用形状 `[1, D]` 的抓取姿态；交付的汇总 Shadow 数据使用 `[N, 29]`，一个文件包含同场景下多条成功抓取。
交付的汇总 Shadow 数据还有逐抓取的 `scene_scale`；图鉴导出时将该值乘到场景配置中活动刚体的 `scale` 上。抽样手物几何距离检查表明忽略该倍率会使部分抓取画面中的物体明显偏小、远离手部。

## 场景配置 NPY

场景配置也是保存的 Python 字典：

- `scene`：对象名称到对象类型、模型路径、尺度和姿态。
- `scene_id`：对象、场景类型和尺度组成的标识。
- `task`：任务类型及活动对象。

对象姿态使用 `[x, y, z, qw, qx, qy, qz]`。尺度通常为 3D 数组。场景中的相对模型路径由 `load_scene_cfg` 相对场景文件目录解析。

## 安全与兼容

这些 NPY 文件通过 `allow_pickle=True` 读取，只能加载可信来源。`legacy_api=True` 会转换旧字段名和旧场景结构；新代码不应继续产生旧格式。
