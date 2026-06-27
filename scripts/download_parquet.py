"""
download_parquet.py
===================
从 huggingface 镜像站下载指定子文件夹的 parquet 文件到本地。

用法:
    python scripts/download_parquet.py --subfolder high_average
"""

import os
import argparse
import requests

# ===================== 配置项 =====================
REPO_ID = "IPEC-COMMUNITY/OpenFly"
BASE_FOLDER = "traj/env_ue_bigcity/astar_data"
LOCAL_BASE_DIR = "./openfly_syn_parquet/env_ue_bigcity/astar_data"
TOKEN = os.environ.get("HF_TOKEN", "")
MIRROR_URL = "https://hf-mirror.com"
# ==================================================


def download_subfolder(subfolder):
    folder_path = f"{BASE_FOLDER}/{subfolder}"
    local_dir = os.path.join(LOCAL_BASE_DIR, subfolder)

    # 确保下载文件夹存在
    os.makedirs(local_dir, exist_ok=True)

    print(f"🔍 正在通过 tunnel 获取文件清单: {folder_path} ...")
    api_url = f"{MIRROR_URL}/api/datasets/{REPO_ID}/tree/main/{folder_path}"
    headers = {"Authorization": f"Bearer {TOKEN}"}

    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        print(f"❌ 获取目录失败: {response.status_code} - {response.text}")
        exit(1)

    parquet_files = [
        f['path'] for f in response.json()
        if f.get('type') == 'file' and f['path'].endswith('.parquet')
    ]
    print(f"✅ 成功锁定 {len(parquet_files)} 个 Parquet 文件！开始下载：\n")

    success_count = 0
    fail_count = 0

    for file_path in parquet_files:
        file_name = file_path.split('/')[-1]
        save_path = os.path.join(local_dir, file_name)

        # 断点续传：如果文件已存在且有大小，直接跳过
        if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
            print(f"⏭️ 已存在，跳过: {file_name}")
            success_count += 1
            continue

        # 拼装真实的数据流物理下载地址
        download_url = f"{MIRROR_URL}/datasets/{REPO_ID}/resolve/main/{file_path}"
        print(f"⬇️ 正在下载: {file_name} ...", end="", flush=True)

        try:
            with requests.get(download_url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(" ✅ 成功！")
            success_count += 1
        except Exception as e:
            print(f" ❌ 失败: {e}")
            fail_count += 1

    print(f"\n🎉 下载完成！成功: {success_count}, 失败: {fail_count}")
    if fail_count > 0:
        exit(1)


def main():
    parser = argparse.ArgumentParser(description="下载 OpenFly parquet 数据")
    parser.add_argument("--subfolder", required=True,
                        help="子文件夹名，如 high_average, high_long 等")
    args = parser.parse_args()
    download_subfolder(args.subfolder)


if __name__ == "__main__":
    main()
