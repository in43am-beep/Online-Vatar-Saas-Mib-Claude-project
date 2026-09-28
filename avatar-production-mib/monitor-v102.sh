#!/bin/bash
# Monitor v1.0.2 release for AvatarProductionByMIB.exe, up to ~120 min.
REPO="in43am-beep/avatar-production-mib"
REL_URL="https://api.github.com/repos/$REPO/releases/tags/v1.0.2"
RUNS_URL="https://api.github.com/repos/$REPO/actions/runs?per_page=20"
INTERVAL=300
MAX_CHECKS=24

for i in $(seq 1 $MAX_CHECKS); do
  echo "=== check $i at $(date -u +%FT%TZ) ==="
  rel=$(curl -s -H "Accept: application/vnd.github+json" "$REL_URL")
  exe=$(echo "$rel" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except: d={}
for a in d.get('assets',[]):
    if a.get('name')=='AvatarProductionByMIB.exe' and a.get('state')=='uploaded':
        print(a.get('browser_download_url',''),'|',a.get('size',0),'|',a.get('digest',''))
        break
")
  runs=$(curl -s -H "Accept: application/vnd.github+json" "$RUNS_URL")
  runinfo=$(echo "$runs" | python3 -c "
import json,sys
try: d=json.load(sys.stdin)
except: d={}
for r in d.get('workflow_runs',[]):
    hb=r.get('head_branch','')
    if hb=='v1.0.2' or (r.get('event')=='release' and 'v1.0.2' in hb):
        print(r.get('id'),'|',r.get('name'),'|',hb,'|',r.get('status'),'|',r.get('conclusion'))
        break
")
  echo "exe: ${exe:-none}"
  echo "run: ${runinfo:-none}"
  size=$(echo "$exe" | awk -F'|' '{print $2}' | tr -d ' ')
  concl=$(echo "$runinfo" | awk -F'|' '{print $5}' | tr -d ' ')
  if [ -n "$exe" ] && [ "$size" -gt 50000000 ] 2>/dev/null && [ "$concl" = "success" ]; then
    echo "RESULT: READY"
    echo "download: https://github.com/$REPO/releases/download/v1.0.2/AvatarProductionByMIB.exe"
    echo "size_bytes: $size"
    echo "digest: $(echo "$exe" | awk -F'|' '{print $3}')"
    echo "run: $runinfo"
    exit 0
  fi
  if [ "$concl" = "failure" ] || [ "$concl" = "cancelled" ]; then
    echo "RESULT: BUILD FAILED"
    rid=$(echo "$runinfo" | awk -F'|' '{print $1}' | tr -d ' ')
    curl -s -H "Accept: application/vnd.github+json" "https://api.github.com/repos/$REPO/actions/runs/$rid/jobs?per_page=50" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for j in d.get('jobs',[]):
    if j.get('conclusion') in ('failure','cancelled'):
        print('FAILED JOB:',j.get('name'))
        for s in j.get('steps',[]):
            if s.get('conclusion')=='failure':
                print('FAILED STEP:',s.get('name'))
"
    exit 1
  fi
  [ $i -lt $MAX_CHECKS ] && sleep $INTERVAL
done
echo "RESULT: TIMEOUT after ~120 min"
echo "last exe: ${exe:-none}"
echo "last run: ${runinfo:-none}"
exit 2
