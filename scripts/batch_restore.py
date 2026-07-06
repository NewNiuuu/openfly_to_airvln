"""
batch_restore.py
================
将下载好的 parquet 文件解压还原为 metadata.json + images/ 结构。

用法:
    python scripts/batch_restore.py --subfolder high_average
"""

import os
import glob
import argparse
import pandas as pd
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 配置项 =====================
PARQUET_BASE_DIR = "./openfly_syn_parquet"
OUTPUT_BASE_DIR = "./openfly_to_airvln_data"
DEFAULT_ENV = "env_ue_bigcity"
MAX_WORKERS = 16
# ==================================================


def restore_single_parquet(parquet_path, out_dir):
    try:
        table = pq.read_table(parquet_path)
        df = table.to_pandas()
        if df.empty:
            return f"ℹ️ 空文件跳过: {parquet_path}"

        # 获取轨迹ID，没有则用文件名代替
        traj_id = str(df['traj_id'].iloc[0]) if 'traj_id' in df.columns else os.path.basename(parquet_path).replace('.parquet', '')
        traj_out_dir = os.path.join(out_dir, traj_id)
        img_save_dir = os.path.join(traj_out_dir, "images")
        json_path = os.path.join(traj_out_dir, "metadata.json")

        # 断点续传：如果JSON已存在，说明该文件已还原过，直接跳过
        if os.path.exists(json_path):
            return f"⏭️ 跳过(已还原): {traj_id}"

        os.makedirs(img_save_dir, exist_ok=True)
        img_paths = []

        # 逐行解包二进制图片
        for idx, row in df.iterrows():
            img_data = row['image']
            image_bytes = b""
            base_name = ""

            if isinstance(img_data, dict) and "bytes" in img_data:
                image_bytes = bytes(img_data["bytes"])
                path_str = img_data.get("path") or ""
                base_name = os.path.basename(path_str) if path_str else ""
            elif img_data is not None:
                image_bytes = bytes(img_data)
                if 'filename' in df.columns and pd.notna(row['filename']):
                    base_name = os.path.basename(str(row['filename']))

            if not base_name:
                base_name = f"{row['image_id']}.png" if 'image_id' in df.columns and pd.notna(row['image_id']) else f"frame_{idx}.png"
            if not os.path.splitext(base_name)[1]:
                base_name += ".png"

            with open(os.path.join(img_save_dir, base_name), 'wb') as f:
                f.write(image_bytes)

            img_paths.append(os.path.join("images", base_name))

        # 替换二进制为相对路径字符串，导出干净的JSON
        df['image'] = img_paths
        df.to_json(json_path, orient="records", indent=4, force_ascii=False)
        return f"✅ 成功: {traj_id} (共 {len(img_paths)} 张图)"

    except Exception as e:
        return f"❌ 失败: {os.path.basename(parquet_path)} -> {e}"


def main():
    parser = argparse.ArgumentParser(description="批量解压 parquet 数据为图片+metadata")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"仿真环境名，如 env_ue_bigcity, env_airsim_16 等（默认 {DEFAULT_ENV}）")
    parser.add_argument("--subfolder", required=True,
                        help="轨迹类型，如 high_average, high_long 等")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS,
                        help=f"并发线程数，默认 {MAX_WORKERS}")
    args = parser.parse_args()

    src_dir = os.path.join(PARQUET_BASE_DIR, args.env, "astar_data", args.subfolder)
    out_dir = os.path.join(OUTPUT_BASE_DIR, args.env, args.subfolder)

    if not os.path.exists(src_dir):
        print(f"❌ 源目录不存在: {src_dir}")
        exit(1)

    os.makedirs(out_dir, exist_ok=True)

    # 递归查找目录下所有的 parquet 文件
    parquet_files = glob.glob(os.path.join(src_dir, "**/*.parquet"), recursive=True)
    total_files = len(parquet_files)
    print(f"📦 找到 {total_files} 个 Parquet 文件，开始以 {args.workers} 线程批量解压...\n", flush=True)

    success_count = 0
    skip_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(restore_single_parquet, p, out_dir) for p in parquet_files]

        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if "跳过" in result:
                skip_count += 1
                # 跳过的条目只在少量时打印
                if skip_count <= 5 or skip_count % 100 == 0:
                    print(f"  [{i}/{total_files}] {result}", flush=True)
                elif skip_count == 6:
                    print(f"  ... 后续跳过的条目不再逐条显示 ...", flush=True)
            elif result.startswith("❌"):
                fail_count += 1
                print(f"  [{i}/{total_files}] {result}", flush=True)
            else:
                success_count += 1
                print(f"  [{i}/{total_files}] {result}", flush=True)

    print(f"\n🎉 解压完成！成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}", flush=True)
    if fail_count > 0:
        fail_rate = fail_count / total_files
        if fail_rate > 0.1:
            # 超过10%失败率才中断
            print(f"❌ 失败率 {fail_rate:.1%} 超过阈值，中断流程", flush=True)
            exit(1)
        else:
            print(f"⚠️ 有 {fail_count} 个文件解压失败（{fail_rate:.1%}），继续后续阶段", flush=True)


if __name__ == "__main__":
    main()
