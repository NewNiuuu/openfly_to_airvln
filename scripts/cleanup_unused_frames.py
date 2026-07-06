"""
cleanup_unused_frames.py
========================
删除标注 JSONL 中未被引用的图片帧。

由于 step=4 抽帧逻辑，每4帧只取第1帧作为输入，约3/4的图片帧在标注中
未被引用。本脚本解析生成的 annotation JSONL，收集所有被引用的图片路径，
然后删除对应子文件夹 images/ 目录下未被引用的帧。

用法:
    python scripts/cleanup_unused_frames.py --subfolder high_average
    python scripts/cleanup_unused_frames.py --subfolder high_average --dry-run
"""

import os
import json
import glob
import argparse

# ===================== 配置项 =====================
DATASET_BASE_DIR = "./openfly_to_airvln_data"
ANNOTATION_DIR = "./openfly_to_airvln_data/annotation"
DEFAULT_ENV = "env_ue_bigcity"
# ==================================================


def collect_referenced_images(jsonl_path):
    """从 annotation JSONL 中提取所有被引用的图片相对路径。

    JSONL 每行的 "image" 字段是一个列表，每项形如:
        "<env_id>/<traj_id>/images/xxx.png"

    返回: dict[traj_id] -> set(filename)，只保留文件名部分用于匹配。
    """
    referenced = {}  # traj_id -> set of image filenames

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for img_path in row.get("image", []):
                # img_path 形如: "env_ue_bigcity/astar_data/high_average/<traj_id>/images/xxx.png"
                # 或: "<env_id>/<traj_id>/images/xxx.png"
                parts = img_path.replace("\\", "/").split("/")
                # 找到 "images" 的位置，往前一位是 traj_id，往后是文件名
                if "images" in parts:
                    img_idx = parts.index("images")
                    traj_id = parts[img_idx - 1]
                    filename = "/".join(parts[img_idx:])  # "images/xxx.png"
                    if traj_id not in referenced:
                        referenced[traj_id] = set()
                    referenced[traj_id].add(filename)

    return referenced


def cleanup_unused_frames(env, subfolder, dry_run=False):
    """删除指定环境+子文件夹中未被标注引用的图片帧。"""

    jsonl_path = os.path.join(ANNOTATION_DIR, env, f"{subfolder}.jsonl")
    dataset_dir = os.path.join(DATASET_BASE_DIR, env, subfolder)

    if not os.path.exists(jsonl_path):
        print(f"❌ 标注文件不存在: {jsonl_path}")
        print("   请确保阶段3（转标注）已完成。")
        exit(1)

    if not os.path.exists(dataset_dir):
        print(f"❌ 数据目录不存在: {dataset_dir}")
        exit(1)

    # 1. 收集所有被引用的图片
    print(f"📖 解析标注文件: {jsonl_path}")
    referenced = collect_referenced_images(jsonl_path)
    total_referenced = sum(len(v) for v in referenced.values())
    print(f"   → 共 {len(referenced)} 条轨迹, {total_referenced} 张被引用的图片")

    # 2. 遍历所有轨迹目录，找出未引用的帧
    traj_dirs = glob.glob(os.path.join(dataset_dir, "*/images"))
    total_deleted = 0
    total_kept = 0
    total_skipped_trajs = 0

    for img_dir in sorted(traj_dirs):
        traj_dir = os.path.dirname(img_dir)
        traj_id = os.path.basename(traj_dir)

        if traj_id not in referenced:
            # 该轨迹完全不在标注中（可能因错误被跳过），保留不动
            total_skipped_trajs += 1
            continue

        ref_set = referenced[traj_id]

        # 列出 images/ 下所有文件
        for fname in os.listdir(img_dir):
            rel_path = f"images/{fname}"
            if rel_path in ref_set:
                total_kept += 1
            else:
                full_path = os.path.join(img_dir, fname)
                if dry_run:
                    total_deleted += 1
                else:
                    os.remove(full_path)
                    total_deleted += 1

    # 3. 输出统计
    action = "将删除" if dry_run else "已删除"
    print(f"\n📊 清理统计:")
    print(f"   保留: {total_kept} 张 (标注引用)")
    print(f"   {action}: {total_deleted} 张 (未引用)")
    print(f"   跳过轨迹: {total_skipped_trajs} 条 (不在标注中)")

    if dry_run:
        print(f"\n⚠️  DRY-RUN 模式，未实际删除任何文件。去掉 --dry-run 参数执行真正清理。")
    else:
        if total_deleted > 0:
            print(f"\n✅ 清理完成！释放了约 {total_deleted} 张未引用帧。")
        else:
            print(f"\n✅ 没有需要清理的未引用帧。")


def main():
    parser = argparse.ArgumentParser(description="删除标注中未被引用的图片帧")
    parser.add_argument("--env", default=DEFAULT_ENV,
                        help=f"仿真环境名，如 env_ue_bigcity, env_airsim_16 等（默认 {DEFAULT_ENV}）")
    parser.add_argument("--subfolder", required=True,
                        help="轨迹类型，如 high_average, high_long 等")
    parser.add_argument("--dry-run", action="store_true",
                        help="只统计不实际删除（预览模式）")
    args = parser.parse_args()

    cleanup_unused_frames(args.env, args.subfolder, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
