"""
fix_slashes.py
==============
修正 metadata.json 中的路径斜杠和文件名映射问题。

用法:
    python scripts/fix_slashes.py --subfolder high_average
"""

import os
import json
import glob
import argparse

# ===================== 配置项 =====================
DATASET_BASE_DIR = "./openfly_to_airvln_data"
DEFAULT_ENV = "env_ue_bigcity"
# ==================================================


def fix_metadata_paths(dataset_dir):
    if not os.path.exists(dataset_dir):
        print(f"❌ 找不到目录: {dataset_dir}", flush=True)
        exit(1)

    # 递归抓取所有的 metadata.json
    json_files = glob.glob(os.path.join(dataset_dir, "**/metadata.json"), recursive=True)
    total = len(json_files)
    print(f"🔍 找到 {total} 个 metadata.json 文件，开始纠正路径与名称...", flush=True)

    fixed_count = 0
    fail_count = 0

    for idx, json_path in enumerate(json_files, 1):
        traj_dir = os.path.dirname(json_path)
        img_dir = os.path.join(traj_dir, "images")

        # 1. 读取 JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception as e:
                fail_count += 1
                print(f"  [{idx}/{total}] ❌ 读取失败 {json_path}: {e}", flush=True)
                continue

        # 2. 盘点当前轨迹 images 目录下真实存在的物理图片
        img_map = {}
        if os.path.exists(img_dir):
            for fname in os.listdir(img_dir):
                if fname.endswith('.png'):
                    prefix = "_".join(fname.replace('.png', '').split('_')[:2])
                    img_map[prefix] = fname

        # 3. 修正字段
        for item in data:
            image_id = item.get("image_id")

            if image_id in img_map:
                item["image"] = f"images/{img_map[image_id]}"
            elif "image" in item:
                item["image"] = item["image"].replace("\\/", "/").replace("\\", "/")

            if "env_id" in item:
                item["env_id"] = item["env_id"].replace("\\/", "/").replace("\\", "/")

        # 4. 覆写回本地
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        fixed_count += 1
        # 每100个或最后一个打印进度
        if idx <= 3 or idx % 100 == 0 or idx == total:
            print(f"  [{idx}/{total}] ✅ 已修正: {os.path.basename(traj_dir)}", flush=True)

    print(f"\n🎉 路径修正完毕！成功: {fixed_count}, 失败: {fail_count}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="修正 metadata.json 中的路径斜杠问题")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"仿真环境名，如 env_ue_bigcity, env_airsim_16 等（默认 {DEFAULT_ENV}）")
    parser.add_argument("--subfolder", required=True,
                        help="轨迹类型，如 high_average, high_long 等")
    args = parser.parse_args()

    dataset_dir = os.path.join(DATASET_BASE_DIR, args.env, args.subfolder)
    fix_metadata_paths(dataset_dir)


if __name__ == "__main__":
    main()
