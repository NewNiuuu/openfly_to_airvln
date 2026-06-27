# OpenFly → AirVLN 数据转换项目

## 项目概述

将 HuggingFace 上的 OpenFly 数据集（parquet 格式）转换为 AirVLN 格式的 SFT 训练数据。

## 目录结构

```
openfly_to_airvln/
├── openfly_syn_parquet/                          # 中间产物：下载的parquet文件
│   └── env_ue_bigcity/astar_data/
│       ├── high_average/*.parquet
│       ├── high_long/*.parquet
│       └── ...
├── openfly_to_airvln_data/                       # 最终产物
│   ├── <subfolder>/<traj_id>/                    # 解压后的轨迹数据
│   │   ├── metadata.json
│   │   └── images/*.png
│   ├── annotation/                               # 标注jsonl（每子文件夹一个）
│   │   ├── high_average.jsonl
│   │   └── ...
│   └── train.json                                # instruction索引（已有）
├── scripts/
│   ├── download_parquet.py                       # 阶段1：下载parquet
│   ├── batch_restore.py                          # 阶段2：解压parquet→图片+metadata
│   ├── convert_metadata_to_airvln.py             # 阶段3：生成AirVLN标注jsonl
│   ├── fix_slashes.py                            # 阶段4：修正路径斜杠
│   └── run_pipeline.sh                           # 自动化脚本（传参运行单个子文件夹）
├── doc/
│   └── changelog.md                              # 项目运行日志
└── CLAUDE.md                                     # 本文件
```

## 数据子文件夹

来源: `https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly/tree/main/traj/env_ue_bigcity/astar_data`

共12个子文件夹（逐个处理以控制内存）：
- high_average
- high_long
- high_short
- low_average
- low_average_updown
- low_long
- low_long_updown
- low_short
- low_short_updown
- medium_average_updown
- medium_long_updown
- medium_short_updown

## 使用方法

### 跑单个子文件夹（推荐）

```bash
cd /root/nyp/openfly_to_airvln
bash scripts/run_pipeline.sh high_average
# 检查内存: free -h
bash scripts/run_pipeline.sh high_long
```

### 单独运行各阶段

```bash
# 阶段1: 下载
python scripts/download_parquet.py --subfolder high_average

# 阶段2: 解压 (16线程)
python scripts/batch_restore.py --subfolder high_average

# 阶段3: 转标注
python scripts/convert_metadata_to_airvln.py \
    --restored_root ./openfly_to_airvln_data/high_average \
    --train_json ./openfly_to_airvln_data/train.json \
    --output ./openfly_to_airvln_data/annotation/high_average.jsonl \
    --overwrite --continue_on_error

# 阶段4: 修斜杠
python scripts/fix_slashes.py --subfolder high_average
```

## 4阶段流水线

1. **下载** (`download_parquet.py`): 从 hf-mirror.com 下载指定子文件夹的 parquet 文件
   - `?recursive=true` 递归穿透子目录
   - 自动翻页突破 HF API 1000 文件上限
   - 16线程并发下载（`--workers` 可调）
   - 断点续传：已存在文件自动跳过
2. **解压** (`batch_restore.py`): 16线程并发将 parquet 解包为 metadata.json + images/，支持跳过已还原文件
3. **转标注** (`convert_metadata_to_airvln.py`): 读取 metadata.json + train.json 中的 instruction，生成 AirVLN 格式 jsonl
4. **修斜杠** (`fix_slashes.py`): 修正 metadata.json 中的路径反斜杠和文件名映射

## 关键配置

- HuggingFace 镜像: `https://hf-mirror.com`
- Token: 见 `download_parquet.py` 中硬编码
- 并发线程: 16（可通过 `--workers` 参数调整）
- 每阶段有断点续传/跳过机制，中断后可重跑

## 注意事项

- 数据量大，每次只跑一个子文件夹，跑完检查内存再继续
- `train.json` 是所有子文件夹共享的 instruction 索引，不要删除
- 所有脚本的工作目录需为项目根目录 `/root/nyp/openfly_to_airvln/`

## Session 规则

- **每次修改必须同步更新 `doc/changelog.md` 运行日志**，用最简洁的语言记录：日期、改了什么、为什么改
- 每个新 session 启动时先读本文件，了解项目状态后再开始工作
