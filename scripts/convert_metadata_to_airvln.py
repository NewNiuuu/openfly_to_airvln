"""
convert_metadata_to_airvln.py
=============================
从 ``restored_dataset/<cat>/<traj_id>/metadata.json`` 目录组织形式直接转 AirVLN
格式 SFT 训练数据.

**自包含**: 本脚本不依赖任何上游模块, ACTION_MAP / PROMPT 模板 / chunks / build_row
等 helper 全部内联. 与原 ``convert_pose_dir_to_airvln.py`` 输出 100% 一致
(step=4 模式, 每 4 帧 = 1 turn).

目录结构 (restored_dataset):
    restored_dataset/
        <cat>/                           # 例如 high_average / high_long / ...
            <traj_id>/
                metadata.json            # 全量帧数组
                images/
                    20250104_015146.png
                    ...

train.json 匹配键:
    image_path == f"{env_id}/{traj_id}"
    其中 env_id 和 traj_id 都来自 metadata.json 的首条记录.
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 常量 (从 convert_pose_dir_to_airvln.py 内联)
# ---------------------------------------------------------------------------

HUMAN_TEMPLATES = [
    "you are toward the {image_token}",
    "you can spot {image_token}",
    "there is {image_token}",
    "ahead of you is {image_token}",
    "in front of you is {image_token}",
    "in your sight is {image_token}",
    "you can see {image_token}",
]

PROMPT_PREFIX = (
    "You are an autonomous navigation assistant. "
    "Your task is to {instruction}. "
    "Devise an action sequence to follow the instruction using the actions: "
    "<STOP>, <MOVE_FORWARD_3>, <MOVE_FORWARD_6>, <MOVE_FORWARD_9>, "
    "<TURN_LEFT_30>, <TURN_RIGHT_30>, <GO_UP_3>, <GO_DOWN_3>, "
    "<MOVE_LEFT_3>, <MOVE_RIGHT_3>."
)

PROMPT_CURR_ROW0 = "{prefix} This is your current view: {image_token}"
PROMPT_CURR_ROWN = (
    "{prefix} These are your historical observations: "
    "{history_tokens} This is your current view: {image_token}"
)
IMG_TOKEN = "<image>"

# manifest action_type + action_value → OpenFly 整数编码
ACTION_MAP = {
    ("stop", 0): 0,
    ("go straight", 3): 1,
    ("turn left", 30): 2,
    ("turn right", 30): 3,
    ("go up", 3): 4,
    ("go down", 3): 5,
    ("move left", 3): 6,
    ("move right", 3): 7,
    ("go straight", 6): 8,
    ("go straight", 9): 9,
}

INT_TO_TOKEN = {
    0: "<STOP>",
    1: "<MOVE_FORWARD_3>",
    2: "<TURN_LEFT_30>",
    3: "<TURN_RIGHT_30>",
    4: "<GO_UP_3>",
    5: "<GO_DOWN_3>",
    6: "<MOVE_LEFT_3>",
    7: "<MOVE_RIGHT_3>",
    8: "<MOVE_FORWARD_6>",
    9: "<MOVE_FORWARD_9>",
}

# step=4 模式: 每 turn 输入 1 帧, 预测 STEP 个 action (末 turn 可能 < STEP)
STEP = 4
MIN_FRAMES = STEP  # N < STEP 跳过
TURNS_PER_ROW = 8  # 一行最多 8 turn


# ---------------------------------------------------------------------------
# train.json 加载 (一次性, 高效)
# ---------------------------------------------------------------------------

def load_all_instructions(train_json_path):
    """一次性把 train.json 全部 instruction 加载为 dict, image_path → gpt_instruction.

    对 405 MB 的 train.json 也只读一次, O(N) 时间 O(N) 内存.
    """
    print(f"[train] 加载 {train_json_path} ...", flush=True)
    with open(train_json_path) as f:
        data = json.load(f)
    out = {}
    for d in data:
        ipath = d.get("image_path")
        if ipath:
            out[ipath] = d["gpt_instruction"]
    print(f"[train] → {len(out)} 条 instruction 索引", flush=True)
    return out


# ---------------------------------------------------------------------------
# step=4 切 turn + 单行构建 (内联自上游)
# ---------------------------------------------------------------------------

def chunks(frames, step=STEP):
    """把 frames 列表切成 turn 列表. 每个 turn = chunk of `step` frames (末 turn 可能 < step).

    turn 字典结构:
        {
          "input_frame": <chunk[0] 帧字典>,     # 提供 image / pos / yaw
          "action_ints": [a0, a1, ...],          # chunk 内每帧的 action_int
        }
    """
    out = []
    n = len(frames)
    for s in range(0, n, step):
        chunk = frames[s : s + step]
        out.append({
            "input_frame": chunk[0],
            "action_ints": [f["action_int"] for f in chunk],
        })
    return out


def actions_to_tokens(actions_int):
    return " ".join(INT_TO_TOKEN[a] for a in actions_int)


def build_row(env_id, traj_id, row_idx, turns, instruction,
              prev_history_imgs, prev_history_pos, prev_history_yaw,
              image_prefix, is_last_row=False):
    """构建一行 (一个 jsonl 行).

    Args:
        env_id: env_id
        traj_id: trajectory id
        row_idx: 行号 (0-indexed)
        turns: list[turn dict], 1 ≤ len(turns) ≤ TURNS_PER_ROW
        instruction: gpt_instruction
        prev_history_imgs/pos/yaw: 上一行的 history (row_idx=0 时为空)
        image_prefix: 图像路径前缀
        is_last_row: 是否是最后一行 (仅用于文档, 末帧 STOP 由调用方保证)
    """
    n_turns = len(turns)
    assert 1 <= n_turns <= TURNS_PER_ROW, f"n_turns={n_turns} 越界 [1, {TURNS_PER_ROW}]"

    # image / pos / yaw 列表: 每 turn 1 项, 取输入帧 (chunk[0]) 的值
    turn_imgs = [f"{image_prefix}/{t['input_frame']['saved_as']}" for t in turns]
    turn_pos = [t["input_frame"]["pos"] for t in turns]
    turn_yaw = [t["input_frame"]["yaw"] for t in turns]

    if row_idx == 0:
        image_list = turn_imgs
        pos_list = turn_pos
        yaw_list = turn_yaw
    else:
        assert len(prev_history_imgs) == TURNS_PER_ROW, (
            f"row {row_idx} 的 prev_history 长度 {len(prev_history_imgs)} ≠ {TURNS_PER_ROW}"
        )
        image_list = list(prev_history_imgs) + turn_imgs
        pos_list = list(prev_history_pos) + turn_pos
        yaw_list = list(prev_history_yaw) + turn_yaw

    prefix = PROMPT_PREFIX.format(instruction=instruction)
    convs = []

    if row_idx == 0:
        human0 = PROMPT_CURR_ROW0.format(prefix=prefix, image_token=IMG_TOKEN)
    else:
        history_imgs = "".join([IMG_TOKEN] * TURNS_PER_ROW)
        human0 = PROMPT_CURR_ROWN.format(
            prefix=prefix, history_tokens=history_imgs, image_token=IMG_TOKEN
        )
    convs.append({"from": "human", "value": human0})
    convs.append({"from": "gpt", "value": ""})

    for t in range(1, n_turns):
        template = HUMAN_TEMPLATES[(row_idx * TURNS_PER_ROW + t) % len(HUMAN_TEMPLATES)]
        convs.append({"from": "human", "value": template.format(image_token=IMG_TOKEN)})
        convs.append({"from": "gpt", "value": ""})

    # 填充 gpt 输出: 每 turn 输出 1-4 个 token (空格分隔)
    for t in range(n_turns):
        convs[2 * t + 1]["value"] = actions_to_tokens(turns[t]["action_ints"])

    return {
        "id": f"{env_id}#{traj_id}#row{row_idx:03d}",
        "data_source": env_id,
        "conversations": convs,
        "image": image_list,
        "pos": pos_list,
        "yaw": yaw_list,
    }


# ---------------------------------------------------------------------------
# metadata.json 解析
# ---------------------------------------------------------------------------

def parse_metadata(path):
    """读 metadata.json, 返回 list[dict] (按 frame_index 升序).

    期望每条记录至少含:
        env_id, traj_id, frame_index, image, pos, yaw, action_type, action_value

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 字段缺失 / 解析失败
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在")

    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: 期望非空 list, 实际 {type(data).__name__}")

    required = {"env_id", "traj_id", "frame_index", "image", "pos", "yaw",
                "action_type", "action_value"}
    missing = required - set(data[0].keys())
    if missing:
        raise ValueError(f"{path}: 缺少字段 {missing}")

    # 按 frame_index 排序, 防御写入顺序错乱
    data.sort(key=lambda d: d["frame_index"])
    return data


def build_frames_from_metadata(metadata_path, image_dir):
    """从 metadata.json + 图像目录构建 frame 列表.

    Args:
        metadata_path: metadata.json 路径
        image_dir: 图像所在目录 (用于校验所有 frame 的 image 文件都存在)

    Returns:
        frames list. saved_as 始终是非空字符串 (metadata 的 ``image`` 字段).

    Raises:
        FileNotFoundError: metadata.json 不存在
        ValueError: 字段缺失 / N < MIN_FRAMES / 末帧非 STOP
        KeyError: 出现未知的 (action_type, action_value) 组合
        RuntimeError: 任一 frame 的 image 文件在 image_dir 缺失
    """
    records = parse_metadata(metadata_path)
    image_dir = Path(image_dir)

    # 校验所有 image 文件确实存在于磁盘
    missing = []
    for r in records:
        img_path = image_dir / r["image"]
        if not img_path.exists():
            missing.append(r["image"])
    if missing:
        raise RuntimeError(
            f"{image_dir}: 缺少 {len(missing)} 张图像, 例如 {missing[:5]}"
        )

    frames = []
    for r in records:
        key = (r["action_type"], r["action_value"])
        if key not in ACTION_MAP:
            raise KeyError(
                f"未知 action_type/action_value: {key}, frame_index={r['frame_index']}"
            )
        frames.append({
            "frame_index": r["frame_index"],
            "pos": r["pos"],
            "yaw": r["yaw"],
            "action_int": ACTION_MAP[key],
            "saved_as": r["image"],
        })

    # N < STEP 跳过
    if len(frames) < MIN_FRAMES:
        raise ValueError(
            f"{metadata_path.parent.name}: N={len(frames)} < {MIN_FRAMES} (步长={STEP}), 跳过"
        )

    # 末帧必须 STOP
    if frames[-1]["action_int"] != 0:
        raise ValueError(
            f"{metadata_path.parent.name}: 最后一帧 action={frames[-1]['action_int']} "
            f"(应为 0=STOP)"
        )

    return frames


# ---------------------------------------------------------------------------
# 单 trajectory 处理
# ---------------------------------------------------------------------------

def convert_one_metadata_traj(metadata_path, instruction, output_path, image_prefix):
    """处理单个 metadata.json.

    Args:
        metadata_path: metadata.json 路径
        instruction: 提前查好的 gpt_instruction, 不在函数内读 train.json
        output_path: 输出 jsonl 路径 (追加模式)
        image_prefix: 图像路径前缀 (与 saved_as 拼成完整 image path)

    Returns:
        (env_id, traj_id, n_frames, n_rows)
    """
    metadata_path = Path(metadata_path).resolve()
    image_dir = metadata_path.parent  # metadata.json 所在目录 (含 images/)

    records = parse_metadata(metadata_path)
    head = records[0]
    env_id = head["env_id"]
    traj_id = head["traj_id"]

    if instruction is None:
        raise ValueError(
            f"instruction 为 None, 请确认 train.json 中存在 {env_id}/{traj_id}"
        )

    frames = build_frames_from_metadata(metadata_path, image_dir)

    # 切 turn: turn t = frames[t*STEP : t*STEP+STEP] (末 turn 可能 < STEP)
    turns = chunks(frames, step=STEP)
    n_turns = len(turns)
    n_rows = (n_turns + TURNS_PER_ROW - 1) // TURNS_PER_ROW

    prev_history_imgs, prev_history_pos, prev_history_yaw = [], [], []
    rows = []

    for r in range(n_rows):
        start = r * TURNS_PER_ROW
        end = min(start + TURNS_PER_ROW, n_turns)
        row_turns = turns[start:end]
        is_last = (r == n_rows - 1)

        row = build_row(
            env_id, traj_id, r, row_turns, instruction,
            prev_history_imgs, prev_history_pos, prev_history_yaw,
            image_prefix, is_last_row=is_last,
        )

        # history 滑动: 永远取最后 TURNS_PER_ROW 个 turn 的 input_frame
        history_turns = row_turns[-TURNS_PER_ROW:]
        prev_history_imgs = [
            f"{image_prefix}/{t['input_frame']['saved_as']}" for t in history_turns
        ]
        prev_history_pos = [t["input_frame"]["pos"] for t in history_turns]
        prev_history_yaw = [t["input_frame"]["yaw"] for t in history_turns]

        rows.append(row)

    with open(output_path, "a") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return env_id, traj_id, len(frames), len(rows)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def default_image_prefix(env_id, traj_id):
    """基于 env_id/traj_id 推导 image_prefix.

    metadata 中 env_id 形如: env_ue_bigcity/astar_data/high_average
    实际存储路径为:           env_ue_bigcity/high_average/<traj_id>/images/xxx.png

    去掉中间的 astar_data 层级，使标注路径与磁盘存储一致。
    """
    # env_id = "env_ue_bigcity/astar_data/high_average"
    # 去掉 astar_data → "env_ue_bigcity/high_average"
    parts = env_id.replace("\\", "/").split("/")
    cleaned_parts = [p for p in parts if p != "astar_data"]
    return "/".join(cleaned_parts) + "/" + traj_id


def iter_metadata_files(root):
    """rglob 找 root 下所有 metadata.json, 排序后返回 Path 列表."""
    root = Path(root).resolve()
    return sorted(root.rglob("metadata.json"))


def main():
    parser = argparse.ArgumentParser(
        description="metadata.json 目录组织 → AirVLN 格式 (无 parquet/pose.jsonl 依赖, "
                    "自包含, 不依赖上游 convert_pose_dir_to_airvln)"
    )
    parser.add_argument("--restored_root", required=True,
                        help="restored_dataset 根目录, 内部递归找所有 metadata.json")
    parser.add_argument("--train_json", required=True,
                        help="train.json 路径, 用于查 gpt_instruction (按 image_path 匹配)")
    parser.add_argument("--output", required=True, help="输出 jsonl")
    parser.add_argument("--image_prefix", default=None,
                        help="图像路径前缀, 默认 <env_id>/<traj_id>")
    parser.add_argument("--overwrite", action="store_true", help="覆盖输出文件")
    parser.add_argument("--continue_on_error", action="store_true",
                        help="单 trajectory 失败时打印错误并继续, 而非中断")
    parser.add_argument("--limit", type=int, default=None,
                        help="只处理前 N 个 metadata.json (调试用)")
    args = parser.parse_args()

    if args.overwrite:
        Path(args.output).write_text("")

    # 一次性加载 train.json
    instruction_map = load_all_instructions(args.train_json)

    # 找所有 metadata.json
    metadata_files = iter_metadata_files(args.restored_root)
    if args.limit:
        metadata_files = metadata_files[:args.limit]
    print(f"[scan] 在 {args.restored_root} 下找到 {len(metadata_files)} 个 metadata.json",
          flush=True)

    total_rows = 0
    total_trajs = 0
    n_errors = 0
    err_breakdown = {
        "skip_no_instruction": 0,
        "skip_short": 0,
        "skip_no_stop": 0,
        "skip_missing_image": 0,
        "skip_unknown_action": 0,
        "skip_other": 0,
    }

    for mp in metadata_files:
        # 从 metadata 提前读 env_id / traj_id (用于错误日志 + image_prefix 计算)
        try:
            head = parse_metadata(mp)[0]
        except (FileNotFoundError, ValueError) as e:
            n_errors += 1
            err_breakdown["skip_other"] += 1
            print(f"  ❌ {mp}: {e}", file=sys.stderr, flush=True)
            if not args.continue_on_error:
                raise
            continue

        env_id = head["env_id"]
        traj_id = head["traj_id"]

        # image_prefix 优先级: 命令行 > 默认 (<env_id>/<traj_id>)
        image_prefix = args.image_prefix if args.image_prefix else default_image_prefix(env_id, traj_id)

        # O(1) 查 instruction
        instruction = instruction_map.get(f"{env_id}/{traj_id}")

        try:
            real_env_id, real_traj_id, n_frames, n_rows = convert_one_metadata_traj(
                mp, instruction, args.output, image_prefix
            )
            print(f"  ✅ {real_env_id}/{real_traj_id}: {n_frames} 帧 → {n_rows} 行",
                  flush=True)
            total_rows += n_rows
            total_trajs += 1
        except (FileNotFoundError, ValueError, RuntimeError, KeyError) as e:
            n_errors += 1
            msg = f"  ❌ {env_id}/{traj_id}: {e}"
            # 错误分类
            if isinstance(e, ValueError) and "instruction 为 None" in str(e):
                err_breakdown["skip_no_instruction"] += 1
            elif isinstance(e, ValueError) and "<" in str(e) and "步长=" in str(e):
                err_breakdown["skip_short"] += 1
            elif isinstance(e, ValueError) and "0=STOP" in str(e):
                err_breakdown["skip_no_stop"] += 1
            elif isinstance(e, RuntimeError):
                err_breakdown["skip_missing_image"] += 1
            elif isinstance(e, KeyError):
                err_breakdown["skip_unknown_action"] += 1
            else:
                err_breakdown["skip_other"] += 1

            if args.continue_on_error:
                print(msg, flush=True)
            else:
                print(msg, file=sys.stderr, flush=True)
                raise

    print(
        f"\n=== 总计 {total_trajs} trajectory / {total_rows} 行, 错误 {n_errors} → {args.output} ===",
        flush=True,
    )
    if n_errors:
        print(f"[err_breakdown] {err_breakdown}", flush=True)


if __name__ == "__main__":
    main()
