# OpenFly → AirVLN 数据转换流水线

将 HuggingFace 上的 [OpenFly 数据集](https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly)（parquet 格式）转换为 AirVLN 格式的 SFT 训练数据。

## 项目结构

```
openfly_to_airvln/
├── openfly_syn_parquet/                          # 阶段1产物：下载的parquet文件
│   └── env_ue_bigcity/astar_data/
│       ├── high_average/*.parquet
│       ├── high_long/*.parquet
│       └── ...
├── openfly_to_airvln_data/                       # 阶段2-4产物
│   ├── high_average/                             # 解压后的轨迹数据
│   │   └── <traj_id>/
│   │       ├── metadata.json
│   │       └── images/*.png
│   ├── high_long/
│   │   └── ...
│   ├── annotation/                               # AirVLN标注文件（每子文件夹一个jsonl）
│   │   ├── high_average.jsonl
│   │   ├── high_long.jsonl
│   │   └── ...
│   └── train.json                                # instruction索引（需提前准备）
├── scripts/
│   ├── download_parquet.py                       # 阶段1：从hf-mirror下载parquet
│   ├── batch_restore.py                          # 阶段2：解压parquet→图片+metadata
│   ├── convert_metadata_to_airvln.py             # 阶段3：生成AirVLN标注jsonl
│   ├── fix_slashes.py                            # 阶段4：修正路径斜杠
│   └── run_pipeline.sh                           # 一键自动化脚本
├── CLAUDE.md
└── README.md
```

## 环境准备

### 依赖安装

```bash
pip install pandas pyarrow requests
```

### 环境变量

运行前需设置 HuggingFace Token：

```bash
export HF_TOKEN="your_huggingface_token"
```

### 数据准备

确保 `openfly_to_airvln_data/train.json` 已存在（instruction 索引文件，所有子文件夹共用）。

## 使用方法

### 一键运行（推荐）

每次传入一个子文件夹名，自动完成 下载 → 解压 → 转标注 → 修斜杠 全流程：

```bash
cd /path/to/openfly_to_airvln

# 跑一个子文件夹
bash scripts/run_pipeline.sh high_average

# 检查内存（数据量大，防止OOM）
free -h

# 确认内存ok后再跑下一个
bash scripts/run_pipeline.sh high_long
```

### 可选子文件夹列表

| 子文件夹 | 说明 |
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
| `medium_average_updown` | 中空-中距离-升降 |
| `medium_long_updown` | 中空-长距离-升降 |
| `medium_short_updown` | 中空-短距离-升降 |

### 分阶段运行

也可以单独运行各阶段：

```bash
# 阶段1: 下载 parquet 文件
python scripts/download_parquet.py --subfolder high_average

# 阶段2: 解压为图片 + metadata（默认16线程）
python scripts/batch_restore.py --subfolder high_average
# 可自定义线程数：
python scripts/batch_restore.py --subfolder high_average --workers 8

# 阶段3: 生成 AirVLN 标注 jsonl
python scripts/convert_metadata_to_airvln.py \
    --restored_root ./openfly_to_airvln_data/high_average \
    --train_json ./openfly_to_airvln_data/train.json \
    --output ./openfly_to_airvln_data/annotation/high_average.jsonl \
    --overwrite --continue_on_error

# 阶段4: 修正 metadata.json 路径斜杠
python scripts/fix_slashes.py --subfolder high_average
```

## 4阶段流水线说明

| 阶段 | 脚本 | 功能 | 特性 |
|------|------|------|------|
| 1 | `download_parquet.py` | 从 hf-mirror.com 下载 parquet 文件 | 断点续传（跳过已下载文件） |
| 2 | `batch_restore.py` | 解包 parquet 为 metadata.json + images/ | 16线程并发，跳过已还原轨迹 |
| 3 | `convert_metadata_to_airvln.py` | 生成 AirVLN 格式标注 jsonl | 按 step=4 切 turn，支持 continue_on_error |
| 4 | `fix_slashes.py` | 修正 metadata 中的反斜杠和文件名映射 | 自动匹配磁盘上的真实文件名 |

## 注意事项

- **内存控制**：数据量大，建议每次只跑一个子文件夹，跑完用 `free -h` 检查内存再继续
- **断点续传**：所有阶段均支持中断后重跑，会自动跳过已完成部分
- **错误处理**：`run_pipeline.sh` 在任何阶段失败时会立即停止，不会继续后续阶段
- **工作目录**：所有脚本需在项目根目录下运行

## 数据来源

- 数据集：[IPEC-COMMUNITY/OpenFly](https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly)
- 下载镜像：https://hf-mirror.com
