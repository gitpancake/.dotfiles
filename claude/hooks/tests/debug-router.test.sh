#!/usr/bin/env bash

set -u

hook="$(cd "$(dirname "$0")/.." && pwd)/debug-router.sh"
failures=0

expectFires() {
  local want=$1 prompt=$2 sessionId out got
  sessionId="debug-router-test-$$-$RANDOM"
  out=$(jq -nc --arg p "$prompt" --arg s "$sessionId" \
    '{session_id: $s, prompt: $p, cwd: "/tmp"}' | bash "$hook")
  rm -f "${HOME}/.claude/state/turn-counters/session-${sessionId}.warned"
  [[ -n "$out" ]] && got=1 || got=0
  if [[ "$got" != "$want" ]]; then
    failures=$((failures + 1))
    printf 'FAIL want=%s got=%s  %s\n' "$want" "$got" "$prompt"
  fi
}

expectFires 0 "can we do a full review of our claude code environment - fable misclassifying the root cause, with our test runner using sonnet - it required long hours"
expectFires 0 "i want to study my practice, the latest audit covered everything"
expectFires 0 "write tests for the new sendEmail use case, make sure the port is covered and required fields are typed"
expectFires 0 "the checkout page needs a redesign, registered users only"
expectFires 1 "why is PR 9210 failing"
expectFires 1 "tests are failing on main"
expectFires 1 "the wilson tests keep going red"
expectFires 1 "ci is red on my branch"
expectFires 1 "PR checks are failing"
expectFires 1 "build failed again"
expectFires 1 "bun type-check won't run"
expectFires 1 "holland is broken"
expectFires 1 "why did the nightly job crash"

if (( failures > 0 )); then
  printf '%s failing case(s)\n' "$failures"
  exit 1
fi
echo "debug-router: all cases pass"
