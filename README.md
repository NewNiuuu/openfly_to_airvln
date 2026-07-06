# OpenFly → AirVLN 数据转换流水线

将 HuggingFace 上的 [OpenFly 数据集](https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly)（parquet 格式）转换为 AirVLN 格式的 SFT 训练数据。

---

## 快速开始

### 1. 创建虚拟环境

```bash
# 创建 conda 环境
conda create -n openfly_data python=3.10 -y

# 激活环境
conda activate openfly_data
```

### 2. 安装依赖

```bash
cd /root/nyp/openfly_to_airvln
pip install -r requirements.txt
```

依赖包说明：

| 包名 | 用途 |
|------|------|
| `requests` | 从 HuggingFace 镜像站下载 parquet 文件 |
| `pandas` | 解析 parquet 数据为 DataFrame |
| `pyarrow` | 读取 parquet 文件格式 |

### 3. 配置环境变量

```bash
export HF_TOKEN="your_huggingface_token"
```

> 如果不设置，脚本仍会尝试匿名下载，但可能会受到速率限制。

### 4. 准备数据

确保 `openfly_to_airvln_data/train.json` 已存在（instruction 索引文件，所有环境和子文件夹共用）。

### 5. 一键运行

#### 批量处理整个环境（推荐）

只需传入环境名，自动依次处理所有12种轨迹类型，结束后输出磁盘空间和汇总报告：

```bash
# 处理整个环境（所有轨迹类型）
bash scripts/run_all_subfolders.sh env_ue_bigcity

# 省略参数默认 env_ue_bigcity
bash scripts/run_all_subfolders.sh

# 处理其他环境
bash scripts/run_all_subfolders.sh env_airsim_16
```

> 不在 train.json 中的轨迹类型会自动跳过（标记为 skipped），不影响其他轨迹的处理。

#### 单个轨迹类型

如果只想处理某个特定轨迹类型：

```bash
# 指定环境 + 轨迹类型
bash scripts/run_pipeline.sh env_ue_bigcity high_average

# 只指定轨迹类型（环境默认 env_ue_bigcity，兼容旧用法）
bash scripts/run_pipeline.sh high_average

# 处理其他仿真环境
bash scripts/run_pipeline.sh env_airsim_16 low_long

# 检查内存（数据量大，防止OOM）
free -h
```

---

## 可用仿真环境

共 14 个仿真环境，来源于 OpenFly 数据集的 `traj/` 目录：

| 环境名 | 类型 |
|--------|------|
| `env_ue_bigcity` | UE 大城市 (默认) |
| `env_ue_smallcity` | UE 小城市 |
| `env_airsim_16` | AirSim 场景16 |
| `env_airsim_18` | AirSim 场景18 |
| `env_airsim_23` | AirSim 场景23 |
| `env_airsim_26` | AirSim 场景26 |
| `env_airsim_gz` | AirSim 广州 |
| `env_airsim_sh` | AirSim 上海 |
| `env_game_gtav` | GTA V |
| `env_gs_ecust` | 高斯 华东理工 |
| `env_gs_nwpu01` | 高斯 西工大01 |
| `env_gs_nwpu02` | 高斯 西工大02 |
| `env_gs_sjtu01` | 高斯 上交01 |
| `env_gs_sjtu02` | 高斯 上交02 |

## 可选轨迹类型

每个环境下的 `astar_data/` 包含以下轨迹类型（不同环境可能有差异）：

| 轨迹类型 | 说明 |
|----------|------|
| `high_average` | 高空-中距离 |
| `high_long` | 高空-长距离 |
| `high_short` | 高空-短距离 |
| `low_average` | 低空-中距离 |
| `low_average_updown` | 低空-中距离-升降 |
| `low_long` | 低空-长距离 |
| `low_long_updown` | 低空-长距离-升降 |
| `low_short` | 低空-短距离 |
| `low_short_updown` | 低空-短距离-升降 |
| `medium_average` | 中空-中距离 |
| `medium_average_updown` | 中空-中距离-升降 |
| `medium_long` | 中空-长距离 |
| `medium_long_updown` | 中空-长距离-升降 |
| `medium_short` | 中空-短距离 |
| `medium_short_updown` | 中空-短距离-升降 |

---

## 分阶段运行

也可以单独运行各阶段（适用于调试或部分重跑）：

```bash
# 阶段1: 下载 parquet 文件
python scripts/download_parquet.py --env env_airsim_16 --subfolder high_average
# 省略 --env 则默认 env_ue_bigcity

# 阶段2: 解压为图片 + metadata（默认16线程）
python scripts/batch_restore.py --env env_airsim_16 --subfolder high_average
# 可自定义线程数：
python scripts/batch_restore.py --env env_airsim_16 --subfolder high_average --workers 8

# 阶段3: 生成 AirVLN 标注 jsonl
python scripts/convert_metadata_to_airvln.py \
    --restored_root ./openfly_to_airvln_data/env_airsim_16/high_average \
    --train_json ./openfly_to_airvln_data/train.json \
    --output ./openfly_to_airvln_data/annotation/env_airsim_16/high_average.jsonl \
    --overwrite --continue_on_error

# 阶段4: 修正 metadata.json 路径斜杠
python scripts/fix_slashes.py --env env_airsim_16 --subfolder high_average

# 阶段5: 清理未引用帧
python scripts/cleanup_unused_frames.py --env env_airsim_16 --subfolder high_average
# 预览模式（不实际删除）：
python scripts/cleanup_unused_frames.py --env env_airsim_16 --subfolder high_average --dry-run

# 阶段6: 清理 parquet 中间文件
python scripts/cleanup_parquet.py --env env_airsim_16 --subfolder high_average
# 预览模式（不实际删除）：
python scripts/cleanup_parquet.py --env env_airsim_16 --subfolder high_average --dry-run
```

---

## 6 阶段流水线说明

| 阶段 | 脚本 | 功能 | 特性 |
|------|------|------|------|
| 1 | `download_parquet.py` | 从 hf-mirror.com 下载 parquet 文件 | 递归扫描 + 自动翻页 + 16线程并发 + 断点续传 |
| 2 | `batch_restore.py` | 解包 parquet 为 metadata.json + images/ | 16线程并发，跳过已还原轨迹 |
| 3 | `convert_metadata_to_airvln.py` | 生成 AirVLN 格式标注 jsonl | 按 step=4 切 turn，支持 continue_on_error |
| 4 | `fix_slashes.py` | 修正 metadata 中的反斜杠和文件名映射 | 自动匹配磁盘上的真实文件名 |
| 5 | `cleanup_unused_frames.py` | 删除标注中未被引用的图片帧 | step=4 抽帧后约 3/4 帧冗余，支持 dry-run |
| 6 | `cleanup_parquet.py` | 删除已解压的中间 parquet 文件 | 释放磁盘空间，支持 dry-run |

---

## 项目结构

```
openfly_to_airvln/
├── scripts/
│   ├── download_parquet.py                       # 阶段1：从hf-mirror下载parquet
│   ├── batch_restore.py                          # 阶段2：解压parquet→图片+metadata
│   ├── convert_metadata_to_airvln.py             # 阶段3：生成AirVLN标注jsonl
│   ├── fix_slashes.py                            # 阶段4：修正路径斜杠
│   ├── cleanup_unused_frames.py                  # 阶段5：删除未引用的帧
│   ├── cleanup_parquet.py                        # 阶段6：删除中间parquet文件
│   ├── run_pipeline.sh                           # 单个轨迹类型自动化脚本
│   └── run_all_subfolders.sh                     # 批量处理整个环境的所有轨迹类型
├── openfly_syn_parquet/                          # 中间产物（流程结束后自动清理）
│   └── <env>/astar_data/<subfolder>/*.parquet
├── openfly_to_airvln_data/                       # 最终产物
│   ├── <env>/<subfolder>/                        # 解压后的轨迹数据
│   │   └── <traj_id>/
│   │       ├── metadata.json
│   │       └── images/*.png                      # 仅保留标注引用的帧
│   ├── annotation/<env>/                         # AirVLN标注文件
│   │   ├── high_average.jsonl
│   │   └── ...
│   └── train.json                                # instruction索引（需提前准备）
├── doc/
│   └── changelog.md                              # 项目运行日志
├── requirements.txt                              # Python 依赖
├── CLAUDE.md
└── README.md
```

---

## 注意事项

- **内存控制**：数据量大，建议每次只跑一个子文件夹，跑完用 `free -h` 检查内存再继续
- **断点续传**：阶段1-2均支持中断后重跑，会自动跳过已完成部分
- **错误处理**：`run_pipeline.sh` 在任何阶段失败时会立即停止，不会继续后续阶段
- **工作目录**：所有脚本需在项目根目录 `/root/nyp/openfly_to_airvln/` 下运行
- **向后兼容**：所有脚本省略 `--env` 参数时默认使用 `env_ue_bigcity`

---

## 数据来源

- 数据集：[IPEC-COMMUNITY/OpenFly](https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly)
- 下载镜像：https://hf-mirror.com
