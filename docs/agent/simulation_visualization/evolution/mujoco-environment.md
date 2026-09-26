# MuJoCo 环境

## 类结构

- `MuJoCo_BaseEnv`：装配手和场景模型、状态访问、接触解析及调试输出。
- `MuJoCo_OptEnv`：向目标接触点施力，保持手部稳定，生成 squeeze 姿态。
- `MuJoCo_EvalEnv`：执行 force-closure 或运动轨迹并按物体位姿变化判断成功。
- `MuJoCo_VisEnv`：执行正向运动学，提取视觉或碰撞网格并导出姿态网格。

## 模型语义

Shadow 数据中的姿态为 29 维，其中自由手腕 7 维、手关节 22 维。场景对象由 NPY 场景配置引用对象 XML、URDF、视觉网格、信息文件、尺度和初始姿态。

## 可视化模式

`visual` 使用 contype 为 0 的视觉几何，`collision` 使用碰撞几何并对网格取凸包。OBJ 导出可选手、物体、接触箭头和骨架；USD 导出可组合多个姿态阶段。

## 当前验证

MuJoCo Menagerie 的 Shadow 网格已恢复。项目内 `.viz-env` 使用 Python 3.10、MuJoCo 3.3.3 和 Trimesh 4.5.3，已经加载真实 Shadow XML、Objaverse 场景和一条抓取姿态，并成功提取手与物体视觉网格。该验证属于离线运动学与资产导出，不是物理抓取评估。
