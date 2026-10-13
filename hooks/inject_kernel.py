#!/usr/bin/env python3
"""SubagentStart hook: deliver one injected string of a role's kernel.

Registered once per slot (``--slot N``): slot N prints the Nth string a spawn
receives, so the kernel and the project's own ``CLAUDE.md`` arrive as several
strings under the 10,000-character cap. The strings are, in order, the role's
kernel strings from ``claude/kernels/index.json`` and then the project root
``CLAUDE.md`` split at line ends into numbered parts. Stdout is empty or one
``hookSpecificOutput`` JSON; the exit code is always 0, so a failing hook can
never block a spawn.

Who receives anything: an agent of this plugin (``praxion:<role>``) whose adoption
status in the running plugin's ledger (``.ai-state/kernel_adoption.yaml``) is
``trial`` or ``switched``. A host-native agent, another plugin's agent of the same
role name, a role at no status, a plugin with no ledger or no index, and an unknown
index schema all receive nothing. There is no disable variable: a switched role
must never be silenced.

Where things are found, never from this script's own location: the plugin root
from ``CLAUDE_PLUGIN_ROOT`` (the kernel and the ledger are the running plugin's,
never a copy in the project) and the project from the payload ``cwd`` through git.
The hook reads two files of the plugin, so it needs only the standard library and
any ``python3`` from 3.9: the ledger is scanned line by line for the shape the
ledger's writers emit (``roles:`` then ``  <role>:`` then ``    status: <status>``,
no YAML parser), the index is JSON. A status copied into the index is informative
only; a stale index is the manifest checker's finding.

The project file is delivered as the harness would load it, minus what the role
does not inherit: a line of the form ``@<relative path>`` is replaced, once and
not recursively, by that file's text when it is a regular file inside the project;
the file itself is read only when it is a regular file inside the project after
symlinks are resolved, and never beyond the bytes the reserved slots can carry.

Every slot computes the whole delivery from the same inputs and prints its own
part: a delivery any of whose strings passes the cap is refused by every slot
alike, so a role never receives part of a kernel.

Delivery evidence has two channels. Every injected string begins with a one-line
marker (its own paragraph) carrying the kernel version and its slot number: the adherence eval
cannot read a sandbox's observation log, so the marker in the transcript is the
only evidence it can read. Slot 1 also appends the single ``kernel_injected``
row to the project's observation log (none for a spawn that receives nothing).

Order of delivery across slots is not guaranteed (hooks run in parallel and
their strings arrive in completion order), so the marker names the slot and each
project-file part names its place in the file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import namedtuple
from datetime import datetime, timezone

PLUGIN_NAMESPACE = "praxion"
ACTIVE_STATUSES = frozenset({"trial", "switched"})
INDEX_SCHEMA = 1
INDEX_PATH = ("claude", "kernels", "index.json")
LEDGER_PATH = (".ai-state", "kernel_adoption.yaml")
PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
PROJECT_FILE_NAME = "CLAUDE.md"
PROJECT_MODULE = "project-claude-md"
KERNEL_ROW = "kernel_injected"
GIT_TIMEOUT_SECONDS = 3

# One injected string may not exceed the harness's inline limit; beyond it the
# harness saves the text to a file and shows a preview, which is not delivery.
INJECTION_CAP = 10_000
# The harness counts the cap in UTF-16 code units (as JavaScript strings do), so a
# character outside the Basic Multilingual Plane weighs two.
BMP_LIMIT = 0xFFFF
# Room a project-file part leaves for the slot marker, the part header and an
# overflow notice, so a part of this much file text always fits the cap.
FRAMING_RESERVE = 1_000
PART_TEXT_LIMIT = INJECTION_CAP - FRAMING_RESERVE
LINE_CONTINUED = "\n[line continued]\n"

# The marker is framing, not kernel prose: it stands as its own paragraph and stays under 24
# characters (the length below which a paragraph is too short to identify its source), so a
# comparison of what a role received against the committed kernel text sets it aside. Eight
# hexadecimal characters of the kernel version identify it; the row carries the whole version.
MARKER = "[praxion {version} #{slot}]"
MARKER_VERSION_CHARS = 8
MARKER_GAP = "\n\n"
# A kernel string ends its last paragraph, so strings that reach a reader joined end to end
# (their order and joining are the harness's) never fuse one string's last paragraph into the
# next string's marker.
STRING_END = "\n\n"
PART_HEADER = "[project CLAUDE.md, part {number} of {total}]"
OMITTED_NOTICE = "\n[project CLAUDE.md: {qualifier}{omitted} further part(s) were not delivered; read {path} for the rest]\n"
AT_LEAST = "at least "

# A kernel the hook may deliver, parsed once from the index: its version, how many
# slots are registered, and its strings (each with the modules it packs).
Kernel = namedtuple("Kernel", ("version", "slots", "strings"))
KernelString = namedtuple("KernelString", ("text", "modules"))
# The project's root instruction file as read: where, what it says, and whether that is all of
# it (a file past the read bound is held only as far as the bound).
ProjectFile = namedtuple("ProjectFile", ("path", "text", "complete"))
# One string to inject (before its marker), and which module or part it carries.
Piece = namedtuple("Piece", ("body", "module", "part"))
# What a spawn receives: the pieces in slot order and, when a project file was
# delivered, its row summary ({chars, parts, omitted}).
Delivery = namedtuple("Delivery", ("pieces", "project_file"))
# A piece as injected, marker included.
Injection = namedtuple("Injection", ("text", "module", "part"))

_LINE = re.compile(r"[^\n]*\n|[^\n]+")
# The ledger's generated shape (block style): the `roles:` key at the margin, a role at two
# spaces, its `status:` at four. Anything else is not read.
_LEDGER_ROLES = re.compile(r"roles:[ \t]*(#.*)?$")
_LEDGER_ROLE = re.compile(r"  ([\w.-]+):[ \t]*(#.*)?$")
_LEDGER_STATUS = re.compile(r"    status:[ \t]*([\w-]+)[ \t]*(#.*)?$")
# A project-file line that imports another file, as the harness reads it: `@path` at line start.
_IMPORT_LINE = re.compile(r"^@(?P<path>\S+)[ \t]*(?=\r?$)", re.MULTILINE)
_FINAL_LINE_END = re.compile(r"\r?\n\Z")


def main(argv=None):
    """Print slot N's string for the spawn on stdin; always return 0."""
    try:
        slot = parse_slot(sys.argv[1:] if argv is None else argv)
        payload = parse_payload(sys.stdin.read())
        if slot is not None and payload is not None:
            run(slot, payload, os.environ)
    except Exception:
        pass
    return 0


def run(slot, payload, environ):
    """The edge: gather what the spawn needs, compute its delivery, emit and record."""
    role = role_of(payload.get("agent_type"))
    plugin_root = environ.get("CLAUDE_PLUGIN_ROOT")
    if role is None or not plugin_root:
        return
    if adoption_status(read_ledger(plugin_root), role) not in ACTIVE_STATUSES:
        return
    kernel = parse_kernel(load_index(plugin_root), role)
    if kernel is None or slot > kernel.slots:
        return
    # Every slot reads the project and plans the whole delivery: whether it is refused for
    # passing the cap must come out the same in each, or a role would get part of a kernel.
    project = read_project_file(payload.get("cwd"), kernel.slots * INJECTION_CAP)
    delivery = plan_delivery(kernel, plugin_root, project)
    injections = render(kernel.version, delivery)
    if slot > len(injections):
        return
    emit(injections[slot - 1].text)
    if slot == 1:
        record_delivery(payload, role, kernel.version, injections, delivery.project_file, environ)


# -- Pure core: who receives what ---------------------------------------------------


def parse_slot(argv):
    """The slot number after ``--slot``, or None when absent or not a positive integer."""
    if len(argv) == 2 and argv[0] == "--slot" and argv[1].isdigit() and int(argv[1]) > 0:
        return int(argv[1])
    return None


def parse_payload(text):
    """The SubagentStart payload as a dict, or None for anything else."""
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def role_of(agent_type):
    """The role of an agent of this plugin (``praxion:<role>``); None for any other agent."""
    if not isinstance(agent_type, str):
        return None
    namespace, separator, role = agent_type.partition(":")
    return role if separator and namespace == PLUGIN_NAMESPACE and role else None


def adoption_status(ledger_text, role):
    """The role's status in the ledger's text, or None; a ledger that does not read gives None.

    Only the ledger's own generated shape is read (see ``_LEDGER_*``): the first ``status:``
    under the role's key inside the top-level ``roles:`` block.
    """
    in_roles, current = False, None
    for line in ledger_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            in_roles, current = bool(_LEDGER_ROLES.match(line)), None
        elif in_roles and (named := _LEDGER_ROLE.match(line)):
            current = named.group(1)
        elif in_roles and current == role and (found := _LEDGER_STATUS.match(line)):
            return found.group(1)
    return None


def parse_kernel(index, role):
    """The kernel the index holds for a role; None when there is none or the index is unreadable.

    Whether the role is to receive it is the ledger's decision, not the index's.
    """
    if not isinstance(index, dict) or index.get("schema") != INDEX_SCHEMA:
        return None
    version, slots, roles = index.get("kernel_version"), index.get("slots"), index.get("roles")
    entry = roles.get(role) if isinstance(roles, dict) else None
    if not isinstance(entry, dict):
        return None
    strings = entry.get("strings")
    if not (isinstance(version, str) and isinstance(slots, int) and isinstance(strings, list)):
        return None
    if not strings or not all(isinstance(text, str) for text in strings):
        return None
    labels = module_labels(entry.get("modules"), len(strings))
    kernel_strings = tuple(KernelString(strings[n], labels[n]) for n in range(len(strings)))
    return Kernel(version, slots, kernel_strings)


def module_labels(labels, count):
    """The modules each of ``count`` kernel strings packs, from the index; positional names if absent."""
    if isinstance(labels, list) and len(labels) == count:
        return [str(label) for label in labels]
    return [f"kernel-{number}" for number in range(1, count + 1)]


def plan_delivery(kernel, plugin_root, project):
    """The kernel strings with the plugin location written out, then the project file's parts."""
    pieces = [
        Piece(
            string.text.replace(PLUGIN_ROOT_VARIABLE, plugin_root) + STRING_END,
            string.modules,
            None,
        )
        for string in kernel.strings
    ]
    if project is None or not project.text.strip():
        return Delivery(tuple(pieces), None)
    room = kernel.slots - len(kernel.strings)
    parts, summary = project_parts(project, room)
    return Delivery(tuple(pieces + parts), summary)


def project_parts(project, room):
    """The project file as numbered parts that fit ``room`` slots, and its row summary.

    Whatever does not fit is named in the last delivered part's notice, so the
    role knows to read the file; the row records how many parts were left out.
    """
    chunks = split_chunks(project.text, PART_TEXT_LIMIT)
    delivered = chunks[: max(room, 0)]
    omitted = len(chunks) - len(delivered)
    parts = [
        Piece(
            PART_HEADER.format(number=number, total=len(chunks)) + "\n" + chunk,
            PROJECT_MODULE,
            number,
        )
        for number, chunk in enumerate(delivered, 1)
    ]
    if omitted and parts:
        qualifier = "" if project.complete else AT_LEAST
        notice = OMITTED_NOTICE.format(qualifier=qualifier, omitted=omitted, path=project.path)
        parts[-1] = parts[-1]._replace(body=parts[-1].body + notice)
    return parts, {"chars": units(project.text), "parts": len(parts), "omitted": omitted}


def split_chunks(text, limit):
    """``text`` as chunks of at most ``limit`` UTF-16 units that concatenate back to it.

    Cuts fall at line ends. The one exception is a single line longer than
    ``limit``, which is cut inside the line and marked at each cut.
    """
    chunks, current, size = [], "", 0
    for line in _LINE.findall(text):
        width = units(line)
        if width > limit:
            if current:
                chunks.append(current)
            *cut, current = cut_long_line(line, limit)
            chunks.extend(cut)
            size = units(current)
        elif current and size + width > limit:
            chunks.append(current)
            current, size = line, width
        else:
            current, size = current + line, size + width
    if current:
        chunks.append(current)
    return chunks


def cut_long_line(line, limit):
    """A line longer than ``limit`` units as pieces; every piece but the last ends in the marker.

    A cut never falls inside a character, so a piece may fall one unit short of the limit.
    """
    room = limit - units(LINE_CONTINUED)
    pieces, start, used = [], 0, 0
    for index, char in enumerate(line):
        width = units(char)
        if used + width > room:
            pieces.append(line[start:index] + LINE_CONTINUED)
            start, used = index, 0
        used += width
    pieces.append(line[start:])
    return pieces


def units(text):
    """The length of ``text`` in UTF-16 code units, which is how the harness counts its cap."""
    return len(text) + sum(1 for char in text if ord(char) > BMP_LIMIT)


def render(version, delivery):
    """Each piece as injected: its marker, then its body. Empty when any would pass the cap.

    A string over the cap is refused with the whole delivery, never trimmed: a
    role either receives its complete kernel or none, and the liveness check
    reports the spawn that left no row.
    """
    injections = tuple(
        Injection(
            MARKER.format(version=version[:MARKER_VERSION_CHARS], slot=slot)
            + MARKER_GAP
            + piece.body,
            piece.module,
            piece.part,
        )
        for slot, piece in enumerate(delivery.pieces, 1)
    )
    return () if any(units(each.text) > INJECTION_CAP for each in injections) else injections


def kernel_row(payload, role, version, injections, project_file, timestamp):
    """The ``kernel_injected`` row for a delivering spawn."""
    return {
        "timestamp": timestamp,
        "session_id": payload.get("session_id"),
        "event_type": KERNEL_ROW,
        "agent_type": payload.get("agent_type"),
        "agent_id": payload.get("agent_id"),
        "role": role,
        "kernel_version": version,
        "strings": [
            {"module": each.module, "part": each.part, "chars": units(each.text)}
            for each in injections
        ],
        "project_file": project_file,
    }


# -- Effects at the edge -------------------------------------------------------------


def load_index(plugin_root):
    """The running plugin's kernel index as parsed JSON; None when absent or unreadable."""
    try:
        with open(os.path.join(plugin_root, *INDEX_PATH), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def read_ledger(plugin_root):
    """The running plugin's adoption ledger as text; empty when absent or unreadable."""
    try:
        with open(os.path.join(plugin_root, *LEDGER_PATH), encoding="utf-8") as handle:
            return handle.read()
    except (OSError, ValueError):
        return ""


def read_project_file(cwd, bound):
    """The root ``CLAUDE.md`` of the git working tree holding ``cwd``, imports expanded.

    None when there is none, or when it is not a regular file inside the working tree.
    ``bound`` caps the characters read from the file and from its imports.
    """
    root = git_toplevel(cwd)
    if root is None:
        return None
    path = os.path.join(root, PROJECT_FILE_NAME)
    text = read_inside(root, path, bound)
    if text is None:
        return None
    expanded = expand_imports(text, root, bound)
    return ProjectFile(path, expanded, len(expanded) < bound)


def expand_imports(text, root, bound):
    """``text`` with each ``@<relative path>`` line replaced by that file's text, once.

    Not recursive: an import inside an imported file stays as written. A line that
    does not name a regular file inside ``root`` stays as written too, and so do
    the lines after ``bound`` characters have been imported.
    """
    pieces, cursor, imported_chars = [], 0, 0
    for found in _IMPORT_LINE.finditer(text):
        if imported_chars >= bound:
            break
        imported = read_import(root, found.group("path"), bound - imported_chars)
        if imported is not None:
            pieces += [text[cursor : found.start()], imported]
            cursor, imported_chars = found.end(), imported_chars + len(imported)
    pieces.append(text[cursor:])
    return "".join(pieces)


def read_import(root, relative, bound):
    """An imported file's text less its final line end (the importing line keeps its own)."""
    if os.path.isabs(relative) or relative.startswith("~"):
        return None
    text = read_inside(root, os.path.join(root, relative), bound)
    return None if text is None else _FINAL_LINE_END.sub("", text, count=1)


def read_inside(root, path, bound):
    """At most ``bound`` characters of the regular file at ``path``, which must resolve inside ``root``.

    Verbatim: the file's own line endings are kept and undecodable bytes are replaced.
    None for anything else (a directory, a pipe, a link out of the tree, an unreadable file).
    """
    try:
        real, base = os.path.realpath(path), os.path.realpath(root)
        if os.path.commonpath([real, base]) != base or not os.path.isfile(real):
            return None
        with open(real, encoding="utf-8", errors="replace", newline="") as handle:
            return handle.read(bound)
    except (OSError, ValueError):
        return None


def git_toplevel(cwd):
    """The working tree root above ``cwd``, or None outside git or on any failure."""
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        return None
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    root = done.stdout.strip()
    return root if done.returncode == 0 and root else None


def emit(text):
    """Print the hook's one JSON object: ``text`` as the spawn's added context."""
    output = {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}}
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()


def record_delivery(payload, role, version, injections, project_file, environ):
    """Append the spawn's one ``kernel_injected`` row; no row where no log serves the project."""
    try:
        from _observation_log import writer
        from _observation_log.location import locate
        from _observation_log.registry import EventClass

        location = locate(payload.get("cwd"))
        if location is None:
            return
        timestamp = datetime.now(timezone.utc).isoformat()
        row = kernel_row(payload, role, version, injections, project_file, timestamp)
        writer.record(location.state_dir, EventClass.KERNEL_INJECTED, row, env=environ)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
