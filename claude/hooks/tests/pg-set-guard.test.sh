#!/usr/bin/env bash
# Fixture for pg-set-guard.sh. Run: bash ~/.claude/hooks/tests/pg-set-guard.test.sh
set -u
hook=~/.claude/hooks/pg-set-guard.sh
tmp=$(mktemp -d)
printf 'SET statement_timeout = 0;\nselect 1;\n' > "$tmp/bad.sql"
printf 'select 1;\n' > "$tmp/ok.sql"
fails=0

run() {
  local want=$1 name=$2 cmd=$3
  local out verdict
  out=$(jq -n --arg c "$cmd" --arg d "$tmp" '{tool_name:"Bash",tool_input:{command:$c},cwd:$d}' | bash "$hook")
  verdict=$(jq -r '.hookSpecificOutput.permissionDecision // "allow"' <<<"${out:-{\}}")
  if [[ "$verdict" == "$want" ]]; then echo "ok    $name"; else echo "FAIL  $name (want $want, got $verdict)"; fails=$((fails+1)); fi
}

run deny  'inline -c set'              'psql "$URL" -c "set default_transaction_read_only=on; select 1"'
run deny  'inline -c SET TO'           'psql "$URL" -c "SET statement_timeout TO 0"'
run deny  'SET SESSION'                'psql "$URL" -c "SET SESSION default_transaction_read_only = on"'
run deny  'heredoc set'                $'psql "$URL" <<\'SQL\'\nset default_transaction_read_only=on;\nselect count(*) from threads;\nSQL'
run deny  'alter role set'             'psql "$URL" -c "ALTER ROLE claude_ro SET default_transaction_read_only = on"'
run deny  'set_config session'         'psql "$URL" -c "select set_config('"'"'statement_timeout'"'"','"'"'0'"'"', false)"'
run deny  'referenced .sql file'       'psql "$URL" -f bad.sql'
run deny  'PGOPTIONS'                  'PGOPTIONS="-c default_transaction_read_only=on" psql "$URL" -c "select 1"'
run deny  'pooler host literal'        'psql "postgresql://u:p@ep-quiet-shadow-awz45in5-pooler.c-12.us-east-1.aws.neon.tech/db" -c "set statement_timeout=0"'
run deny  'pgcli'                      'pgcli "$URL" -c "set statement_timeout=0"'

run allow 'plain select'               'psql "$URL" -X -c "select count(*) from threads"'
run allow 'psql client \set'           'psql "$URL" -c "\set x 1" -c "select :x"'
run allow 'SET LOCAL in txn'           'psql "$URL" -c "begin; set local statement_timeout = 0; select 1; commit"'
run allow 'set_config local'           'psql "$URL" -c "select set_config('"'"'statement_timeout'"'"','"'"'0'"'"', true)"'
run allow 'bash set -a then psql'      'set -a; . ~/.claude/.env.local; set +a; psql "$URL" -c "select 1"'
run allow 'referenced ok .sql'         'psql "$URL" -f ok.sql'
run allow 'unpooled host literal'      'psql "postgresql://u:p@ep-long-bird-aipkxwfd.c-4.us-east-1.aws.neon.tech/db" -c "set statement_timeout=0"'
run allow 'non-psql command'           'git log --oneline | grep -i "set timezone to"'
run allow 'settimeout in a bun script' 'bun run src/x.ts --set foo=bar'
run allow 'UPDATE ... SET col='          'psql "$URL" -X -At -c "update orgs set id=id where false"'
run allow 'prose mentioning psql + SET'  'echo "the psql hook denies SET x = 1 examples" > note.md'
run deny  'SET after semicolon'          'psql "$URL" -c "select 1; set statement_timeout = 0"'
run deny  'SET at heredoc line start'    $'psql "$URL" <<\'SQL\'\nselect 1;\nSET statement_timeout TO 0;\nSQL'

rm -rf "$tmp"
echo; [[ $fails -eq 0 ]] && echo "all passed" || { echo "$fails failed"; exit 1; }
