#!/bin/bash
# =============================================================================
# run_all_subfolders.sh
# =============================================================================
# 对指定仿真环境下的所有轨迹类型依次执行完整6阶段流水线，最后输出汇总报告。
#
# 用法:
#   bash scripts/run_all_subfolders.sh <env>
#   bash scripts/run_all_subfolders.sh               # env 默认 env_ue_bigcity
#
# 示例:
#   bash scripts/run_all_subfolders.sh env_ue_bigcity
#   bash scripts/run_all_subfolders.sh env_airsim_16
# =============================================================================

set -o pipefail  # 管道中任何命令失败都会被捕获

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================================================================
# 配置
# =============================================================================
DEFAULT_ENV="env_ue_bigcity"

# 所有轨迹类型（按顺序处理）
ALL_SUBFOLDERS=(
    "high_average"
    "high_long"
    "high_short"
    "low_average"
    "low_average_updown"
    "low_long"
    "low_long_updown"
    "low_short"
    "low_short_updown"
    "medium_average_updown"
    "medium_long_updown"
    "medium_short_updown"
)

# =============================================================================
# 参数解析
# =============================================================================
ENV="${1:-$DEFAULT_ENV}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

TOTAL=${#ALL_SUBFOLDERS[@]}
START_TIME=$(date +%s)
START_TIME_STR=$(date '+%Y-%m-%d %H:%M:%S')

# 报告文件
REPORT_FILE="./openfly_to_airvln_data/report_${ENV}_$(date '+%Y%m%d_%H%M%S').txt"
mkdir -p ./openfly_to_airvln_data

# =============================================================================
# 状态追踪
# =============================================================================
declare -a STATUS_LIST    # success / failed / skipped
declare -a DETAIL_LIST    # 详细信息

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  OpenFly → AirVLN 批量处理                               ║${NC}"
echo -e "${BLUE}║  环境: ${YELLOW}${ENV}${BLUE}                                          ║${NC}"
echo -e "${BLUE}║  轨迹类型: ${YELLOW}${TOTAL}${BLUE} 个                                        ║${NC}"
echo -e "${BLUE}║  开始时间: ${YELLOW}${START_TIME_STR}${BLUE}                       ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# 阶段0: 一次性下载整个环境的全部 parquet 文件
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW} [预下载] 一次性扫描并下载 ${ENV} 下所有 parquet 文件${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

python scripts/download_parquet.py --env "$ENV" --all

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 下载阶段失败，终止批量处理${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 全部 parquet 文件下载完成${NC}"
echo ""

# =============================================================================
# 逐个处理（阶段2-6，跳过下载）
# =============================================================================
for i in "${!ALL_SUBFOLDERS[@]}"; do
    SUBFOLDER="${ALL_SUBFOLDERS[$i]}"
    IDX=$((i + 1))

    echo -e "${CYAN}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "${CYAN}│ [${IDX}/${TOTAL}] 处理: ${YELLOW}${ENV}/${SUBFOLDER}${CYAN}${NC}"
    echo -e "${CYAN}└─────────────────────────────────────────────────────────┘${NC}"

    SUB_START=$(date +%s)

    # 调用单个子文件夹的 pipeline（跳过下载，已在预下载阶段完成），输出实时显示
    LOG_FILE="/tmp/openfly_pipeline_${ENV}_${SUBFOLDER}.log"
    SKIP_DOWNLOAD=1 bash scripts/run_pipeline.sh "$ENV" "$SUBFOLDER" 2>&1 | tee "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}

    SUB_END=$(date +%s)
    SUB_DURATION=$((SUB_END - SUB_START))
    SUB_MIN=$((SUB_DURATION / 60))
    SUB_SEC=$((SUB_DURATION % 60))

    if [ $EXIT_CODE -eq 0 ]; then
        STATUS_LIST[$i]="success"
        DETAIL_LIST[$i]="耗时 ${SUB_MIN}m${SUB_SEC}s"
        echo -e "${GREEN}  ✅ [${IDX}/${TOTAL}] ${SUBFOLDER} 成功 (${SUB_MIN}m${SUB_SEC}s)${NC}"
    else
        # 检查是否是因为 train.json 中没有对应数据
        if grep -q "instruction 为 None\|总计 0 trajectory" "$LOG_FILE"; then
            STATUS_LIST[$i]="skipped"
            DETAIL_LIST[$i]="不在 train.json 中"
            echo -e "${YELLOW}  ⏭️  [${IDX}/${TOTAL}] ${SUBFOLDER} 跳过 — 不在 train.json 中 (${SUB_MIN}m${SUB_SEC}s)${NC}"
        else
            STATUS_LIST[$i]="failed"
            # 提取最后一行错误信息
            LAST_ERR=$(grep -E "❌|Error|error|失败" "$LOG_FILE" | tail -1)
            DETAIL_LIST[$i]="失败: ${LAST_ERR:-未知错误}"
            echo -e "${RED}  ❌ [${IDX}/${TOTAL}] ${SUBFOLDER} 失败 (${SUB_MIN}m${SUB_SEC}s)${NC}"
            echo -e "${RED}     ${LAST_ERR:-查看日志获取详情}${NC}"
        fi
    fi
    rm -f "$LOG_FILE"
    echo ""

    # 子文件夹之间冷却 3 秒，避免连续请求触发 HF API 限流
    if [ $IDX -lt $TOTAL ]; then
        sleep 3
    fi
done

# =============================================================================
# 汇总统计
# =============================================================================
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))
TOTAL_MIN=$((TOTAL_DURATION / 60))
TOTAL_SEC=$((TOTAL_DURATION % 60))
TOTAL_HOUR=$((TOTAL_MIN / 60))
TOTAL_MIN=$((TOTAL_MIN % 60))

SUCCESS_COUNT=0
FAILED_COUNT=0
SKIPPED_COUNT=0

for status in "${STATUS_LIST[@]}"; do
    case "$status" in
        success) ((SUCCESS_COUNT++)) ;;
        failed) ((FAILED_COUNT++)) ;;
        skipped) ((SKIPPED_COUNT++)) ;;
    esac
done

# =============================================================================
# 磁盘空间报告
# =============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE} 磁盘空间${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
df -h . | head -2
echo ""

# 数据目录占用
DATA_DIR="./openfly_to_airvln_data/${ENV}"
if [ -d "$DATA_DIR" ]; then
    DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)
    echo -e "  📁 数据目录 (${ENV}): ${YELLOW}${DATA_SIZE}${NC}"
fi

ANNO_DIR="./openfly_to_airvln_data/annotation/${ENV}"
if [ -d "$ANNO_DIR" ]; then
    ANNO_SIZE=$(du -sh "$ANNO_DIR" 2>/dev/null | cut -f1)
    echo -e "  📄 标注目录: ${YELLOW}${ANNO_SIZE}${NC}"
fi
echo ""

# =============================================================================
# 输出最终报告
# =============================================================================
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    📋 处理报告                            ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  环境:       ${YELLOW}${ENV}${NC}"
echo -e "  总耗时:     ${YELLOW}${TOTAL_HOUR}h ${TOTAL_MIN}m ${TOTAL_SEC}s${NC}"
echo -e "  成功:       ${GREEN}${SUCCESS_COUNT}${NC} / ${TOTAL}"
echo -e "  跳过:       ${YELLOW}${SKIPPED_COUNT}${NC} (不在 train.json 中)"
echo -e "  失败:       ${RED}${FAILED_COUNT}${NC}"
echo ""
echo -e "  ┌──────────────────────────────┬──────────┬─────────────────────────┐"
echo -e "  │ 轨迹类型                     │ 状态     │ 详情                    │"
echo -e "  ├──────────────────────────────┼──────────┼─────────────────────────┤"

for i in "${!ALL_SUBFOLDERS[@]}"; do
    SUBFOLDER="${ALL_SUBFOLDERS[$i]}"
    STATUS="${STATUS_LIST[$i]}"
    DETAIL="${DETAIL_LIST[$i]}"

    case "$STATUS" in
        success) STATUS_ICON="${GREEN}✅ 成功${NC}" ;;
        skipped) STATUS_ICON="${YELLOW}⏭️  跳过${NC}" ;;
        failed)  STATUS_ICON="${RED}❌ 失败${NC}" ;;
    esac

    printf "  │ %-28s │ %b │ %-23s │\n" "$SUBFOLDER" "$STATUS_ICON" "$DETAIL"
done

echo -e "  └──────────────────────────────┴──────────┴─────────────────────────┘"
echo ""

# =============================================================================
# 写入报告文件（纯文本，无颜色）
# =============================================================================
{
    echo "=========================================="
    echo " OpenFly → AirVLN 批量处理报告"
    echo "=========================================="
    echo ""
    echo "环境:       ${ENV}"
    echo "开始时间:   ${START_TIME_STR}"
    echo "结束时间:   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "总耗时:     ${TOTAL_HOUR}h ${TOTAL_MIN}m ${TOTAL_SEC}s"
    echo ""
    echo "成功: ${SUCCESS_COUNT} / ${TOTAL}"
    echo "跳过: ${SKIPPED_COUNT} (不在 train.json 中)"
    echo "失败: ${FAILED_COUNT}"
    echo ""
    echo "------------------------------------------"
    echo " 详细结果"
    echo "------------------------------------------"
    for i in "${!ALL_SUBFOLDERS[@]}"; do
        SUBFOLDER="${ALL_SUBFOLDERS[$i]}"
        STATUS="${STATUS_LIST[$i]}"
        DETAIL="${DETAIL_LIST[$i]}"
        case "$STATUS" in
            success) MARK="[OK]    " ;;
            skipped) MARK="[SKIP]  " ;;
            failed)  MARK="[FAIL]  " ;;
        esac
        echo "  ${MARK} ${SUBFOLDER} — ${DETAIL}"
    done
    echo ""
    echo "------------------------------------------"
    echo " 磁盘空间"
    echo "------------------------------------------"
    df -h . | head -2
    echo ""
    if [ -d "$DATA_DIR" ]; then
        echo "  数据目录 (${ENV}): $(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)"
    fi
    if [ -d "$ANNO_DIR" ]; then
        echo "  标注目录: $(du -sh "$ANNO_DIR" 2>/dev/null | cut -f1)"
    fi
} > "$REPORT_FILE"

echo -e "  📝 报告已保存: ${YELLOW}${REPORT_FILE}${NC}"
echo ""

# 如果有失败，以非零退出
if [ $FAILED_COUNT -gt 0 ]; then
    echo -e "${RED}⚠️  有 ${FAILED_COUNT} 个轨迹类型处理失败，请检查。${NC}"
    exit 1
fi
