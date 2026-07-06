"""
download_parquet.py
===================
从 huggingface 镜像站下载指定子文件夹的 parquet 文件到本地。

核心特性:
  - 递归扫描：穿透所有子目录，不遗漏深层文件
  - 自动翻页：突破 HF API 单次 1000 文件上限
  - 多线程并发：默认 16 线程并行下载
  - 断点续传：已存在文件自动跳过

用法:
    python scripts/download_parquet.py --subfolder high_average
    python scripts/download_parquet.py --subfolder high_short --workers 8
"""

import os
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 配置项 =====================
REPO_ID = "IPEC-COMMUNITY/OpenFly"
BASE_FOLDER = "traj"
LOCAL_BASE_DIR = "./openfly_syn_parquet"
TOKEN = os.environ.get("HF_TOKEN", "")
MIRROR_URL = "https://hf-mirror.com"
DEFAULT_WORKERS = 16
DEFAULT_ENV = "env_ue_bigcity"
CHUNK_SIZE = 65536  # 64KB per chunk for better throughput
DOWNLOAD_TIMEOUT = 120  # 大文件需要更长超时
# ==================================================


def fetch_all_parquet_files(folder_path, headers):
    """
    递归扫描 + 自动翻页，获取全量 parquet 文件列表。

    修正1: ?recursive=true 穿透所有子文件夹
    修正2: while 循环解析 Link header，突破 1000 文件上限
    """
    # 核心修正1：加上 recursive=true 强行穿透所有子文件夹
    api_url = f"{MIRROR_URL}/api/datasets/{REPO_ID}/tree/main/{folder_path}?recursive=true"

    parquet_files = []
    page_count = 0

    # 核心修正2：自动翻页循环，突破 1000 文件上限
    while api_url:
        page_count += 1
        print(f"  📡 请求第 {page_count} 页...", flush=True)
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code != 200:
            print(f"❌ 获取目录失败 (第{page_count}页): {response.status_code} - {response.text}", flush=True)
            exit(1)

        for f in response.json():
            if f.get('type') == 'file' and f['path'].endswith('.parquet'):
                parquet_files.append(f['path'])

        # 检查是否有下一页（Link header 分页）
        if 'next' in response.links:
            next_url = response.links['next']['url']
            # 确保使用镜像域名
            api_url = next_url.replace('huggingface.co', 'hf-mirror.com')
            print(f"  📄 第{page_count}页完成，累计 {len(parquet_files)} 个文件，继续翻页...", flush=True)
        else:
            break

    return parquet_files


def download_single_file(file_path, local_dir, headers):
    """下载单个文件，支持断点续传（跳过已存在文件）"""
    # 保留相对子路径结构
    # file_path 示例: traj/env_ue_bigcity/astar_data/high_average/sub1/xxx.parquet
    # 需要保留 subfolder 下的相对路径
    rel_path = file_path.split('/', 4)[-1] if file_path.count('/') >= 4 else file_path.split('/')[-1]
    save_path = os.path.join(local_dir, rel_path)
    file_name = file_path.split('/')[-1]

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 断点续传：已存在且非空则跳过
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return ("skip", f"⏭️ 跳过已存在: {file_name}")

    download_url = f"{MIRROR_URL}/datasets/{REPO_ID}/resolve/main/{file_path}"

    try:
        with requests.get(download_url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                    f.write(chunk)
        return ("success", f"✅ 成功: {file_name}")
    except Exception as e:
        # 删除可能写了一半的残缺文件
        if os.path.exists(save_path):
            os.remove(save_path)
        return ("fail", f"❌ 失败: {file_name} ({e})")


def download_subfolder(env, subfolder, workers):
    folder_path = f"{BASE_FOLDER}/{env}/astar_data/{subfolder}"
    local_dir = os.path.join(LOCAL_BASE_DIR, env, "astar_data", subfolder)

    # 确保下载文件夹存在
    os.makedirs(local_dir, exist_ok=True)

    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

    print(f"🔍 正在扫描 {folder_path} 的全量文件列表...", flush=True)
    parquet_files = fetch_all_parquet_files(folder_path, headers)

    if not parquet_files:
        print(f"⚠️ 未找到任何 parquet 文件，请检查子文件夹名称是否正确: {subfolder}", flush=True)
        exit(1)

    print(f"✅ 扫描完毕！共锁定 {len(parquet_files)} 个 Parquet 文件。", flush=True)
    print(f"🚀 启动 {workers} 线程并行下载...\n", flush=True)

    success_count = 0
    skip_count = 0
    fail_count = 0
    total_files = len(parquet_files)

    # 核心修正3：多线程并发下载
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(download_single_file, fp, local_dir, headers): fp
            for fp in parquet_files
        }

        for future in as_completed(future_to_file):
            status, msg = future.result()
            done = success_count + skip_count + fail_count + 1
            if status == "success":
                success_count += 1
                print(f"  [{done}/{total_files}] {msg}", flush=True)
            elif status == "skip":
                skip_count += 1
                # 跳过的文件只在少量时打印，避免刷屏
                if skip_count <= 5 or skip_count % 100 == 0:
                    print(f"  [{done}/{total_files}] {msg}", flush=True)
                elif skip_count == 6:
                    print(f"  ... 后续跳过的文件不再逐条显示 ...", flush=True)
            else:
                fail_count += 1
                print(f"  [{done}/{total_files}] {msg}", flush=True)

    print(f"\n🎉 下载完成！成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}", flush=True)
    print(f"   总计: {success_count + skip_count + fail_count} / {len(parquet_files)}", flush=True)
    if fail_count > 0:
        print(f"⚠️ 有 {fail_count} 个文件下载失败，请重新运行脚本补齐（已下载文件会自动跳过）", flush=True)
        exit(1)


def main():
    parser = argparse.ArgumentParser(description="下载 OpenFly parquet 数据")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"仿真环境名，如 env_ue_bigcity, env_airsim_16 等（默认 {DEFAULT_ENV}）")
    parser.add_argument("--subfolder", required=True,
                        help="轨迹类型，如 high_average, high_long 等")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"并发下载线程数（默认 {DEFAULT_WORKERS}）")
    args = parser.parse_args()
    download_subfolder(args.env, args.subfolder, args.workers)


if __name__ == "__main__":
    main()
