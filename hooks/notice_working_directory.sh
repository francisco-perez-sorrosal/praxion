#!/bin/sh
# Tell the agent, in one line, when a Bash call has left the session somewhere
# other than its home, so relative paths are not silently read against the
# wrong directory.
#
# Usage: notice_working_directory.sh <pre|post>   (the hook payload on stdin)
#   pre   PreToolUse, every tool: resolves a move the moving call's own payload
#         did not show, and takes a move no Bash call made (a worktree entered
#         or left) as the session's new home
#   post  PostToolUse and PostToolUseFailure, Bash: announces a move the call's
#         payload already shows, or marks a call whose command may have moved
#         the session (a call the user cancels fires neither: the next `pre` sees it)
#
# Home is the directory the harness last put the session in; the notice names
# the new directory and home, and a session back at home hears nothing.
#
# One record per main-conversation session, three lines (`v1 settled|moving`,
# home, last seen directory), under the per-user config directory and never in
# the project. It is written only on a transition, through a temporary file and
# `mv`, so parallel tool calls never read half a record. A known limit: that
# makes the record whole, not the notice once-only; two `pre` calls running at
# once while the record is `moving` can both announce the same move.
#
# Cost: this runs on every tool call of every session, so the silent path is
# builtins only (one `cat` for stdin): no interpreter, no write, no `git`.
#
# Fail-open: always exit 0, never a word on stderr. A payload it cannot read
# with certainty adds nothing.

exec 2>/dev/null
# Patterns match bytes, so `[!A-Za-z0-9_-]` and `[[:cntrl:]]` let no locale widen them.
LC_ALL=C

# A directory-change word starts the command value or follows whitespace or a
# shell operator, and ends the value or meets whitespace or an operator. A
# false match costs two small writes, resolved silently at the next `pre`.
WORD_START='[" ;&|(]'
WORD_END='[" ;&|)]'
ESCAPED_SPACE='\\[nt]'

main() {
    event=$1
    input=$(cat)
    case $event in pre | post) ;; *) return ;; esac
    # A subagent's `cd` is not the session's: its cwd resets between calls. The
    # key is matched anywhere, so a main-session call whose `tool_input` holds an
    # `agent_id` key is skipped too and a pending notice waits one call: telling
    # the top-level key apart needs the payload's nesting (no key order is
    # documented), which no builtin reads.
    case $input in *'"agent_id"'*) return ;; esac
    first_value session_id || return
    session=$value
    first_value cwd || return
    cwd=$value
    case $session in '' | *[!A-Za-z0-9_-]*) return ;; esac
    is_clean_path "$cwd" || return
    config=${CLAUDE_CONFIG_DIR:-${HOME:+$HOME/.claude}}
    is_clean_path "$config" || return
    store=$config/praxion/cwd-notice
    record=$store/$session

    read_record
    decide
    [ "$to" = "$from" ] && [ "$to_home" = "$home" ] && [ "$to_last" = "$last" ] || write_record
    [ -n "$notice" ] && announce
}

# Sets value to the payload's first `"<key>":` string value. Both keys come
# before `tool_input` in the harness's payload, so no command text can supply
# them; a value holding an escape is cut short at its `\"` and refused by its
# caller. A raw `"<key>":` never occurs inside a JSON string, only escaped.
first_value() {
    case $input in *\""$1"\":*) ;; *) return 1 ;; esac
    value=${input#*\""$1"\":}
    value=${value#"${value%%[! ]*}"}
    case $value in \"*) ;; *) return 1 ;; esac
    value=${value#\"}
    value=${value%%\"*}
}

# An absolute path the notice can carry inside JSON without an interpreter.
is_clean_path() {
    case $1 in /*) ;; *) return 1 ;; esac
    case $1 in *\\* | *\"* | *[[:cntrl:]]*) return 1 ;; esac
}

# Sets from (unseen, settled or moving), home and last. A record of any other
# shape reads as unseen and is rewritten.
read_record() {
    from=unseen home='' last=''
    [ -f "$record" ] || return
    { IFS= read -r tag && IFS= read -r home && IFS= read -r last; } <"$record" || return
    is_clean_path "$home" && is_clean_path "$last" || return
    case $tag in
        'v1 settled') from=settled ;;
        'v1 moving') from=moving ;;
    esac
}

# The transition table: sets to, to_home, to_last and notice.
decide() {
    to=$from to_home=$home to_last=$last notice=''
    if [ "$from" = unseen ]; then
        to=settled to_home=$cwd to_last=$cwd
    elif same_place "$cwd" "$last"; then
        case $event:$from in
            pre:moving) to=settled ;;
            post:settled) holds_directory_change && to=moving ;;
        esac
    elif [ "$event:$from" = pre:settled ]; then
        # Seen first at a `pre` with no Bash call pending: the harness moved it.
        to=settled to_home=$cwd to_last=$cwd
    else
        to=settled to_last=$cwd
        same_place "$cwd" "$home" || notice="Working directory: a Bash command left this session in $cwd; its root is $home. Relative paths and commands now resolve against $cwd."
    fi
}

# The same string, or the same physical directory (the hook's own directory
# moves, which nothing after it depends on).
same_place() {
    [ "$1" = "$2" ] && return 0
    cd -P "$1" || return 1
    first=$PWD
    cd -P "$2" || return 1
    [ "$first" = "$PWD" ]
}

# Whether the command value (up to the next top-level key the payload holds)
# holds `cd`, `pushd` or `popd` as a word.
holds_directory_change() {
    command=${input#*\"command\":}
    command=${command%%\"description\":*}
    command=${command%%\"tool_response\":*}
    command=${command%%\"error\":*}
    for word in cd pushd popd; do
        case $command in
            *$WORD_START"$word"$WORD_END* | *$WORD_START"$word"$ESCAPED_SPACE* | \
                *$ESCAPED_SPACE"$word"$WORD_END* | *$ESCAPED_SPACE"$word"$ESCAPED_SPACE*)
                return 0 ;;
        esac
    done
    return 1
}

write_record() {
    if [ "$from" = unseen ]; then
        mkdir -p "$store" || return
        # Once per new session: records of sessions gone quiet for a week.
        find "$store" -type f -mtime +7 -exec rm -f {} +
    fi
    staged=$record.$$
    if printf 'v1 %s\n%s\n%s\n' "$to" "$to_home" "$to_last" >"$staged"; then
        mv -f "$staged" "$record" || rm -f "$staged"
    else
        rm -f "$staged"
    fi
}

announce() {
    name=PreToolUse
    if [ "$event" = post ]; then
        # One `post` follows a call that failed too; its output names that event.
        name=PostToolUse
        first_value hook_event_name && [ "$value" = PostToolUseFailure ] && name=$value
    fi
    printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' \
        "$name" "$notice"
}

main "$1"
exit 0
