#!/bin/bash
# =============================================================================
# run_pipeline.sh
# =============================================================================
# 自动化执行 OpenFly → AirVLN 数据转换6阶段流水线

# 加载环境变量（HF_TOKEN）
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_DIR="$(dirname "$_SCRIPT_DIR")"
[ -f "$_PROJECT_DIR/.env" ] && source "$_PROJECT_DIR/.env"
#
# 用法:
#   bash scripts/run_pipeline.sh <env> <subfolder>
#   bash scripts/run_pipeline.sh <subfolder>          # env 默认 env_ue_bigcity
#
# 示例:
#   bash scripts/run_pipeline.sh env_ue_bigcity high_average
#   bash scripts/run_pipeline.sh env_airsim_16 low_long
#   bash scripts/run_pipeline.sh high_average          # 等价于 env_ue_bigcity high_average
#
# 可用仿真环境:
#   env_ue_bigcity, env_ue_smallcity,
#   env_airsim_16, env_airsim_18, env_airsim_23, env_airsim_26,
#   env_airsim_gz, env_airsim_sh,
#   env_game_gtav,
#   env_gs_ecust, env_gs_nwpu01, env_gs_nwpu02, env_gs_sjtu01, env_gs_sjtu02
#
# 可选轨迹类型:
#   high_average, high_long, high_short,
#   low_average, low_average_updown, low_long, low_long_updown,
#   low_short, low_short_updown,
#   medium_average, medium_average_updown, medium_long, medium_long_updown,
#   medium_short, medium_short_updown
# =============================================================================

set -e  # 任何阶段失败立即停止

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# 参数解析
# =============================================================================
DEFAULT_ENV="env_ue_bigcity"

if [ -z "$1" ]; then
    echo -e "${RED}❌ 错误: 请提供参数${NC}"
    echo ""
    echo "用法:"
    echo "  bash scripts/run_pipeline.sh <env> <subfolder>"
    echo "  bash scripts/run_pipeline.sh <subfolder>        # env 默认 ${DEFAULT_ENV}"
    echo ""
    echo "示例:"
    echo "  bash scripts/run_pipeline.sh env_ue_bigcity high_average"
    echo "  bash scripts/run_pipeline.sh env_airsim_16 low_long"
    echo "  bash scripts/run_pipeline.sh high_average"
    exit 1
fi

# 智能参数解析: 如果只有1个参数，视为 subfolder（兼容旧用法）
# 支持环境变量 SKIP_DOWNLOAD=1 跳过下载阶段
if [ -z "$2" ]; then
    ENV="$DEFAULT_ENV"
    SUBFOLDER="$1"
else
    ENV="$1"
    SUBFOLDER="$2"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 切换到项目根目录
cd "$PROJECT_DIR"

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE} OpenFly → AirVLN 数据转换流水线${NC}"
echo -e "${BLUE} 环境:     ${YELLOW}${ENV}${NC}"
echo -e "${BLUE} 轨迹类型: ${YELLOW}${SUBFOLDER}${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# =============================================================================
# 阶段1: 下载 parquet 数据
# =============================================================================
if [ "${SKIP_DOWNLOAD}" = "1" ]; then
    echo -e "${YELLOW} [阶段 1/8] 下载 parquet 数据 — 已跳过（SKIP_DOWNLOAD=1）${NC}"
elif [ "${USE_CACHE}" = "1" ]; then
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW} [阶段 1/8] 下载 parquet 数据（从缓存列表）${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    python scripts/download_parquet.py --env "$ENV" --subfolder "$SUBFOLDER" --from-cache

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 阶段1完成: parquet 数据下载成功${NC}"
    else
        echo -e "${RED}❌ 阶段1失败: parquet 数据下载出错，终止流水线${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW} [阶段 1/8] 下载 parquet 数据${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    python scripts/download_parquet.py --env "$ENV" --subfolder "$SUBFOLDER"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 阶段1完成: parquet 数据下载成功${NC}"
    else
        echo -e "${RED}❌ 阶段1失败: parquet 数据下载出错，终止流水线${NC}"
        exit 1
    fi
fi
echo ""

# =============================================================================
# 阶段2: 解压 parquet 数据
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 2/8] 解压 parquet 数据 (16线程)${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/batch_restore.py --env "$ENV" --subfolder "$SUBFOLDER"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段2完成: parquet 解压成功${NC}"
else
    echo -e "${RED}❌ 阶段2失败: parquet 解压出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 阶段3: 转换 metadata 为 AirVLN 标注格式
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 3/8] 转换 metadata → AirVLN annotation${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

RESTORED_ROOT="./openfly_to_airvln_data/${ENV}/${SUBFOLDER}"
TRAIN_JSON="./openfly_to_airvln_data/train.json"
ANNOTATION_DIR="./openfly_to_airvln_data/annotation/${ENV}"
OUTPUT_JSONL="${ANNOTATION_DIR}/${SUBFOLDER}.jsonl"

# 确保 annotation 目录存在
mkdir -p "$ANNOTATION_DIR"

python scripts/convert_metadata_to_airvln.py \
    --restored_root "$RESTORED_ROOT" \
    --train_json "$TRAIN_JSON" \
    --output "$OUTPUT_JSONL" \
    --overwrite \
    --continue_on_error

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段3完成: annotation 生成成功 → ${OUTPUT_JSONL}${NC}"
else
    echo -e "${RED}❌ 阶段3失败: annotation 生成出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 阶段4: 修正 metadata.json 路径斜杠
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 4/8] 修正 metadata.json 路径斜杠${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/fix_slashes.py --env "$ENV" --subfolder "$SUBFOLDER"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段4完成: 路径斜杠修正成功${NC}"
else
    echo -e "${RED}❌ 阶段4失败: 路径斜杠修正出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 阶段5: 清理未引用的图片帧
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 5/8] 清理未引用的图片帧${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/cleanup_unused_frames.py --env "$ENV" --subfolder "$SUBFOLDER"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段5完成: 未引用帧清理成功${NC}"
else
    echo -e "${RED}❌ 阶段5失败: 未引用帧清理出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 阶段6: 清理中间 parquet 文件
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 6/8] 清理中间 parquet 文件${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/cleanup_parquet.py --env "$ENV" --subfolder "$SUBFOLDER"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段6完成: parquet 中间文件已清理${NC}"
else
    echo -e "${RED}❌ 阶段6失败: parquet 清理出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 阶段7: 清洗 + 上传到 Azure Blob
# =============================================================================
if [ "${SKIP_UPLOAD}" = "1" ]; then
    echo -e "${YELLOW} [阶段 7/8] 上传 Blob — 已跳过（SKIP_UPLOAD=1）${NC}"
else
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW} [阶段 7/8] 清洗 + 上传到 Azure Blob${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    python scripts/prepare_and_upload_blob.py --env "$ENV" --subfolder "$SUBFOLDER"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 阶段7完成: 数据已上传到 Blob${NC}"
    else
        echo -e "${RED}❌ 阶段7失败: 上传出错，终止流水线${NC}"
        exit 1
    fi
fi
echo ""

# =============================================================================
# 阶段8: 删除本地图片数据（已上传到 blob，释放空间）
# =============================================================================
if [ "${SKIP_UPLOAD}" = "1" ]; then
    echo -e "${YELLOW} [阶段 8/8] 删除本地数据 — 已跳过（SKIP_UPLOAD=1）${NC}"
else
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW} [阶段 8/8] 删除本地图片数据（已上传至 Blob）${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    LOCAL_DATA_DIR="./openfly_to_airvln_data/${ENV}/${SUBFOLDER}"
    if [ -d "$LOCAL_DATA_DIR" ]; then
        DATA_SIZE=$(du -sh "$LOCAL_DATA_DIR" 2>/dev/null | cut -f1)
        rm -rf "$LOCAL_DATA_DIR"
        echo -e "${GREEN}✅ 阶段8完成: 已删除本地数据 ${LOCAL_DATA_DIR} (${DATA_SIZE})${NC}"
    else
        echo -e "${GREEN}✅ 阶段8完成: 本地数据已不存在${NC}"
    fi
fi
echo ""

# =============================================================================
# 完成
# =============================================================================
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN} 🎉 全部完成！${NC}"
echo -e "${GREEN} 环境: ${ENV} | 轨迹类型: ${SUBFOLDER}${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "  📁 解压数据:     ./openfly_to_airvln_data/${ENV}/${SUBFOLDER}/"
echo -e "  📄 标注文件:     ${OUTPUT_JSONL}"
echo ""
echo -e "${YELLOW}💡 提示: 请检查内存使用情况后再运行下一个子文件夹${NC}"
echo -e "  使用 'free -h' 或 'htop' 查看内存状态"
