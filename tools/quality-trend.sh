#!/bin/bash
# quality-trend.sh
# Analyzes completion artifacts for quality trends

echo "=== Quality Trend Analysis ==="
echo

ARTIFACT_DIR="work-records/completions"

if [ ! -d "$ARTIFACT_DIR" ]; then
    echo "❌ No artifacts directory found at: $ARTIFACT_DIR"
    echo "💡 Tip: Create artifacts using generate-scorecard.sh"
    exit 1
fi

# Read at most one score per artifact. Blank templates, blocked tasks, and
# malformed/out-of-range scores are unscored, not zero-quality completions.
read_score() {
    awk '
        /^[[:space:]]*(\*\*)?Overall:[[:space:]]*/ {
            sub(/^[[:space:]]*(\*\*)?Overall:[[:space:]]*/, "")
            sub(/[[:space:]]*$/, "")
            sub(/\*\*$/, "")
            if ($0 ~ /^[0-9]+([.][0-9]+)?\/10$/) {
                sub(/\/10$/, "")
                if ($0 + 0 >= 0 && $0 + 0 <= 10) print $0
            }
            exit
        }
    ' "$1"
}

TOTAL_COUNT=0
while IFS= read -r -d '' file; do
    TOTAL_COUNT=$((TOTAL_COUNT + 1))
done < <(find "$ARTIFACT_DIR" -type f -name "*.md" -print0)

if [ "$TOTAL_COUNT" -eq 0 ]; then
    echo "❌ No completion artifacts found"
    echo "💡 Tip: Use generate-scorecard.sh to create your first artifact"
    exit 0
fi

echo "📊 Total artifacts: $TOTAL_COUNT"
echo

LOW_SCORES=()
report_window() {
    local days=$1 count=0 scored=0 file score average
    local scores=()
    while IFS= read -r -d '' file; do
        count=$((count + 1))
        score=$(read_score "$file")
        if [ -n "$score" ]; then
            scores+=("$score")
            scored=$((scored + 1))
            if [ "$days" -eq 7 ] && [ "${#LOW_SCORES[@]}" -lt 5 ] &&
                awk -v score="$score" 'BEGIN {exit !(score < 8)}'; then
                LOW_SCORES+=("${file##*/}: $score/10")
            fi
        fi
    done < <(find "$ARTIFACT_DIR" -type f -name "*.md" -mtime "-$days" -print0)

    if [ "$count" -gt 0 ]; then
        echo "📅 Last $days days: $count artifacts ($scored scored, $((count - scored)) unscored)"
        if [ "$scored" -gt 0 ]; then
            average=$(printf '%s\n' "${scores[@]}" | awk '{sum += $1} END {printf "%.2f", sum/NR}')
            echo "⭐ Average quality score: $average/10"
        else
            echo "⭐ Average quality score: N/A (no numeric scores)"
        fi
        echo
    fi
}

report_window 30
report_window 7

echo "🔍 Recent tasks needing review (<8.0):"
if [ "${#LOW_SCORES[@]}" -eq 0 ]; then
    echo "   No numeric scores below 8.0 found; unscored artifacts are excluded."
else
    printf '   📄 %s\n' "${LOW_SCORES[@]}"
fi

echo
echo "🎯 Target: ≥8.0 individual, ≥8.5 monthly average"
