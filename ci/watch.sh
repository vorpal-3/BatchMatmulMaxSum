#!/usr/bin/env bash
# CANNLab CI watcher.
#
# Runs INSIDE the CANNLab instance. It polls the repository, and whenever a new
# commit lands on the watched branch it rebuilds and pushes the build log back on
# a SEPARATE branch. The development side then reads results with `git fetch`
# instead of having to read the IDE's canvas terminal — which is the whole point:
# the canvas terminal cannot be read programmatically, but git can be.
#
# Watching and publishing are split across branches on purpose: if the watcher
# pushed its logs to the branch it watches, every build would trigger another build.
#
# Setup (once, inside the instance):
#     git config --global credential.helper store
#     cd /mnt/workspace/proj
#     git remote set-url origin https://<TOKEN>@github.com/<owner>/<repo>.git
#     nohup bash ci/watch.sh > /mnt/workspace/watch.out 2>&1 &
#
# Then the loop is: push to master -> wait -> fetch the log branch.

set -u

REPO_DIR="${REPO_DIR:-/mnt/workspace/proj}"
WATCH_BRANCH="${WATCH_BRANCH:-master}"
LOG_BRANCH="${LOG_BRANCH:-ci-logs}"
CANN_HOME="${CANN_HOME:-/home/developer/Ascend/cann-9.0.0}"
INTERVAL="${INTERVAL:-20}"
WORK_SUBDIR="${WORK_SUBDIR:-work}"
CMD="${CMD:-bash run.sh}"

cd "$REPO_DIR" || { echo "[watch] cannot cd $REPO_DIR"; exit 1; }

log() { echo "[watch $(date '+%H:%M:%S')] $*"; }

log "repo=$REPO_DIR watch=$WATCH_BRANCH logs->$LOG_BRANCH interval=${INTERVAL}s"
log "cann=$CANN_HOME cmd='$CMD'"

LAST=""
while true; do
    if ! git fetch origin "$WATCH_BRANCH" -q 2>/dev/null; then
        log "fetch failed; retrying"
        sleep "$INTERVAL"
        continue
    fi

    REMOTE="$(git rev-parse "origin/$WATCH_BRANCH" 2>/dev/null || echo none)"
    if [ "$REMOTE" != "$LAST" ]; then
        SHA="$(git rev-parse --short "origin/$WATCH_BRANCH")"
        log "new commit $SHA -> building"

        git checkout -q -B "$LOG_BRANCH" 2>/dev/null || git checkout -q "$LOG_BRANCH"
        git reset --hard -q "origin/$WATCH_BRANCH"

        OUT="ci-logs/result-$SHA.log"
        mkdir -p ci-logs
        {
            echo "=== commit $REMOTE ==="
            echo "=== host: $(uname -m) $(uname -r) ==="
            echo "=== cmd: $CMD (in $WORK_SUBDIR) ==="
            echo
        } > "$OUT"

        # Load the CANN environment exactly as the组委会 run.sh expects.
        set +u
        # shellcheck disable=SC1090
        source "$CANN_HOME/set_env.sh" >> "$OUT" 2>&1
        set -u

        ( cd "$WORK_SUBDIR" && eval "$CMD" ) >> "$OUT" 2>&1
        RC=$?
        echo "" >> "$OUT"
        echo "=== EXIT=$RC ===" >> "$OUT"
        log "build finished EXIT=$RC"

        git add -f "$OUT" >/dev/null 2>&1
        if git -c user.name=cannlab -c user.email=cannlab@cannlab.local \
               commit -q -m "ci: result for $SHA (exit $RC)" >/dev/null 2>&1; then
            if git push -q -f origin "$LOG_BRANCH" 2>&1 | tail -2; then
                log "pushed $LOG_BRANCH ($SHA)"
            else
                log "push FAILED (check credentials)"
            fi
        else
            log "nothing to commit"
        fi

        # Remember the commit we just built, not the one we pushed, so the
        # watcher does not rebuild its own log commit.
        LAST="$REMOTE"
    fi
    sleep "$INTERVAL"
done
