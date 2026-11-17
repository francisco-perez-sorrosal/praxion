"""Whether a Bash hook payload's command records a git commit: `commit`, `not-a-commit` or `uncertain`.

The commit gate (`commit_gate.sh`) asks this reader only after its own text checks have
seen the word in the command, and skips its checkers on `not-a-commit` alone. Every
reading therefore leans one way: a form the reader cannot follow with certainty is
`uncertain`, never `not-a-commit`, because a real commit judged by no checker is the worse
failure and an extra checker run costs only time.

The command is read as a shell would split it, not matched as text: `shlex` in POSIX
mode with the control operators as punctuation, so `&&`, `||`, `;`, `|`, `&` and an
unquoted newline end a simple command while quotes, escaped quotes and a quoted newline
stay inside one word. Each simple command is then read by these rules, and the command's
verdict is the strongest of its simple commands' (`commit` over `uncertain` over
`not-a-commit`):

- a substitution anywhere in the text (`$(`, a backtick, `<(`, `>(`), or a simple command
  that starts with `eval`, is `uncertain`: the words that run are not in the text;
- a shell (`bash`, `sh`, `zsh`, `dash`, `ksh`, by basename, in any position) given `-c`
  is its script's verdict, read the same way, to a depth of two shells;
- every word that is `git` or ends `/git` starts an invocation: its global options are
  skipped, then `commit` is a commit, a built-in is not, anything else (an alias, an
  unknown option, a word holding `$`, no subcommand at all) is `uncertain`;
- what no rule above can follow keeps the checkers running: a word that holds a whole
  `git ... commit` script for another program, or, in a simple command with no
  invocation of its own, a bare `commit` word (`make commit`, `$GIT commit`, `xargs git`
  fed the word).

Runs on the gate's path as `python -I -S`: `json` and `shlex` only, Python 3.9 syntax.
"""

from __future__ import annotations

import json
import shlex
import sys

# Type checkers read this name as true; at run time `typing` and `collections.abc`
# stay unloaded, a few milliseconds of the gate's budget on every call that gets here.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

    Verdict = Literal["commit", "not-a-commit", "uncertain"]

_STRENGTH = {"not-a-commit": 0, "uncertain": 1, "commit": 2}

SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
MAX_SHELL_DEPTH = 2
SUBSTITUTIONS = ("$(", "`", "<(", ">(")

# A token made only of these is an operator: one holding `<` or `>` redirects (its target
# word names a file, never a command), any other ends the simple command.
SEPARATOR_CHARS = ";&|()\n"
REDIRECT_CHARS = "<>"
SHELL_WHITESPACE = " \t\r"

GIT_FLAGS = frozenset(
    "-p -P --paginate --no-pager --bare --no-replace-objects --literal-pathspecs"
    " --glob-pathspecs --noglob-pathspecs --icase-pathspecs --no-optional-locks"
    " --no-advice".split()
)
GIT_VALUE_OPTIONS = frozenset(
    "-C -c --git-dir --work-tree --namespace --exec-path --config-env --super-prefix".split()
)
# `git --list-cmds=builtins` of git 2.56, less `commit` itself and `commit-tree`, which
# records a commit object of its own and so is read `uncertain`. `commit_gate.sh` decides a
# few of these in shell before asking this reader; its list must stay inside this set, and
# test_commit_command.py holds it there.
GIT_BUILTINS = frozenset(
    """add am annotate apply archive backfill bisect blame branch bugreport bundle cat-file
    check-attr check-ignore check-mailmap check-ref-format checkout checkout--worker
    checkout-index cherry cherry-pick clean clone column commit-graph config count-objects
    credential credential-cache credential-cache--daemon credential-store describe diagnose
    diff diff-files diff-index diff-pairs diff-tree difftool fast-export fast-import fetch
    fetch-pack fmt-merge-msg for-each-ref for-each-repo format-patch format-rev fsck
    fsck-objects fsmonitor--daemon gc get-tar-commit-id grep hash-object help history hook
    index-pack init init-db interpret-trailers last-modified log ls-files ls-remote ls-tree
    mailinfo mailsplit maintenance merge merge-base merge-file merge-index merge-ours
    merge-recursive merge-recursive-ours merge-recursive-theirs merge-subtree merge-tree
    mktag mktree multi-pack-index mv name-rev notes pack-objects pack-redundant pack-refs
    patch-id pickaxe prune prune-packed pull push range-diff read-tree rebase receive-pack
    reflog refs remote remote-ext remote-fd repack replace replay repo rerere reset restore
    rev-list rev-parse revert rm send-pack shortlog show show-branch show-index show-ref
    sparse-checkout stage stash status stripspace submodule--helper switch symbolic-ref tag
    unpack-file unpack-objects update-index update-ref update-server-info upload-archive
    upload-archive--writer upload-pack url-parse var verify-commit verify-pack verify-tag
    version whatchanged worktree write-tree""".split()
)


def main() -> int:
    print(verdict_of(sys.stdin.buffer.read()))
    return 0


def verdict_of(payload: bytes) -> Verdict:
    """The verdict on a hook payload's `tool_input.command`; `uncertain` when it has none."""
    try:
        document = json.loads(payload)
    except ValueError:
        return "uncertain"
    tool_input = document.get("tool_input") if isinstance(document, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return classify(command) if isinstance(command, str) else "uncertain"


def classify(command: str) -> Verdict:
    """Whether running `command` in a POSIX shell records a git commit."""
    return _classify(command, depth=0)


def _classify(command: str, depth: int) -> Verdict:
    if any(marker in command for marker in SUBSTITUTIONS):
        return "uncertain"
    try:
        simple_commands = _simple_commands(command)
    except ValueError:
        return "uncertain"
    return _strongest([_simple_verdict(words, depth) for words in simple_commands])


def _simple_commands(command: str) -> list[list[str]]:
    """The words of each simple command, redirections and their targets left out."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=SEPARATOR_CHARS + REDIRECT_CHARS)
    lexer.whitespace = SHELL_WHITESPACE
    lexer.whitespace_split = True
    lexer.commenters = ""
    simple_commands: list[list[str]] = [[]]
    skip_target = False
    for token in list(lexer):
        if _is_operator(token):
            skip_target = any(char in REDIRECT_CHARS for char in token)
            if not skip_target:
                simple_commands.append([])
        elif skip_target:
            skip_target = False
        else:
            simple_commands[-1].append(token)
    return [words for words in simple_commands if words]


def _simple_verdict(words: Sequence[str], depth: int) -> Verdict:
    if _command_word(words) == "eval":
        return "uncertain"
    shells = [
        _shell_verdict(words[index + 1 :], depth)
        for index, word in enumerate(words)
        if _is_shell(word)
    ]
    scripts = [verdict for verdict in shells if verdict is not None]
    invocations = [
        _git_verdict(words[index + 1 :]) for index, word in enumerate(words) if _is_git(word)
    ]
    readings = scripts + invocations
    if not scripts and any(_holds_a_commit_script(word) for word in words):
        readings.append("uncertain")
    if not readings and "commit" in words:
        readings.append("uncertain")
    return _strongest(readings)


def _shell_verdict(args: Sequence[str], depth: int) -> Verdict | None:
    """The verdict on a shell's `-c` script, or None when the shell is given no `-c`."""
    index, given_c = 0, False
    while index < len(args) and args[index][:1] in ("-", "+") and args[index] != "--":
        option = args[index]
        if option in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            index += 1
        elif not option.startswith("--"):
            given_c = given_c or "c" in option
        index += 1
    if index < len(args) and args[index] == "--":
        index += 1
    if not given_c:
        return None
    if index >= len(args) or depth >= MAX_SHELL_DEPTH:
        return "uncertain"
    return _classify(args[index], depth + 1)


def _git_verdict(args: Sequence[str]) -> Verdict:
    """The verdict on one git invocation, given the words that follow the `git` word."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        option = args[index]
        if option in GIT_FLAGS:
            index += 1
        elif option.split("=", 1)[0] in GIT_VALUE_OPTIONS:
            index += 1 if "=" in option else 2
        else:
            return "uncertain"
    if index >= len(args):
        return "uncertain"
    subcommand = args[index]
    if subcommand == "commit":
        return "commit"
    return "not-a-commit" if subcommand in GIT_BUILTINS else "uncertain"


def _strongest(verdicts: Sequence[Verdict]) -> Verdict:
    return max(verdicts, key=_STRENGTH.__getitem__, default="not-a-commit")


def _is_operator(token: str) -> bool:
    return bool(token) and all(char in SEPARATOR_CHARS or char in REDIRECT_CHARS for char in token)


def _is_assignment(word: str) -> bool:
    name, equals, _ = word.partition("=")
    return bool(equals) and name.isidentifier()


def _command_word(words: Sequence[str]) -> str | None:
    return next((word for word in words if not _is_assignment(word)), None)


def _basename(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _is_git(word: str) -> bool:
    return _basename(word) == "git" and not _is_assignment(word)


def _is_shell(word: str) -> bool:
    return _basename(word) in SHELLS and not _is_assignment(word)


def _holds_a_commit_script(word: str) -> bool:
    """Whether one word is a script for another program that runs `git ... commit`."""
    return len(word.split()) > 1 and "git" in word and "commit" in word


if __name__ == "__main__":
    sys.exit(main())
