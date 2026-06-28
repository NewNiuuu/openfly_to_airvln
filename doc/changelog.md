# 项目运行日志

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
