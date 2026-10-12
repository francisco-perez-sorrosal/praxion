#!/bin/bash
# Ablation harness: per config, record /context and real first-request usage.
S=/private/tmp/claude-501/-Users-fperez-dev-praxion/b4da2e82-a25e-45c1-8855-0425f72ad3ed/scratchpad
OUT=$S/ablate
P=/Users/fperez/dev/praxion
OTHERS='{"enabledPlugins":{"code-simplifier@claude-plugins-official":false,"plugin-dev@claude-plugins-official":false,"code-review@claude-plugins-official":false,"claude-code-setup@claude-plugins-official":false,"claude-mermaid@claude-mermaid":false,"obsidian@obsidian-skills":false,"crvntx@bit-agora":false,"cv@bit-agora":false,"cv-forge@bit-agora":false}}'
run() { # name dir extra-args...
  local name=$1 dir=$2; shift 2
  ( cd "$dir" && timeout 150 claude -p "/context" "$@" > $OUT/$name.context.md 2>&1 )
  ( cd "$dir" && timeout 150 claude -p "Reply with the single word ok." --output-format json "$@" > $OUT/$name.usage.json 2>$OUT/$name.err )
  python3 -c "
import json,sys
try:
  u=json.load(open('$OUT/$name.usage.json'))['usage']; print('$name', u['input_tokens']+u['cache_creation_input_tokens']+u['cache_read_input_tokens'], 'read', u['cache_read_input_tokens'])
except Exception as e: print('$name ERR', e)"
}
case "$1" in
  bare) run bare $P --bare ;;
  empty) run empty $S/emptyproj ;;
  no_others) run no_others $P --settings "$OTHERS" ;;
  no_praxion) run no_praxion $P --settings '{"enabledPlugins":{"praxion@bit-agora":false}}' ;;
  no_automem) run no_automem $P --settings '{"autoMemoryEnabled":false}' ;;
  no_skills) run no_skills $P --disable-slash-commands ;;
  baseline) run baseline $P ;;
  no_mcp) run no_mcp $P --strict-mcp-config ;;
  floor) run floor $S/emptyproj --setting-sources "" ;;
  tools_eager) ENABLE_TOOL_SEARCH=false run tools_eager $P ;;
esac
