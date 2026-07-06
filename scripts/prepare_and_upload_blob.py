"""
prepare_and_upload_blob.py
==========================
准备数据并上传到 Azure Blob。

步骤：
1. 删除空标注 JSONL 对应的子文件夹数据和图片
2. 调整标注 JSONL 中的 image 路径，加上 blob 前缀
3. 调用 azcopy 上传

用法:
    python scripts/prepare_and_upload_blob.py --env env_ue_bigcity
    python scripts/prepare_and_upload_blob.py --env env_ue_bigcity --dry-run
"""

import os
import json
import shutil
import argparse
import subprocess
import glob

# 加载项目根目录的 .env 文件
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_script_dir)
_env_file = os.path.join(_project_dir, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                # 解析 export KEY="VALUE" 或 KEY="VALUE"
                line = line.removeprefix("export ")
                key, _, value = line.partition("=")
                value = value.strip('"').strip("'")
                os.environ.setdefault(key, value)

# ===================== 配置项 =====================
DATASET_BASE_DIR = "./openfly_to_airvln_data"
ANNOTATION_BASE_DIR = "./openfly_to_airvln_data/annotation"
BLOB_BASE_URL = "https://yifanyang.blob.core.windows.net/yifanyang"
BLOB_SAS_TOKEN = os.environ.get("BLOB_SAS_TOKEN", "")
BLOB_UPLOAD_PREFIX = "output/liyan/vln/openfly"  # blob 上传的实际路径前缀
IMAGE_PATH_PREFIX = "vln/openfly"  # 标注 JSONL 中的 image 路径前缀（训练时用）
# ==================================================


def step1_cleanup_empty(env, dry_run=False):
    """删除空标注 JSONL 对应的子文件夹数据。"""
    print(f"\n{'='*60}", flush=True)
    print(f" 步骤1: 清理空标注对应的数据", flush=True)
    print(f"{'='*60}\n", flush=True)

    annotation_dir = os.path.join(ANNOTATION_BASE_DIR, env)
    data_dir = os.path.join(DATASET_BASE_DIR, env)

    if not os.path.exists(annotation_dir):
        print(f"❌ 标注目录不存在: {annotation_dir}", flush=True)
        return

    empty_subfolders = []
    valid_subfolders = []

    for jsonl_file in sorted(glob.glob(os.path.join(annotation_dir, "*.jsonl"))):
        subfolder = os.path.basename(jsonl_file).replace(".jsonl", "")
        if os.path.getsize(jsonl_file) == 0:
            empty_subfolders.append(subfolder)
        else:
            valid_subfolders.append(subfolder)

    if empty_subfolders:
        print(f"  发现 {len(empty_subfolders)} 个空标注（不在 train.json 中）:", flush=True)
        for sf in empty_subfolders:
            sf_data_dir = os.path.join(data_dir, sf)
            sf_jsonl = os.path.join(annotation_dir, f"{sf}.jsonl")

            if os.path.exists(sf_data_dir):
                size = subprocess.run(["du", "-sh", sf_data_dir], capture_output=True, text=True).stdout.split()[0]
                if dry_run:
                    print(f"    [DRY-RUN] 将删除: {sf}/ ({size})", flush=True)
                else:
                    shutil.rmtree(sf_data_dir)
                    os.remove(sf_jsonl)
                    print(f"    ✅ 已删除: {sf}/ ({size}) + {sf}.jsonl", flush=True)
            else:
                # 数据目录已不存在，只删空 JSONL
                if not dry_run:
                    os.remove(sf_jsonl)
                print(f"    ✅ 已删除空标注: {sf}.jsonl（数据目录已不存在）", flush=True)
    else:
        print(f"  ✅ 没有空标注，无需清理", flush=True)

    print(f"\n  有效子文件夹: {len(valid_subfolders)} 个", flush=True)
    for sf in valid_subfolders:
        print(f"    • {sf}", flush=True)

    return valid_subfolders


def step2_fix_image_paths(env, dry_run=False):
    """调整标注 JSONL 中的 image 路径，加上 blob 前缀。

    当前路径: env_ue_bigcity/high_average/<traj_id>/images/xxx.png
    目标路径: vln/openfly/env_ue_bigcity/high_average/<traj_id>/images/xxx.png
    """
    print(f"\n{'='*60}", flush=True)
    print(f" 步骤2: 调整标注中的 image 路径", flush=True)
    print(f"{'='*60}\n", flush=True)

    annotation_dir = os.path.join(ANNOTATION_BASE_DIR, env)
    prefix = IMAGE_PATH_PREFIX  # "vln/openfly"

    jsonl_files = sorted(glob.glob(os.path.join(annotation_dir, "*.jsonl")))
    jsonl_files = [f for f in jsonl_files if os.path.getsize(f) > 0]

    for jsonl_path in jsonl_files:
        subfolder = os.path.basename(jsonl_path).replace(".jsonl", "")

        # 读取全部行
        rows = []
        with open(jsonl_path, 'r') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))

        # 检查是否已经有前缀（避免重复处理）
        if rows and rows[0].get("image") and rows[0]["image"][0].startswith(prefix):
            print(f"  ⏭️  {subfolder}.jsonl 已有正确前缀，跳过", flush=True)
            continue

        # 修改 image 路径
        for row in rows:
            row["image"] = [f"{prefix}/{img}" for img in row["image"]]

        if dry_run:
            print(f"  [DRY-RUN] {subfolder}.jsonl: {len(rows)} 行待修改", flush=True)
            if rows:
                print(f"    示例: {rows[0]['image'][0]}", flush=True)
        else:
            with open(jsonl_path, 'w') as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"  ✅ {subfolder}.jsonl: {len(rows)} 行已更新", flush=True)
            if rows:
                print(f"     示例: {rows[0]['image'][0]}", flush=True)


def step3_upload_blob(env, dry_run=False):
    """使用 azcopy 上传数据到 blob。"""
    print(f"\n{'='*60}", flush=True)
    print(f" 步骤3: 上传到 Azure Blob", flush=True)
    print(f"{'='*60}\n", flush=True)

    data_dir = os.path.join(DATASET_BASE_DIR, env)
    annotation_dir = os.path.join(ANNOTATION_BASE_DIR, env)

    # 拼接 SAS token
    sas = BLOB_SAS_TOKEN
    if not sas:
        print(f"❌ 未设置 BLOB_SAS_TOKEN 环境变量", flush=True)
        print(f"   请在 .env 中添加: export BLOB_SAS_TOKEN=\"...\"", flush=True)
        return False

    # 目标路径: vln/openfly/env_ue_bigcity/
    blob_data_target = f"{BLOB_BASE_URL}/{BLOB_UPLOAD_PREFIX}/{env}/?{sas}"
    blob_anno_target = f"{BLOB_BASE_URL}/{BLOB_UPLOAD_PREFIX}/annotation/{env}/?{sas}"

    # 上传数据目录（图片 + metadata）
    data_src = data_dir.rstrip("/") + "/*"
    print(f"  📤 上传数据: {data_dir}", flush=True)
    print(f"     → blob: {BLOB_UPLOAD_PREFIX}/{env}/", flush=True)
    if dry_run:
        print(f"  [DRY-RUN] 跳过实际上传", flush=True)
    else:
        result = subprocess.run(
            ["azcopy", "copy", data_src, blob_data_target, "--recursive=true"],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"  ❌ 数据上传失败", flush=True)
            return False

    # 上传标注文件
    anno_src = annotation_dir.rstrip("/") + "/*"
    print(f"\n  📤 上传标注: {annotation_dir}", flush=True)
    print(f"     → blob: {BLOB_UPLOAD_PREFIX}/annotation/{env}/", flush=True)
    if dry_run:
        print(f"  [DRY-RUN] 跳过实际上传", flush=True)
    else:
        result = subprocess.run(
            ["azcopy", "copy", anno_src, blob_anno_target, "--recursive=true"],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"  ❌ 标注上传失败", flush=True)
            return False

    print(f"\n  ✅ 上传完成!", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="准备数据并上传到 Azure Blob")
    parser.add_argument("--env", required=True,
                        help="仿真环境名，如 env_ue_bigcity")
    parser.add_argument("--subfolder", default=None,
                        help="只处理指定子文件夹（集成到 pipeline 时使用）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只预览不实际执行")
    parser.add_argument("--skip-upload", action="store_true",
                        help="只做清理和路径修正，不上传")
    args = parser.parse_args()

    print(f"🚀 准备上传 {args.env} 到 Blob", flush=True)
    print(f"   Blob 目标: {BLOB_BASE_URL}/{BLOB_UPLOAD_PREFIX}/{args.env}/", flush=True)
    if args.subfolder:
        print(f"   子文件夹: {args.subfolder}", flush=True)
    if args.dry_run:
        print(f"   ⚠️  DRY-RUN 模式，不会实际修改或上传", flush=True)

    if args.subfolder:
        # 单个子文件夹模式
        _process_single_subfolder(args.env, args.subfolder, args.dry_run, args.skip_upload)
    else:
        # 整环境模式
        valid_subfolders = step1_cleanup_empty(args.env, dry_run=args.dry_run)
        step2_fix_image_paths(args.env, dry_run=args.dry_run)
        if not args.skip_upload:
            step3_upload_blob(args.env, dry_run=args.dry_run)
        else:
            print(f"\n  ⏭️  跳过上传（--skip-upload）", flush=True)

    print(f"\n{'='*60}", flush=True)
    print(f" 🎉 完成!", flush=True)
    print(f"{'='*60}", flush=True)


def _process_single_subfolder(env, subfolder, dry_run=False, skip_upload=False):
    """处理单个子文件夹：检查标注→修路径→上传。"""
    annotation_dir = os.path.join(ANNOTATION_BASE_DIR, env)
    jsonl_path = os.path.join(annotation_dir, f"{subfolder}.jsonl")
    data_dir = os.path.join(DATASET_BASE_DIR, env, subfolder)

    # 检查标注是否为空
    if not os.path.exists(jsonl_path):
        print(f"  ⚠️ 标注文件不存在: {jsonl_path}，跳过", flush=True)
        return
    if os.path.getsize(jsonl_path) == 0:
        print(f"  ⚠️ 标注为空（不在 train.json 中），删除数据并跳过", flush=True)
        if not dry_run:
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
            os.remove(jsonl_path)
        return

    # 修正 image 路径
    prefix = IMAGE_PATH_PREFIX
    rows = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    if rows and rows[0].get("image") and not rows[0]["image"][0].startswith(prefix):
        for row in rows:
            row["image"] = [f"{prefix}/{img}" for img in row["image"]]
        if not dry_run:
            with open(jsonl_path, 'w') as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  ✅ {subfolder}.jsonl: {len(rows)} 行路径已更新", flush=True)
    else:
        print(f"  ⏭️ {subfolder}.jsonl 路径已正确", flush=True)

    # 上传
    if skip_upload:
        print(f"  ⏭️ 跳过上传（--skip-upload）", flush=True)
        return

    sas = BLOB_SAS_TOKEN
    if not sas:
        print(f"  ❌ 未设置 BLOB_SAS_TOKEN，无法上传", flush=True)
        return

    # 上传数据
    blob_data_target = f"{BLOB_BASE_URL}/{BLOB_UPLOAD_PREFIX}/{env}/{subfolder}/?{sas}"
    data_src = data_dir.rstrip("/") + "/*"
    print(f"  📤 上传: {subfolder}/", flush=True)
    if not dry_run:
        result = subprocess.run(
            ["azcopy", "copy", data_src, blob_data_target, "--recursive=true"],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"  ❌ 数据上传失败", flush=True)
            return

    # 上传标注
    blob_anno_target = f"{BLOB_BASE_URL}/{BLOB_UPLOAD_PREFIX}/annotation/{env}/{subfolder}.jsonl?{sas}"
    print(f"  📤 上传: annotation/{env}/{subfolder}.jsonl", flush=True)
    if not dry_run:
        result = subprocess.run(
            ["azcopy", "copy", jsonl_path, blob_anno_target],
            capture_output=False
        )
        if result.returncode != 0:
            print(f"  ❌ 标注上传失败", flush=True)
            return

    print(f"  ✅ 上传完成", flush=True)


if __name__ == "__main__":
    main()
