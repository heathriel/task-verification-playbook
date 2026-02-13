#!/bin/bash
# quality-trend.sh
# Analyzes completion artifacts for quality trends

echo "=== Quality Trend Analysis ==="
echo

ARTIFACT_DIR="work-records/completions"

# Check if directory exists
if [ ! -d "$ARTIFACT_DIR" ]; then
    echo "❌ No artifacts directory found at: $ARTIFACT_DIR"
    echo "💡 Tip: Create artifacts using generate-scorecard.sh"
    exit 1
fi

# Count artifacts
TOTAL_COUNT=$(find "$ARTIFACT_DIR" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

if [ "$TOTAL_COUNT" -eq 0 ]; then
    echo "❌ No completion artifacts found"
    echo "💡 Tip: Use generate-scorecard.sh to create your first artifact"
    exit 0
fi

echo "📊 Total completions: $TOTAL_COUNT"
echo

# Last 30 days average
RECENT_COUNT=$(find "$ARTIFACT_DIR" -name "*.md" -mtime -30 2>/dev/null | wc -l | tr -d ' ')
if [ "$RECENT_COUNT" -gt 0 ]; then
    echo "📅 Last 30 days: $RECENT_COUNT completions"
    RECENT_AVG=$(find "$ARTIFACT_DIR" -name "*.md" -mtime -30 2>/dev/null \
      | xargs grep "Overall:" 2>/dev/null \
      | awk -F: '{print $NF}' \
      | awk '{gsub(/\/10/, ""); sum+=$1; count++} END {if(count>0) printf "%.2f", sum/count; else print "N/A"}')
    echo "⭐ Average quality score: $RECENT_AVG/10"
    echo
fi

# Last 7 days
WEEK_COUNT=$(find "$ARTIFACT_DIR" -name "*.md" -mtime -7 2>/dev/null | wc -l | tr -d ' ')
if [ "$WEEK_COUNT" -gt 0 ]; then
    echo "📅 Last 7 days: $WEEK_COUNT completions"
    WEEK_AVG=$(find "$ARTIFACT_DIR" -name "*.md" -mtime -7 2>/dev/null \
      | xargs grep "Overall:" 2>/dev/null \
      | awk -F: '{print $NF}' \
      | awk '{gsub(/\/10/, ""); sum+=$1; count++} END {if(count>0) printf "%.2f", sum/count; else print "N/A"}')
    echo "⭐ Average quality score: $WEEK_AVG/10"
    echo
fi

# Recent low scores (<8.0)
echo "🔍 Recent tasks needing review (<8.0):"
LOW_SCORES=$(find "$ARTIFACT_DIR" -name "*.md" -mtime -7 2>/dev/null \
  | xargs grep -l "Overall: [0-7]\." 2>/dev/null \
  | head -5)

if [ -z "$LOW_SCORES" ]; then
    echo "   ✅ None found - all recent tasks scored ≥8.0"
else
    echo "$LOW_SCORES" | while read file; do
        SCORE=$(grep "Overall:" "$file" | awk -F: '{print $NF}')
        echo "   📄 $(basename "$file"): $SCORE"
    done
fi

echo
echo "🎯 Target: ≥8.0 individual, ≥8.5 monthly average"
