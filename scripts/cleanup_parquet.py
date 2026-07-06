"""
cleanup_parquet.py
==================
删除指定子文件夹对应的中间 parquet 文件。

parquet 文件在阶段2解压后不再需要，本脚本清理这些中间产物以释放磁盘空间。

用法:
    python scripts/cleanup_parquet.py --subfolder high_average
    python scripts/cleanup_parquet.py --subfolder high_average --dry-run
"""

import os
import shutil
import argparse

# ===================== 配置项 =====================
PARQUET_BASE_DIR = "./openfly_syn_parquet"
DEFAULT_ENV = "env_ue_bigcity"
# ==================================================


def cleanup_parquet(env, subfolder, dry_run=False):
    """删除指定环境+子文件夹的 parquet 中间文件。"""

    parquet_dir = os.path.join(PARQUET_BASE_DIR, env, "astar_data", subfolder)

    if not os.path.exists(parquet_dir):
        print(f"ℹ️  Parquet 目录不存在（可能已清理）: {parquet_dir}", flush=True)
        return

    # 计算目录大小
    total_size = 0
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(parquet_dir):
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            total_size += os.path.getsize(fpath)
            file_count += 1

    size_mb = total_size / (1024 * 1024)
    size_gb = total_size / (1024 * 1024 * 1024)

    if size_gb >= 1:
        size_str = f"{size_gb:.2f} GB"
    else:
        size_str = f"{size_mb:.1f} MB"

    print(f"🗂️  Parquet 目录: {parquet_dir}", flush=True)
    print(f"   文件数: {file_count}", flush=True)
    print(f"   占用空间: {size_str}", flush=True)

    if dry_run:
        print(f"\n⚠️  DRY-RUN 模式，未实际删除。去掉 --dry-run 参数执行真正清理。", flush=True)
        return

    # 删除整个子文件夹目录
    shutil.rmtree(parquet_dir)
    print(f"\n✅ 已删除 parquet 中间文件，释放 {size_str} 磁盘空间。", flush=True)


def main():
    parser = argparse.ArgumentParser(description="删除中间 parquet 文件")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"仿真环境名，如 env_ue_bigcity, env_airsim_16 等（默认 {DEFAULT_ENV}）")
    parser.add_argument("--subfolder", required=True,
                        help="轨迹类型，如 high_average, high_long 等")
    parser.add_argument("--dry-run", action="store_true",
                        help="只统计不实际删除（预览模式）")
    args = parser.parse_args()

    cleanup_parquet(args.env, args.subfolder, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
