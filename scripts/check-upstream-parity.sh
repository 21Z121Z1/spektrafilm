#!/usr/bin/env bash
# check-upstream-parity.sh — verify local branch has not diverged from upstream/main
# and that core simulation files + shared data match upstream.
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel 2>/dev/null || \
             git -C "$(cd "$(dirname "$0")/.." && pwd)" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
UPSTREAM_REF="${UPSTREAM_REF:-${UPSTREAM_REMOTE}/${UPSTREAM_BRANCH}}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

fail=0

pass() { printf "  ${GREEN}PASS${NC}  %s\n" "$*"; }
warn() { printf "  ${YELLOW}WARN${NC}  %s\n" "$*"; }
fail_msg() { printf "  ${RED}FAIL${NC}  %s\n" "$*"; fail=1; }

# ── 1. Fetch upstream ────────────────────────────────────────────────────────
echo "=== 1. Fetching ${UPSTREAM_REMOTE} ==="
if git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
    git fetch "$UPSTREAM_REMOTE" 2>/dev/null || warn "fetch failed (offline?) — using cached refs"
else
    echo "  Remote '${UPSTREAM_REMOTE}' not configured; skipping fetch."
    echo "  Set UPSTREAM_REMOTE to the remote name, e.g.:"
    echo "    UPSTREAM_REMOTE=origin bash $0"
    if ! git rev-parse "$UPSTREAM_REF" >/dev/null 2>&1; then
        fail_msg "Cannot resolve ${UPSTREAM_REF}. Exiting."
        exit "$fail"
    fi
fi

# ── 2. Merge-base check ─────────────────────────────────────────────────────
echo ""
echo "=== 2. Merge-base divergence check ==="
MERGE_BASE="$(git merge-base HEAD "$UPSTREAM_REF" 2>/dev/null || true)"
UPSTREAM_SHA="$(git rev-parse "$UPSTREAM_REF" 2>/dev/null || true)"
HEAD_SHA="$(git rev-parse HEAD)"

if [ -z "$MERGE_BASE" ]; then
    fail_msg "No merge-base found between HEAD and ${UPSTREAM_REF}."
elif [ "$MERGE_BASE" = "$UPSTREAM_SHA" ]; then
    pass "HEAD is up-to-date with ${UPSTREAM_REF} (merge-base = ${MERGE_BASE:0:12})"
else
    UPSTREAM_LOG="$(git log --oneline "$MERGE_BASE".."$UPSTREAM_SHA" | wc -l | tr -d ' ')"
    fail_msg "HEAD diverged from ${UPSTREAM_REF}."
    echo "         merge-base  : ${MERGE_BASE:0:12}"
    echo "         upstream tip: ${UPSTREAM_SHA:0:12}"
    echo "         upstream has ${UPSTREAM_LOG} commit(s) past merge-base."
fi

# ── 3. Core simulation file diffs ───────────────────────────────────────────
echo ""
echo "=== 3. Core simulation file diffs against ${UPSTREAM_REF} ==="

CORE_FILES=(
    src/spektrafilm/runtime/pipeline.py
    src/spektrafilm/runtime/process.py
    src/spektrafilm/runtime/params_builder.py
    src/spektrafilm/runtime/params_schema.py
    src/spektrafilm/runtime/stages/filming.py
    src/spektrafilm/runtime/stages/printing.py
    src/spektrafilm/runtime/stages/scanning.py
    src/spektrafilm/runtime/services/spectral_lut_compute.py
    src/spektrafilm/model/emulsion.py
    src/spektrafilm/model/density_curves.py
    src/spektrafilm/model/couplers.py
    src/spektrafilm/model/color_filters.py
    src/spektrafilm/profiles/io.py
    src/spektrafilm/profiles/__init__.py
    src/spektrafilm/config.py
)

for f in "${CORE_FILES[@]}"; do
    if ! git rev-parse "$UPSTREAM_REF:$f" >/dev/null 2>&1; then
        fail_msg "${f}  (missing in ${UPSTREAM_REF})"
        continue
    fi
    if [ ! -e "$f" ]; then
        fail_msg "${f}  (missing locally)"
        continue
    fi
    if git diff --quiet "$UPSTREAM_REF" -- "$f" 2>/dev/null; then
        pass "${f}"
    else
        fail_msg "${f}  (differs from ${UPSTREAM_REF})"
    fi
done

# ── 4. Shared data / profile file SHA-256 hashes ────────────────────────────
echo ""
echo "=== 4. Shared data / profile file SHA-256 hashes ==="

# Discover shared data files tracked by upstream. Current upstream stores runtime
# data under src/spektrafilm/data/; the older roots are kept for compatibility
# with historical layouts and downstream forks.
DATA_PATHS=()
while IFS= read -r path; do
    [ -n "$path" ] && DATA_PATHS+=("$path")
done < <(git ls-tree --name-only -r "$UPSTREAM_REF" 2>/dev/null | \
         grep -E '^(src/spektrafilm/data/|data/|profiles/data/).*\.(icc|icm|spectrum|json|csv|npy|npz|dat|txt|lut)$' || true)

if [ ${#DATA_PATHS[@]} -eq 0 ]; then
    warn "no shared data files found in ${UPSTREAM_REF}"
else
    echo "  Found ${#DATA_PATHS[@]} shared upstream data file(s)."
    for f in "${DATA_PATHS[@]}"; do
        # Compute hash of the file as it exists in the upstream tree
        upstream_hash="$(git cat-file blob "${UPSTREAM_REF}:${f}" 2>/dev/null | shasum -a 256 | cut -d' ' -f1 || true)"

        # Compute hash of the file as it exists in the working tree
        if [ ! -f "$f" ]; then
            fail_msg "${f}  (missing locally; upstream hash = ${upstream_hash:0:16}…)"
            continue
        fi
        local_hash="$(shasum -a 256 "$f" | cut -d' ' -f1)"

        if [ "$upstream_hash" = "$local_hash" ]; then
            pass "${f}  (sha256 ${local_hash:0:16}…)"
        else
            fail_msg "${f}  (local ${local_hash:0:16}… != upstream ${upstream_hash:0:16}…)"
        fi
    done
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Summary ==="
echo "Compared HEAD ${HEAD_SHA:0:12} against ${UPSTREAM_REF} ${UPSTREAM_SHA:0:12}"
if [ "$fail" -eq 0 ]; then
    printf "${GREEN}All checks passed.${NC}\n"
else
    printf "${RED}Some checks failed (see above).${NC}\n"
fi

exit "$fail"
