#!/bin/bash
# Spektrafilm Autonomous Improvement Loop
# Runs code review → fix → test → review cycles until convergence

set -e
cd /home/Z121Z121/spektrafilm

LOG="/home/Z121Z121/spektrafilm/docs/dev/autonomous-loop.log"
ROUND=1
MAX_ROUNDS=10

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"
}

run_tests() {
    .venv/bin/python -m pytest --ignore=tests/gui -q 2>&1 | tail -10
}

log "=== Autonomous Improvement Loop Started ==="

# Wait for research to complete
log "Waiting for research session to complete..."
while [ ! -f "/home/Z121Z121/spektrafilm/docs/dev/research-gpu-color-management.md" ]; do
    sleep 30
done
log "Research complete. Starting improvement cycles."

while [ $ROUND -le $MAX_ROUNDS ]; do
    log "=== Round $ROUND ==="
    
    # Step 1: Run tests to establish baseline
    log "Running test baseline..."
    TEST_OUTPUT=$(run_tests 2>&1)
    PASSED=$(echo "$TEST_OUTPUT" | grep -oP '\d+ passed' | grep -oP '\d+')
    FAILED=$(echo "$TEST_OUTPUT" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")
    log "Baseline: $PASSED passed, $FAILED failed"
    
    if [ "$FAILED" != "0" ] && [ "$FAILED" != "" ]; then
        log "Tests failing! Running fix cycle..."
        claude -p "Tests are failing. Run .venv/bin/python -m pytest --ignore=tests/gui -q to see failures. Fix each failing test by addressing the root cause in the source code. Run tests after each fix. Continue until all tests pass. Read CLAUDE.md for project rules." \
            --effort max \
            --allowedTools "Bash(*)" "Read(*)" "Write(*)" "Edit(*)" "Glob(*)" "Grep(*)" \
            2>&1 | tee -a "$LOG"
    fi
    
    # Step 2: Code quality review
    log "Running code quality review..."
    claude -p "Perform a thorough code quality review of the spektrafilm project. Focus on:
1. Type hints and docstrings coverage
2. Error handling patterns
3. Dead code and unused imports
4. Code duplication
5. API consistency
6. Test coverage gaps
7. Performance anti-patterns
8. Security concerns

Read CLAUDE.md for project context. Use web-search MCP to look up best practices for any patterns you find.

Write your findings to docs/dev/code-quality-review-round-$ROUND.md with specific file:line references and actionable fixes.

Do NOT modify any code - this is a read-only review." \
        --effort max \
        --allowedTools "Bash(*)" "Read(*)" "Write(*)" "Edit(*)" "Glob(*)" "Grep(*)" \
        2>&1 | tee -a "$LOG"
    
    # Step 3: Apply improvements from quality review
    log "Applying code quality improvements..."
    claude -p "Read docs/dev/code-quality-review-round-$ROUND.md and fix the most impactful issues found. Read CLAUDE.md for project rules. Focus on:
1. Any bugs or correctness issues
2. Missing error handling
3. Type hint improvements for public APIs
4. Test coverage for untested edge cases
5. Performance improvements

Run .venv/bin/python -m pytest --ignore=tests/gui -q after each fix. All tests must pass." \
        --effort max \
        --allowedTools "Bash(*)" "Read(*)" "Write(*)" "Edit(*)" "Glob(*)" "Grep(*)" \
        2>&1 | tee -a "$LOG"
    
    # Step 4: Check if research suggests new improvements
    if [ -f "/home/Z121Z121/spektrafilm/docs/dev/research-gpu-color-management.md" ]; then
        log "Applying research insights..."
        claude -p "Read docs/dev/research-gpu-color-management.md for GPU acceleration and color management best practices. Read CLAUDE.md for project context. Identify the TOP 3 most impactful improvements we can make to the codebase RIGHT NOW based on the research findings. Implement only the ones that are:
1. Low risk (won't break existing tests)
2. High impact (improve correctness, performance, or maintainability)
3. Self-contained (don't require major architectural changes)

Run .venv/bin/python -m pytest --ignore=tests/gui -q after each change. Write what you did to docs/dev/research-implementation-round-$ROUND.md." \
            --effort max \
            --allowedTools "Bash(*)" "Read(*)" "Write(*)" "Edit(*)" "Glob(*)" "Grep(*)" \
            2>&1 | tee -a "$LOG"
    fi
    
    # Step 5: Final test verification
    log "Final test verification for round $ROUND..."
    FINAL_TESTS=$(run_tests 2>&1)
    FINAL_PASSED=$(echo "$FINAL_TESTS" | grep -oP '\d+ passed' | grep -oP '\d+')
    FINAL_FAILED=$(echo "$FINAL_TESTS" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")
    log "Round $ROUND complete: $FINAL_PASSED passed, $FINAL_FAILED failed"
    
    # Step 6: Commit improvements
    if git diff --quiet HEAD 2>/dev/null; then
        log "No changes to commit this round."
    else
        git add -A
        git commit -m "autonomous: round $ROUND improvements [skip ci]" 2>&1 | tee -a "$LOG"
        log "Committed round $ROUND changes."
    fi
    
    # Check convergence
    if [ "$FINAL_FAILED" = "0" ] || [ "$FINAL_FAILED" = "" ]; then
        if git diff --quiet HEAD~1 HEAD 2>/dev/null; then
            log "No changes in round $ROUND. Convergence reached."
            break
        fi
    fi
    
    ROUND=$((ROUND + 1))
done

log "=== Autonomous Loop Complete after $((ROUND-1)) rounds ==="
log "Final test status: $(run_tests 2>&1 | tail -3)"
