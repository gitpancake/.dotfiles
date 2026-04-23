#!/usr/bin/env bash
# Rank recent Claude Code sessions by estimated API-equivalent $ cost.
#
# Reads ~/.claude/projects/**/*.jsonl, tallies each assistant turn's token
# usage against Anthropic list pricing per model, and prints the top N
# sessions over the last N days. Useful for post-mortem on what burned
# your Max-plan buckets.
#
# Usage: transcript-costs.sh [days=7] [top=10]

set -u

days=${1:-7}
top=${2:-10}
projectsDir="${HOME}/.claude/projects"

cutoffSecs=$(( $(date +%s) - days * 86400 ))

statMtime() {
  stat -f %m "$1" 2>/dev/null || stat -c %Y "$1"
}

shopt -s nullglob
rows=$(
  for file in "$projectsDir"/*/*.jsonl "$projectsDir"/*.jsonl; do
    (( $(statMtime "$file") < cutoffSecs )) && continue

    jq -sr --arg file "$file" '
      # Anthropic list pricing per million tokens:
      # [input, cache_creation, cache_read, output]
      def priceFor($model):
        if   ($model | test("opus"))  then [15,   18.75, 1.50, 75]
        elif ($model | test("haiku")) then [0.80, 1,     0.08, 4]
        else                               [3,    3.75,  0.30, 15]  # sonnet default
        end;

      [ .[] | select(.type == "assistant" and .message.usage != null) ] as $turns
      | [ .[] | select(.type == "user")
              | .message.content
              | select(type == "string") ] as $prompts
      | (
          # Prefer first real prose prompt (skip <caveat>/<command-*> markers)
          ([ $prompts[] | select(startswith("<") | not) ][0])
          # Fall back to slash-command name if session was kicked off by one
          // ([ $prompts[] | try (capture("<command-name>(?<c>[^<]+)</command-name>") | .c) catch empty ][0])
          // "(no prompt)"
        ) as $firstPrompt
      | ([ .[] | select(.timestamp != null) | .timestamp ][0] // "") as $startedAt
      | (reduce $turns[] as $t (
          {cost: 0, tokens: 0, turns: 0, models: {}};
          priceFor($t.message.model // "sonnet") as $p
          | .cost   += ( ($t.message.usage.input_tokens // 0)                * $p[0]
                       + ($t.message.usage.cache_creation_input_tokens // 0) * $p[1]
                       + ($t.message.usage.cache_read_input_tokens // 0)     * $p[2]
                       + ($t.message.usage.output_tokens // 0)               * $p[3]
                       ) / 1e6
          | .tokens += ( ($t.message.usage.input_tokens // 0)
                       + ($t.message.usage.cache_creation_input_tokens // 0)
                       + ($t.message.usage.cache_read_input_tokens // 0)
                       + ($t.message.usage.output_tokens // 0) )
          | .turns  += 1
          | .models[$t.message.model // "?"] = ((.models[$t.message.model // "?"] // 0) + 1)
        )) as $s
      | ($s.models | to_entries | sort_by(-.value)[0].key // "?") as $dominantModel
      | [ $s.cost, $s.tokens, $s.turns, $dominantModel, ($startedAt | .[0:10]), ($firstPrompt | gsub("\n"; " ") | .[0:60]) ]
      | @tsv
    ' "$file"
  done
)

if [[ -z "$rows" ]]; then
  echo "No sessions in the last ${days} day(s)."
  exit 0
fi

echo "$rows" \
  | sort -t$'\t' -k1 -gr \
  | head -n "$top" \
  | awk -F'\t' -v days="$days" '
      BEGIN {
        printf "Top sessions — last %d day(s)\n", days
        printf "%-7s %8s %5s %-14s %-10s %s\n", "COST", "TOKENS", "TURNS", "MODEL", "STARTED", "FIRST PROMPT"
      }
      {
        cost=$1; tokens=$2; turns=$3; model=$4; started=$5; prompt=$6
        sub(/^claude-/, "", model)
        printf "$%-6.2f %7.1fM %5d %-14s %-10s %s\n", cost, tokens/1e6, turns, model, started, prompt
      }
      END {
        if (NR == 0) print "(none)"
      }'

total=$(echo "$rows" | awk -F'\t' '{sum += $1} END {printf "%.2f", sum}')
sessions=$(echo "$rows" | wc -l | tr -d ' ')
printf "\nTotal: $%s across %s session(s)\n" "$total" "$sessions"
