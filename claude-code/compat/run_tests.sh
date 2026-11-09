#!/bin/zsh
# Desktop-compat test runner. Works on a STAGED COPY of the live host-adapter; HOME is isolated; nothing live is modified.
#   zsh run_tests.sh           compat tests + EP's retention suites
#   zsh run_tests.sh --full    ... plus the existing recall / scenario modules (compared as plain pass/fail lines)
#   KEEP=1 zsh run_tests.sh    keep the stage dir for inspection
HERE=${0:A:h}
CC=${EP_CC:-${HERE:h}}                                                 # the claude-code/ kit under test (repo checkout or installed copy)
EP_HOME=${EP_HOME:-$HOME/.evolving-profile}
REALHOME=$HOME
LIVE=${EP_ADAPTER:-$EP_HOME/runtime/host-adapter}                      # host-adapter under test (copied to a stage dir; nothing live is modified)
PY=${EP_PY:-$EP_HOME/runtime/python-3.11/bin/python}
[[ -x $PY ]] || PY=$(command -v python3)
SP=${EP_PYTEST_SITE:-$HOME/Library/Python/3.9/lib/python/site-packages}  # only used by --full for pytest-style modules
S=$(mktemp -d /private/tmp/ep_compat.XXXXXX)                         # real path: the source codec rejects symlinked parents (/tmp -> /private/tmp)
trap '[[ -n "$KEEP" ]] || rm -rf "$S"' EXIT
mkdir -p $S/home
for d in config controller guidance ham-os status console; do [[ -e ${LIVE:h}/$d ]] && ln -sfn ${LIVE:h}/$d $S/$d; done
cp -R $LIVE $S/host-adapter 2>/dev/null
rc=0

echo "== 1. are the patches intact in the staged copy of the live files?"
$PY -I $CC/compat/desktop_compat_patches.py check --adapter $S/host-adapter || rc=1

echo "== 2. compat tests (patcher, origin_agent, desktop roots + discovery, settle period, host_id label)"
out=$(HOME=$S/home PYTHONPATH=$S/host-adapter:$CC:${EP_API_SRC:-${CC:h}/api} $PY -m unittest discover -s $CC/compat/tests -p 'test_*.py' 2>&1); st=$?
echo "$out" | tail -n 6
[[ $st -eq 0 ]] || rc=1

echo "== 3. EP retention suites (existing)"
out=$(cd $S/host-adapter && HOME=$S/home $PY -m unittest -q test_retention_worker test_retention_write_policy 2>&1); st=$?
echo "$out" | tail -n 4
[[ $st -eq 0 ]] || rc=1

if [[ "$1" == "--full" ]]; then
  echo "== 4. existing recall / scenario modules"
  cd $S/host-adapter
  for m in test_manual_entry_integration test_memory_route_probe test_pre_tool_use_memory_guard test_prompt_ingress_metadata test_rollback_drill test_system_probe test_retrieval_audit_repairs test_agent_process_route test_context_summary test_context_incremental test_scenario_source test_scenario_chunks test_scenario_episodes test_scenario_state_v3; do
    [[ -f $m.py ]] || { printf "%-42s missing\n" $m; continue; }
    if grep -q "^import pytest\|^from pytest" $m.py || ! grep -q "unittest" $m.py; then
      r=$(HOME=$S/home PYTHONPATH=$SP /usr/bin/python3 -m pytest -q -p no:cacheprovider $m.py 2>&1 | tail -n 1)
    else
      r=$(HOME=$S/home $PY -m unittest -q $m 2>&1 | tail -n 3 | tr '\n' ' ')
    fi
    printf "%-42s %s\n" $m "$r"
  done
  echo "(known baseline failures before ANY desktop patch: test_agent_process_route, test_retrieval_audit_repairs(1), test_scenario_state_v3, test_context_incremental::test_cli_discovery_needs_no_provider...)"
fi
echo "== result: $([[ $rc -eq 0 ]] && echo PASS || echo FAIL)"
exit $rc
