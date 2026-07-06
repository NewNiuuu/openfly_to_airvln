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
import time
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== 配置项 =====================
REPO_ID = "IPEC-COMMUNITY/OpenFly"
BASE_FOLDER = "traj"
LOCAL_BASE_DIR = "./openfly_syn_parquet"
TOKEN = os.environ.get("HF_TOKEN", "")
MIRROR_URL = "https://hf-mirror.com"
DEFAULT_WORKERS = 4
DEFAULT_ENV = "env_ue_bigcity"
CHUNK_SIZE = 65536  # 64KB per chunk for better throughput
DOWNLOAD_TIMEOUT = 120  # 大文件需要更长超时
API_MAX_RETRIES = 5  # API 请求最大重试次数
API_RETRY_BASE_WAIT = 60  # 429限流重试基础等待秒数（5分钟窗口，需要等久一点）
DOWNLOAD_INTERVAL = 0.3  # 每个文件下载后的间隔秒数，控制请求速率
# ==================================================


def request_with_retry(url, headers, timeout=30, max_retries=API_MAX_RETRIES):
    """带重试机制的 HTTP GET 请求，处理 429 限流和网络错误。"""
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                # 限流：指数退避等待
                wait = API_RETRY_BASE_WAIT * attempt
                print(f"  ⏳ 被限流 (429)，等待 {wait}s 后重试 (第{attempt}/{max_retries}次)...", flush=True)
                time.sleep(wait)
                continue

            if response.status_code >= 500:
                # 服务器错误：短暂等待后重试
                wait = 5 * attempt
                print(f"  ⚠️ 服务器错误 ({response.status_code})，等待 {wait}s 后重试 (第{attempt}/{max_retries}次)...", flush=True)
                time.sleep(wait)
                continue

            # 其他错误（如 404）不重试
            return response

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            wait = 5 * attempt
            print(f"  ⚠️ 网络错误: {e}，等待 {wait}s 后重试 (第{attempt}/{max_retries}次)...", flush=True)
            time.sleep(wait)

    # 全部重试失败
    print(f"❌ 请求失败，已重试 {max_retries} 次: {url}", flush=True)
    return None


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
        response = request_with_retry(api_url, headers, timeout=30)
        if response is None or response.status_code != 200:
            status = response.status_code if response else "无响应"
            text = response.text if response else "重试耗尽"
            print(f"❌ 获取目录失败 (第{page_count}页): {status} - {text}", flush=True)
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

    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            with requests.get(download_url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                if r.status_code == 429:
                    wait = API_RETRY_BASE_WAIT * attempt
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
            return ("success", f"✅ 成功: {file_name}")
        except Exception as e:
            # 删除可能写了一半的残缺文件
            if os.path.exists(save_path):
                os.remove(save_path)
            if attempt < API_MAX_RETRIES:
                time.sleep(5 * attempt)
                continue
            return ("fail", f"❌ 失败: {file_name} ({e})")

    # 不应到这里，但安全兜底
    return ("fail", f"❌ 失败: {file_name} (重试耗尽)")


def download_files(parquet_files, local_base_dir, headers, workers, label=""):
    """下载一批 parquet 文件，返回 (success, skip, fail) 计数。"""
    success_count = 0
    skip_count = 0
    fail_count = 0
    total_files = len(parquet_files)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(download_single_file, fp, local_base_dir, headers): fp
            for fp in parquet_files
        }

        for future in as_completed(future_to_file):
            status, msg = future.result()
            done = success_count + skip_count + fail_count + 1
            if status == "success":
                success_count += 1
                print(f"  {label}[{done}/{total_files}] {msg}", flush=True)
            elif status == "skip":
                skip_count += 1
                if skip_count <= 5 or skip_count % 100 == 0:
                    print(f"  {label}[{done}/{total_files}] {msg}", flush=True)
                elif skip_count == 6:
                    print(f"  {label}... 后续跳过的文件不再逐条显示 ...", flush=True)
            else:
                fail_count += 1
                print(f"  {label}[{done}/{total_files}] {msg}", flush=True)

    return success_count, skip_count, fail_count


def download_subfolder(env, subfolder, workers):
    """下载单个子文件夹的 parquet 文件（需调用一次 API 扫描）。"""
    folder_path = f"{BASE_FOLDER}/{env}/astar_data/{subfolder}"
    local_dir = os.path.join(LOCAL_BASE_DIR, env, "astar_data", subfolder)

    os.makedirs(local_dir, exist_ok=True)

    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

    print(f"🔍 正在扫描 {folder_path} 的文件列表...", flush=True)
    parquet_files = fetch_all_parquet_files(folder_path, headers)

    if not parquet_files:
        print(f"⚠️ 未找到任何 parquet 文件，请检查子文件夹名称是否正确: {subfolder}", flush=True)
        exit(1)

    print(f"✅ 扫描完毕！共 {len(parquet_files)} 个文件。", flush=True)
    print(f"🚀 启动 {workers} 线程下载...\n", flush=True)

    success, skip, fail = download_files(parquet_files, local_dir, headers, workers)

    print(f"\n🎉 下载完成！成功: {success}, 跳过: {skip}, 失败: {fail}", flush=True)
    print(f"   总计: {success + skip + fail} / {len(parquet_files)}", flush=True)
    if fail > 0:
        print(f"⚠️ 有 {fail} 个文件下载失败，请重新运行脚本补齐（已下载文件会自动跳过）", flush=True)
        exit(1)


def download_all_subfolders(env, workers):
    """一次 API 调用扫描整个环境，按子文件夹分组逐个下载。"""
    folder_path = f"{BASE_FOLDER}/{env}/astar_data"
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

    print(f"🔍 一次性扫描 {folder_path} 下全部文件...", flush=True)
    all_files = fetch_all_parquet_files(folder_path, headers)

    if not all_files:
        print(f"⚠️ 未找到任何 parquet 文件: {folder_path}", flush=True)
        exit(1)

    # 按子文件夹分组
    # 路径形如: traj/env_ue_bigcity/astar_data/high_average/xxx.parquet
    groups = {}
    for fp in all_files:
        parts = fp.split("/")
        # parts: ['traj', 'env_ue_bigcity', 'astar_data', 'high_average', 'xxx.parquet']
        if len(parts) >= 5:
            subfolder = parts[3]  # astar_data 之后的第一级
            groups.setdefault(subfolder, []).append(fp)

    print(f"✅ 扫描完毕！共 {len(all_files)} 个文件，分布在 {len(groups)} 个子文件夹中。\n", flush=True)

    total_success = 0
    total_skip = 0
    total_fail = 0

    for idx, (subfolder, files) in enumerate(sorted(groups.items()), 1):
        local_dir = os.path.join(LOCAL_BASE_DIR, env, "astar_data", subfolder)
        os.makedirs(local_dir, exist_ok=True)

        print(f"📦 [{idx}/{len(groups)}] {subfolder}: {len(files)} 个文件", flush=True)
        success, skip, fail = download_files(files, local_dir, headers, workers, label=f"({subfolder}) ")
        total_success += success
        total_skip += skip
        total_fail += fail
        print(f"   → 成功: {success}, 跳过: {skip}, 失败: {fail}\n", flush=True)

    print(f"🎉 全部下载完成！成功: {total_success}, 跳过: {total_skip}, 失败: {total_fail}", flush=True)
    if total_fail > 0:
        print(f"⚠️ 有 {total_fail} 个文件下载失败，请重新运行补齐", flush=True)
        exit(1)


def scan_and_cache(env):
    """一次性扫描整个环境的文件列表，缓存到本地 JSON 文件。"""
    folder_path = f"{BASE_FOLDER}/{env}/astar_data"
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

    print(f"🔍 一次性扫描 {folder_path} 下全部文件列表...", flush=True)
    all_files = fetch_all_parquet_files(folder_path, headers)

    if not all_files:
        print(f"⚠️ 未找到任何 parquet 文件: {folder_path}", flush=True)
        exit(1)

    # 按子文件夹分组
    groups = {}
    for fp in all_files:
        parts = fp.split("/")
        if len(parts) >= 5:
            subfolder = parts[3]
            groups.setdefault(subfolder, []).append(fp)

    # 缓存到本地文件
    import json
    cache_dir = os.path.join(LOCAL_BASE_DIR, env)
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "_file_list_cache.json")
    with open(cache_path, 'w') as f:
        json.dump(groups, f)

    print(f"✅ 扫描完毕！共 {len(all_files)} 个文件，分布在 {len(groups)} 个子文件夹中。", flush=True)
    print(f"   缓存已保存: {cache_path}", flush=True)
    for sub, files in sorted(groups.items()):
        print(f"   • {sub}: {len(files)} 个文件", flush=True)


def download_from_cache(env, subfolder, workers):
    """从缓存的文件列表中读取指定子文件夹的文件，直接下载（不调 API）。"""
    import json
    cache_path = os.path.join(LOCAL_BASE_DIR, env, "_file_list_cache.json")

    if not os.path.exists(cache_path):
        print(f"⚠️ 缓存文件不存在: {cache_path}", flush=True)
        print(f"   请先运行: python scripts/download_parquet.py --env {env} --scan-only", flush=True)
        exit(1)

    with open(cache_path) as f:
        groups = json.load(f)

    if subfolder not in groups:
        print(f"⚠️ 缓存中没有子文件夹 '{subfolder}'，可能该环境下不存在此轨迹类型", flush=True)
        print(f"   可用的子文件夹: {', '.join(sorted(groups.keys()))}", flush=True)
        exit(1)

    parquet_files = groups[subfolder]
    local_dir = os.path.join(LOCAL_BASE_DIR, env, "astar_data", subfolder)
    os.makedirs(local_dir, exist_ok=True)
    headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

    print(f"📦 从缓存加载 {subfolder}: {len(parquet_files)} 个文件", flush=True)
    print(f"🚀 启动 {workers} 线程下载...\n", flush=True)

    success, skip, fail = download_files(parquet_files, local_dir, headers, workers)

    print(f"\n🎉 下载完成！成功: {success}, 跳过: {skip}, 失败: {fail}", flush=True)
    if fail > 0:
        print(f"⚠️ 有 {fail} 个文件下载失败，请重新运行补齐", flush=True)
        exit(1)


def main():
    parser = argparse.ArgumentParser(description="下载 OpenFly parquet 数据")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"仿真环境名，如 env_ue_bigcity, env_airsim_16 等（默认 {DEFAULT_ENV}）")
    parser.add_argument("--subfolder", default=None,
                        help="轨迹类型，如 high_average, high_long 等")
    parser.add_argument("--scan-only", action="store_true",
                        help="只扫描文件列表并缓存到本地（不下载）")
    parser.add_argument("--from-cache", action="store_true",
                        help="从缓存的文件列表下载（不调 API）")
    parser.add_argument("--all", action="store_true",
                        help="一次性下载整个环境所有子文件夹")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"并发下载线程数（默认 {DEFAULT_WORKERS}）")
    args = parser.parse_args()

    if args.scan_only:
        scan_and_cache(args.env)
    elif args.from_cache:
        if not args.subfolder:
            parser.error("--from-cache 需要配合 --subfolder 使用")
        download_from_cache(args.env, args.subfolder, args.workers)
    elif args.all:
        download_all_subfolders(args.env, args.workers)
    elif args.subfolder:
        download_subfolder(args.env, args.subfolder, args.workers)
    else:
        parser.error("请指定 --subfolder、--all 或 --scan-only")


if __name__ == "__main__":
    main()
