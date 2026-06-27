#!/bin/bash
# =============================================================================
# run_pipeline.sh
# =============================================================================
# 自动化执行 OpenFly → AirVLN 数据转换4阶段流水线
#
# 用法:
#   bash scripts/run_pipeline.sh <subfolder>
#
# 示例:
#   bash scripts/run_pipeline.sh high_average
#   bash scripts/run_pipeline.sh low_long
#
# 可选子文件夹:
#   high_average, high_long, high_short,
#   low_average, low_average_updown, low_long, low_long_updown,
#   low_short, low_short_updown,
#   medium_average_updown, medium_long_updown, medium_short_updown
# =============================================================================

set -e  # 任何阶段失败立即停止

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# 参数检查
# =============================================================================
if [ -z "$1" ]; then
    echo -e "${RED}❌ 错误: 请提供子文件夹名作为参数${NC}"
    echo ""
    echo "用法: bash scripts/run_pipeline.sh <subfolder>"
    echo ""
    echo "可选子文件夹:"
    echo "  high_average, high_long, high_short,"
    echo "  low_average, low_average_updown, low_long, low_long_updown,"
    echo "  low_short, low_short_updown,"
    echo "  medium_average_updown, medium_long_updown, medium_short_updown"
    exit 1
fi

SUBFOLDER="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 切换到项目根目录
cd "$PROJECT_DIR"

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE} OpenFly → AirVLN 数据转换流水线${NC}"
echo -e "${BLUE} 子文件夹: ${YELLOW}${SUBFOLDER}${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# =============================================================================
# 阶段1: 下载 parquet 数据
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 1/4] 下载 parquet 数据${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/download_parquet.py --subfolder "$SUBFOLDER"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段1完成: parquet 数据下载成功${NC}"
else
    echo -e "${RED}❌ 阶段1失败: parquet 数据下载出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 阶段2: 解压 parquet 数据
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [阶段 2/4] 解压 parquet 数据 (16线程)${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/batch_restore.py --subfolder "$SUBFOLDER"

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
echo -e "${YELLOW} [阶段 3/4] 转换 metadata → AirVLN annotation${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

RESTORED_ROOT="./openfly_to_airvln_data/${SUBFOLDER}"
TRAIN_JSON="./openfly_to_airvln_data/train.json"
ANNOTATION_DIR="./openfly_to_airvln_data/annotation"
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
echo -e "${YELLOW} [阶段 4/4] 修正 metadata.json 路径斜杠${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

python scripts/fix_slashes.py --subfolder "$SUBFOLDER"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 阶段4完成: 路径斜杠修正成功${NC}"
else
    echo -e "${RED}❌ 阶段4失败: 路径斜杠修正出错，终止流水线${NC}"
    exit 1
fi
echo ""

# =============================================================================
# 完成
# =============================================================================
echo -e "${GREEN}=============================================${NC}"
echo -e "${GREEN} 🎉 全部完成！子文件夹: ${SUBFOLDER}${NC}"
echo -e "${GREEN}=============================================${NC}"
echo ""
echo -e "  📁 Parquet 数据: ./openfly_syn_parquet/env_ue_bigcity/astar_data/${SUBFOLDER}/"
echo -e "  📁 解压数据:     ./openfly_to_airvln_data/${SUBFOLDER}/"
echo -e "  📄 标注文件:     ${OUTPUT_JSONL}"
echo ""
echo -e "${YELLOW}💡 提示: 请检查内存使用情况后再运行下一个子文件夹${NC}"
echo -e "  使用 'free -h' 或 'htop' 查看内存状态"
