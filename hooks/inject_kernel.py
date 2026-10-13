#!/usr/bin/env python3
"""SubagentStart hook: deliver one injected string of a role's kernel.

Registered once per slot (``--slot N``): slot N prints the Nth string a spawn
receives, so the kernel and the project's own ``CLAUDE.md`` arrive as several
strings under the 10,000-character cap. The strings are, in order, the role's
kernel strings from ``claude/kernels/index.json`` and then the project root
``CLAUDE.md`` split at line ends into numbered parts. Stdout is empty or one
``hookSpecificOutput`` JSON; the exit code is always 0, so a failing hook can
never block a spawn.

Who receives anything: an agent of this plugin (``praxion:<role>``) whose index
status is ``trial`` or ``switched``. A host-native agent, another plugin's agent
of the same role name, a role at no status, a plugin with no index, and an
unknown index schema all receive nothing. There is no disable variable: a
switched role must never be silenced.

Where things are found, never from this script's own location: the plugin root
from ``CLAUDE_PLUGIN_ROOT`` (the kernel is the running plugin's, never a copy
in the project) and the project from the payload ``cwd`` through git. The hook
reads one file of the plugin, a JSON index, so it needs only the standard
library and any ``python3`` from 3.9. The ledger is projected into the index by
the generator; a stale index is the manifest checker's finding.

Delivery evidence has two channels. Every injected string begins with a one-line
marker carrying the kernel version and its slot number: the adherence eval
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
PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
PROJECT_FILE_NAME = "CLAUDE.md"
PROJECT_MODULE = "project-claude-md"
KERNEL_ROW = "kernel_injected"
GIT_TIMEOUT_SECONDS = 3

# One injected string may not exceed the harness's inline limit; beyond it the
# harness saves the text to a file and shows a preview, which is not delivery.
INJECTION_CAP = 10_000
# Room a project-file part leaves for the slot marker, the part header and an
# overflow notice, so a part of this much file text always fits the cap.
FRAMING_RESERVE = 1_000
PART_TEXT_LIMIT = INJECTION_CAP - FRAMING_RESERVE
LINE_CONTINUED = "\n[line continued]\n"

MARKER = "[praxion kernel version={version} slot={slot}]"
PART_HEADER = "[project CLAUDE.md, part {number} of {total}]"
OMITTED_NOTICE = "\n[project CLAUDE.md: {omitted} further part(s) were not delivered; read {path} for the rest]\n"

# A kernel the hook may deliver, parsed once from the index: its version, how many
# slots are registered, and its strings (each with the modules it packs).
Kernel = namedtuple("Kernel", ("version", "slots", "strings"))
KernelString = namedtuple("KernelString", ("text", "modules"))
# The project's root instruction file as read: where, and what it says.
ProjectFile = namedtuple("ProjectFile", ("path", "text"))
# One string to inject (before its marker), and which module or part it carries.
Piece = namedtuple("Piece", ("body", "module", "part"))
# What a spawn receives: the pieces in slot order and, when a project file was
# delivered, its row summary ({chars, parts, omitted}).
Delivery = namedtuple("Delivery", ("pieces", "project_file"))
# A piece as injected, marker included.
Injection = namedtuple("Injection", ("text", "module", "part"))

_LINE = re.compile(r"[^\n]*\n|[^\n]+")


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
    kernel = parse_kernel(load_index(plugin_root), role)
    if kernel is None or slot > kernel.slots:
        return
    # Kernel strings need no project: only slot 1 (the row) and the slots past
    # the kernel strings pay for the git call and the file read.
    needs_project = slot == 1 or slot > len(kernel.strings)
    project = read_project_file(payload.get("cwd")) if needs_project else None
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


def parse_kernel(index, role):
    """The kernel a role at trial or switched receives; None for everything else."""
    if not isinstance(index, dict) or index.get("schema") != INDEX_SCHEMA:
        return None
    version, slots, roles = index.get("kernel_version"), index.get("slots"), index.get("roles")
    entry = roles.get(role) if isinstance(roles, dict) else None
    if not isinstance(entry, dict) or entry.get("status") not in ACTIVE_STATUSES:
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
        Piece(string.text.replace(PLUGIN_ROOT_VARIABLE, plugin_root), string.modules, None)
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
        notice = OMITTED_NOTICE.format(omitted=omitted, path=project.path)
        parts[-1] = parts[-1]._replace(body=parts[-1].body + notice)
    return parts, {"chars": len(project.text), "parts": len(parts), "omitted": omitted}


def split_chunks(text, limit):
    """``text`` as chunks of at most ``limit`` characters that concatenate back to it.

    Cuts fall at line ends. The one exception is a single line longer than
    ``limit``, which is cut inside the line and marked at each cut.
    """
    chunks, current = [], ""
    for line in _LINE.findall(text):
        if len(line) > limit:
            if current:
                chunks.append(current)
            *cut, current = cut_long_line(line, limit)
            chunks.extend(cut)
        elif current and len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


def cut_long_line(line, limit):
    """A line longer than ``limit`` as pieces; every piece but the last ends in the marker."""
    step = limit - len(LINE_CONTINUED)
    starts = range(0, len(line), step)
    pieces = [line[start : start + step] + LINE_CONTINUED for start in starts]
    pieces[-1] = pieces[-1][: -len(LINE_CONTINUED)]
    return pieces


def render(version, delivery):
    """Each piece as injected: its marker, then its body. Empty when any would pass the cap.

    A string over the cap is refused with the whole delivery, never trimmed: a
    role either receives its complete kernel or none, and the liveness check
    reports the spawn that left no row.
    """
    injections = tuple(
        Injection(
            MARKER.format(version=version, slot=slot) + "\n" + piece.body,
            piece.module,
            piece.part,
        )
        for slot, piece in enumerate(delivery.pieces, 1)
    )
    return () if any(len(each.text) > INJECTION_CAP for each in injections) else injections


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
            {"module": each.module, "part": each.part, "chars": len(each.text)}
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


def read_project_file(cwd):
    """The root ``CLAUDE.md`` of the git working tree holding ``cwd``; None when there is none."""
    root = git_toplevel(cwd)
    if root is None:
        return None
    path = os.path.join(root, PROJECT_FILE_NAME)
    try:
        # newline="" keeps the file's own line endings: it arrives verbatim.
        with open(path, encoding="utf-8", errors="replace", newline="") as handle:
            return ProjectFile(path, handle.read())
    except OSError:
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
