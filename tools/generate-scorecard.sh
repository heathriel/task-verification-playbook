#!/bin/bash
# generate-scorecard.sh
# Creates a completion artifact template with verification scorecard

TASK_ID=$1
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARTIFACT_DIR="work-records/completions"
ARTIFACT="$ARTIFACT_DIR/TASK_${TASK_ID}_${TIMESTAMP}.md"

# Create directory if it doesn't exist
mkdir -p "$ARTIFACT_DIR"

cat > "$ARTIFACT" << 'EOF'
---
# Task {id}: {title}
Date: {timestamp}
Status: [COMPLETE | BLOCKED | PARTIAL]

## Request
{original request text}

## Success Criteria
{what "done" looks like}

## Approach
{methodology used step-by-step}

## Output
{deliverable summary or link}

## Verification Scorecard
Completeness: __/10
Correctness: __/10
Documentation: __/10
Verifiability: __/10
**Overall: __/10**

## Evidence
- {link, screenshot, log, or attachment}

## Issues Encountered
{problems faced and how they were resolved}

## Lessons Learned
{what would you do differently next time}

## Next Actions
{follow-up tasks if any}
---
EOF

echo "✅ Created: $ARTIFACT"
echo "📝 Fill in the template and calculate overall score (average of 4 dimensions)"
echo "🎯 Target: ≥8.0 for shipping"
