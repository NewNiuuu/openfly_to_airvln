# 项目运行日志

## 2026-07-06

- **修复 HF API 429 限流问题**：`download_parquet.py` 新增 `request_with_retry()` 函数，429/5xx/网络错误时指数退避重试（最多5次）；文件下载同样支持重试；`run_all_subfolders.sh` 子文件夹之间冷却3秒；内置 HF_TOKEN 避免匿名限流
- **优化终端输出**：所有 Python 脚本加 `flush=True` 保证实时输出；`run_all_subfolders.sh` 改用 `tee` 实时显示子流程输出（不再静默捕获）；大量跳过文件时折叠输出避免刷屏
- **新增 `run_all_subfolders.sh`**：批量脚本，只传环境名即可依次处理所有12种轨迹类型，结束后输出磁盘空间和汇总报告（含成功/跳过/失败统计）
- **新增阶段5 `cleanup_unused_frames.py`**：标注生成后删除未被引用的图片帧（step=4抽帧逻辑导致约3/4的帧冗余），支持 `--dry-run` 预览
- **新增阶段6 `cleanup_parquet.py`**：删除已解压的中间 parquet 文件释放磁盘空间，支持 `--dry-run` 预览
- **所有脚本新增 `--env` 参数**：支持 OpenFly 全部14个仿真环境（不再硬编码 env_ue_bigcity），省略时默认 env_ue_bigcity 保持向后兼容
- **重写 `run_pipeline.sh`**：支持双参数 `<env> <subfolder>`，从4阶段扩展为6阶段
- **数据目录重新组织**：`openfly_to_airvln_data/<env>/<subfolder>/`，标注输出到 `annotation/<env>/`
- **更新 README.md + CLAUDE.md**：同步所有变更
- **创建 conda 环境**：`openfly_data`（Python 3.10）

## 2026-06-28

- **README 虚拟环境改为 conda 流程**：`python -m venv` → `conda create` + `conda activate`
- **添加 `requirements.txt`**：列出第三方依赖（requests、pandas、pyarrow），方便新环境一键安装
- **重写 `README.md`**：快速开始（创建虚拟环境→安装依赖→运行）置顶，项目结构和详细说明后置

## 2026-06-27

- **修复 `download_parquet.py` 三个致命问题**：
  1. 加 `?recursive=true` 递归穿透子目录（解决 high_average 等深层目录扫不到文件）
  2. 加 `response.links['next']` 自动翻页（突破 HF API 1000 文件硬限制，high_short 之前只下了 1000/实际更多）
  3. 加 `ThreadPoolExecutor(max_workers=16)` 多线程并发下载（原来是串行 for 循环）
- 附带优化：chunk_size 8KB→64KB、timeout 30s→120s、失败时删残缺文件、新增 `--workers` 参数
- 更新 CLAUDE.md：同步流水线描述、新增 session 规则（强制更新日志）
