# OpenFly → AirVLN 数据转换项目

## 项目概述

将 HuggingFace 上的 OpenFly 数据集（parquet 格式）转换为 AirVLN 格式的 SFT 训练数据。

## 目录结构

```
openfly_to_airvln/
├── openfly_syn_parquet/                          # 中间产物（流程结束后自动清理）
│   └── <env>/astar_data/<subfolder>/*.parquet
├── openfly_to_airvln_data/                       # 最终产物
│   ├── <env>/<subfolder>/<traj_id>/              # 解压后的轨迹数据
│   │   ├── metadata.json
│   │   └── images/*.png                          # 仅保留标注引用的帧
│   ├── annotation/<env>/                         # 标注jsonl（每子文件夹一个）
│   │   ├── high_average.jsonl
│   │   └── ...
│   └── train.json                                # instruction索引（已有）
├── scripts/
│   ├── download_parquet.py                       # 阶段1：下载parquet
│   ├── batch_restore.py                          # 阶段2：解压parquet→图片+metadata
│   ├── convert_metadata_to_airvln.py             # 阶段3：生成AirVLN标注jsonl
│   ├── fix_slashes.py                            # 阶段4：修正路径斜杠
│   ├── cleanup_unused_frames.py                  # 阶段5：删除未引用的帧
│   ├── cleanup_parquet.py                        # 阶段6：删除中间parquet文件
│   ├── prepare_and_upload_blob.py                # 阶段7：清洗+加路径前缀+azcopy上传Blob
│   ├── run_pipeline.sh                           # 单个轨迹类型自动化脚本（阶段8删本地内联于此）
│   └── run_all_subfolders.sh                     # 批量处理整个环境的所有轨迹类型
├── doc/
│   └── changelog.md                              # 项目运行日志
└── CLAUDE.md                                     # 本文件
```

## 可用仿真环境

来源: `https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly/tree/main/traj`

共14个仿真环境：
- env_ue_bigcity (默认)
- env_ue_smallcity
- env_airsim_16, env_airsim_18, env_airsim_23, env_airsim_26
- env_airsim_gz, env_airsim_sh
- env_game_gtav
- env_gs_ecust, env_gs_nwpu01, env_gs_nwpu02, env_gs_sjtu01, env_gs_sjtu02

## 轨迹类型

每个环境下 `astar_data/` 中的轨迹类型（不同环境可能有差异）：
- high_average, high_long, high_short
- low_average, low_average_updown, low_long, low_long_updown, low_short, low_short_updown
- medium_average, medium_average_updown, medium_long, medium_long_updown, medium_short, medium_short_updown

## 使用方法

### 批量处理整个环境（推荐）

```bash
cd /root/nyp/openfly_to_airvln
conda activate openfly_data

# 处理一个环境下全部轨迹类型（依次走完整8阶段，含上传Blob）
bash scripts/run_all_subfolders.sh env_ue_bigcity

# 省略参数默认 env_ue_bigcity
bash scripts/run_all_subfolders.sh

# 处理其他环境
bash scripts/run_all_subfolders.sh env_airsim_16
```

执行完毕后输出：磁盘空间报告 + 成功/跳过/失败汇总表。

### 跑单个环境+轨迹类型

```bash
cd /root/nyp/openfly_to_airvln
conda activate openfly_data

# 指定环境 + 轨迹类型
bash scripts/run_pipeline.sh env_ue_bigcity high_average

# 只指定轨迹类型（默认 env_ue_bigcity，兼容旧用法）
bash scripts/run_pipeline.sh high_average

# 处理其他环境
bash scripts/run_pipeline.sh env_airsim_16 low_long

# 检查内存
free -h
```

### 单独运行各阶段

```bash
# 阶段1: 下载
python scripts/download_parquet.py --env env_airsim_16 --subfolder high_average

# 阶段2: 解压 (16线程)
python scripts/batch_restore.py --env env_airsim_16 --subfolder high_average

# 阶段3: 转标注
python scripts/convert_metadata_to_airvln.py \
    --restored_root ./openfly_to_airvln_data/env_airsim_16/high_average \
    --train_json ./openfly_to_airvln_data/train.json \
    --output ./openfly_to_airvln_data/annotation/env_airsim_16/high_average.jsonl \
    --overwrite --continue_on_error

# 阶段4: 修斜杠
python scripts/fix_slashes.py --env env_airsim_16 --subfolder high_average

# 阶段5: 清理未引用帧
python scripts/cleanup_unused_frames.py --env env_airsim_16 --subfolder high_average
# 预览模式：
python scripts/cleanup_unused_frames.py --env env_airsim_16 --subfolder high_average --dry-run

# 阶段6: 清理parquet中间文件
python scripts/cleanup_parquet.py --env env_airsim_16 --subfolder high_average
# 预览模式：
python scripts/cleanup_parquet.py --env env_airsim_16 --subfolder high_average --dry-run

# 阶段7: 清洗+上传Blob（单个子文件夹）
python scripts/prepare_and_upload_blob.py --env env_airsim_16 --subfolder high_average
# 整环境模式（不带 --subfolder）：清空标注→修路径→上传整个环境
python scripts/prepare_and_upload_blob.py --env env_airsim_16
# 预览 / 只清洗不上传：
python scripts/prepare_and_upload_blob.py --env env_airsim_16 --dry-run
python scripts/prepare_and_upload_blob.py --env env_airsim_16 --skip-upload
# 阶段8（删本地）内联在 run_pipeline.sh，无独立脚本；SKIP_UPLOAD=1 可跳过阶段7-8
```

## 8阶段流水线

1. **下载** (`download_parquet.py`): 从 hf-mirror.com 下载指定环境+轨迹类型的 parquet 文件
   - `?recursive=true` 递归穿透子目录
   - 自动翻页突破 HF API 1000 文件上限
   - 16线程并发下载（`--workers` 可调）
   - 断点续传：已存在文件自动跳过
   - 429/5xx/网络错误指数退避重试（最多5次）；批量模式先 `--scan-only` 预扫描缓存文件列表，各子文件夹用 `--from-cache` 复用，避免重复调 API
2. **解压** (`batch_restore.py`): 16线程并发将 parquet 解包为 metadata.json + images/，支持跳过已还原文件（少量失败不中断流水线）
3. **转标注** (`convert_metadata_to_airvln.py`): 读取 metadata.json + train.json 中的 instruction，生成 AirVLN 格式 jsonl
4. **修斜杠** (`fix_slashes.py`): 修正 metadata.json 中的路径反斜杠和文件名映射
5. **清理未引用帧** (`cleanup_unused_frames.py`): 解析标注 JSONL，删除 images/ 中未被引用的图片帧（step=4 抽帧后约 3/4 帧冗余）
6. **清理 parquet** (`cleanup_parquet.py`): 删除已解压的中间 parquet 文件释放磁盘空间
7. **清洗+上传 Blob** (`prepare_and_upload_blob.py`): 删除空标注对应的数据、给标注 JSONL 的 image 路径加 `vln/openfly` 前缀，用 azcopy 上传数据和标注到 Azure Blob（`output/liyan/vln/openfly/<env>/`）。`SKIP_UPLOAD=1` 可跳过
8. **删本地** (内联于 `run_pipeline.sh`): 上传成功后删除本地图片数据释放磁盘空间。`SKIP_UPLOAD=1` 时一并跳过

## 关键配置

- HuggingFace 镜像: `https://hf-mirror.com`
- Token: 见环境变量 `HF_TOKEN`
- 并发线程: 16（可通过 `--workers` 参数调整）
- 默认环境: `env_ue_bigcity`（所有脚本省略 `--env` 时使用）
- 每阶段有断点续传/跳过机制，中断后可重跑
- Azure Blob 上传: 目标 `output/liyan/vln/openfly/<env>/`，标注 image 路径前缀 `vln/openfly`，SAS token 见环境变量 `BLOB_SAS_TOKEN`（`.env` 中配置）
- `SKIP_UPLOAD=1` 跳过阶段7-8（只做本地转换不上传）；`SKIP_DOWNLOAD=1` 跳过阶段1

## 注意事项

- 数据量大，每次只跑一个子文件夹，跑完检查内存再继续
- `train.json` 是所有环境和子文件夹共享的 instruction 索引，不要删除
- 所有脚本的工作目录需为项目根目录 `/root/nyp/openfly_to_airvln/`
- 所有脚本省略 `--env` 参数时默认使用 `env_ue_bigcity`（向后兼容）

## Session 规则

- **每次修改必须同步更新 `doc/changelog.md` 运行日志**，用最简洁的语言记录：日期、改了什么、为什么改
- 每个新 session 启动时先读本文件，了解项目状态后再开始工作
