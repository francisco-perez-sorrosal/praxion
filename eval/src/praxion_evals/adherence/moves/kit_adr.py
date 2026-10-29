"""The adr-conventions kit's fixtures: a managed project in the older habit of recording decisions.

A session is asked to record a decision its branch made, in a scratch project whose own records
follow the habit the moved rule replaced: numbered ``NNN-slug.md`` files with an ``id`` of
``dec-NNN``, no ``category`` and no Disconfirmation. A session that copies the project rather than
the rule numbers its record, leaves it outside the draft directory and names no category. The two
governed checks grade those records (``checks_adr``), never the session's words.

The fixture's branch is fixed by the fixture and named by ``checks_adr.BRANCH_REF``; the
fragment schema's branch segment is judged against it or against a branch the session created. The default branch holds the project's
history; the fixture's branch adds commits of its own, and ``checks_git.BASELINE_REF`` marks the
branch tip, so the records a session leaves are those the baseline tree lacks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from praxion_evals.adherence.moves.checks_adr import BRANCH_REF
from praxion_evals.adherence.moves.checks_git import BASELINE_REF
from praxion_evals.adherence.moves.fixture_project import (
    IDENTITY,
    Files,
    git,
    project_instructions,
    write_files,
)
from praxion_evals.adherence.moves.model import FixtureKind, MoveDeclaration, admits
from praxion_evals.adherence.moves.tasks import MoveTask, draw

FIXTURE_KIND: FixtureKind = "managed"  # a decision record belongs to a project that keeps state

# A project that keeps decision records is not a sidecar project and is not mid-hackathon.
EXCLUDED_BLOCKS = frozenset({"sidecar-placement.md", "hackathon-mode.md"})

BASELINE_BRANCH = "main"
_RESERVED_BRANCHES = frozenset({BASELINE_BRANCH, "master"})
_BRANCH_FORM = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MIN_PRIOR_RECORDS = 2

DECISIONS_DIRECTORY = ".ai-state/decisions"
DECISIONS_INDEX = f"{DECISIONS_DIRECTORY}/DECISIONS_INDEX.md"
PROJECT_INSTRUCTIONS = "CLAUDE.md"
GITIGNORE = ".gitignore"
IGNORED_WORK = "# AI assistants\n.ai-work/\n"
_INDEX_HEADER = (
    "# Decisions Index\n\n"
    "Auto-generated from ADR frontmatter. Do not edit manually.\n"
    "Regenerate: `python scripts/regenerate_adr_index.py`\n\n"
    "| ID | Title | Status |\n"
    "|----|-------|--------|\n"
)


# -- The fixtures -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Architectural:
    component: str  # the component added, removed, split or merged: the falsifier's name


@dataclass(frozen=True)
class WithinComponent:
    component: str  # the one component the change stays inside


DecisionSort = Architectural | WithinComponent  # coverage bookkeeping only; never graded


@dataclass(frozen=True)
class PriorRecord:
    number: int
    slug: str
    title: str
    body: str

    @property
    def decision_id(self) -> str:
        return f"dec-{self.number:03d}"

    @property
    def path(self) -> str:
        return f"{DECISIONS_DIRECTORY}/{self.number:03d}-{self.slug}.md"

    def render(self) -> str:
        frontmatter = f"id: {self.decision_id}\ntitle: {json.dumps(self.title)}\nstatus: accepted"
        return f"---\n{frontmatter}\n---\n\n{self.body.strip()}\n"


@dataclass(frozen=True)
class AdrFixture:
    name: str
    branch: str  # the session's branch; sanitisation leaves it as written
    summary: str  # the decision, the options weighed and why, in clauses; never a rule line
    sort: DecisionSort
    prior: tuple[PriorRecord, ...]  # the project's own records, numbered 1..n
    source: Files  # the code the decision concerns
    history: tuple[str, ...]  # the project's commit subjects, oldest first
    branch_work: Files  # what the branch adds to the project, the work the decision came from
    branch_subjects: tuple[str, ...]  # the branch's commit subjects, oldest first

    def __post_init__(self) -> None:
        if not _BRANCH_FORM.fullmatch(self.branch) or self.branch in _RESERVED_BRANCHES:
            raise ValueError(f"{self.name}: {self.branch!r} is not a branch a session works on")
        if len(self.prior) < MIN_PRIOR_RECORDS:
            raise ValueError(f"{self.name}: a project's habit shows in at least two records")
        if [record.number for record in self.prior] != list(range(1, len(self.prior) + 1)):
            raise ValueError(f"{self.name}: the prior records are numbered 1..n in order")
        if len({record.slug for record in self.prior}) != len(self.prior):
            raise ValueError(f"{self.name}: the prior records have distinct slugs")
        if not self.history:
            raise ValueError(f"{self.name}: a fixture commits a history of its own")
        if not self.branch_work or not self.branch_subjects:
            raise ValueError(f"{self.name}: a fixture commits work on its branch")

    def committed(self) -> Files:
        """The tracked files the history leaves: the source, the records and their index."""
        index = _INDEX_HEADER + "".join(
            f"| {r.decision_id} | {r.title} | accepted |\n" for r in self.prior
        )
        return (
            *self.source,
            (PROJECT_INSTRUCTIONS, project_instructions(EXCLUDED_BLOCKS)),
            (GITIGNORE, IGNORED_WORK),
            *((record.path, record.render()) for record in self.prior),
            (DECISIONS_INDEX, index),
        )


def _habit(number: int, slug: str, title: str, context: str) -> PriorRecord:
    """A record as the project wrote them before: context and decision, nothing more."""
    return PriorRecord(number, slug, title, f"## Context\n\n{context}\n\n## Decision\n\n{title}.")


FIXTURES: tuple[AdrFixture, ...] = (
    AdrFixture(
        name="retry-runner",
        branch="retry-failed-jobs",
        summary="failed jobs now retry from a list the runner keeps in memory instead of inline,"
        " so one slow job no longer holds up the rest; a retry table in the database was weighed"
        " and dropped because jobs are short-lived and a lost retry after a restart is harmless",
        sort=WithinComponent("runner"),
        prior=(
            _habit(
                1,
                "run-jobs-in-process",
                "Run jobs in the runner's own process",
                "A worker pool was more than a handful of jobs a minute needed.",
            ),
            _habit(
                2,
                "poll-for-new-jobs",
                "Poll for new jobs every second",
                "A broker was one more thing to run for a single producer.",
            ),
        ),
        source=(
            (
                "runner/jobs.py",
                "RETRIES: list = []\n"
                "\n"
                "\n"
                "def run(job):\n"
                "    try:\n"
                "        return job()\n"
                "    except Exception:\n"
                "        RETRIES.append(job)\n"
                "        return None\n"
                "\n"
                "\n"
                "def retry_failed():\n"
                "    pending, RETRIES[:] = list(RETRIES), []\n"
                "    return [run(job) for job in pending]\n",
            ),
            (
                "runner/poller.py",
                "import time\n"
                "\n"
                "from runner.jobs import retry_failed, run\n"
                "\n"
                "\n"
                "def poll(source):\n"
                "    while True:\n"
                "        for job in source():\n"
                "            run(job)\n"
                "        retry_failed()\n"
                "        time.sleep(1)\n",
            ),
        ),
        history=("Added the runner.", "Added a poller."),
        branch_work=(
            (
                "tests/test_jobs.py",
                "from runner.jobs import RETRIES, retry_failed, run\n"
                "\n"
                "\n"
                "def test_a_failed_job_is_retried_later():\n"
                "    run(lambda: 1 / 0)\n"
                "    assert len(RETRIES) == 1\n"
                "    retry_failed()\n",
            ),
        ),
        branch_subjects=("Moved retries out of the inline path.",),
    ),
    AdrFixture(
        name="search-index",
        branch="expire-cached-results",
        summary="the search cache now drops an entry ten minutes after it was stored instead of"
        " keeping it for good; evicting the least recently used entry was weighed, but the"
        " complaint was stale prices, so age was chosen over recency",
        sort=WithinComponent("search"),
        prior=(
            _habit(
                1,
                "cache-results-in-memory",
                "Cache search results in memory",
                "The same few queries made up most of the traffic.",
            ),
            _habit(
                2,
                "rank-by-term-count",
                "Rank hits by how often the term appears",
                "A learned ranking needed data the shop does not have yet.",
            ),
        ),
        source=(
            (
                "search/cache.py",
                "import time\n"
                "\n"
                "TTL_SECONDS = 600\n"
                "_entries: dict = {}\n"
                "\n"
                "\n"
                "def put(query, hits):\n"
                "    _entries[query] = (time.monotonic(), hits)\n"
                "\n"
                "\n"
                "def get(query):\n"
                "    stored = _entries.get(query)\n"
                "    if stored is None or time.monotonic() - stored[0] > TTL_SECONDS:\n"
                "        return None\n"
                "    return stored[1]\n",
            ),
            (
                "search/query.py",
                "from search import cache\n"
                "\n"
                "\n"
                "def search(query, index):\n"
                "    hits = cache.get(query)\n"
                "    if hits is None:\n"
                "        hits = [doc for doc in index if query in doc]\n"
                "        cache.put(query, hits)\n"
                "    return hits\n",
            ),
        ),
        history=("Added the search module.", "Cached results by query."),
        branch_work=(
            (
                "tests/test_cache.py",
                "from search import cache\n"
                "\n"
                "\n"
                "def test_a_stored_result_is_served_while_fresh():\n"
                "    cache.put('shoes', ['a'])\n"
                "    assert cache.get('shoes') == ['a']\n",
            ),
        ),
        branch_subjects=("Expired old results.",),
    ),
    AdrFixture(
        name="table-export",
        branch="stream-export-rows",
        summary="the export now reads the table in pages of five hundred rows and writes each page"
        " as it goes instead of loading everything first, which keeps memory flat; loading it all"
        " and compressing afterwards was weighed and set aside because the largest customer's"
        " table no longer fits in memory",
        sort=WithinComponent("exporter"),
        prior=(
            _habit(
                1,
                "export-as-csv",
                "Export tables as CSV",
                "Every customer's spreadsheet tool opens it without help.",
            ),
            _habit(
                2,
                "one-export-per-table",
                "Write one file per table",
                "Customers asked for single tables far more often than for the lot.",
            ),
        ),
        source=(
            (
                "exporter/export.py",
                "import csv\n"
                "\n"
                "PAGE_SIZE = 500\n"
                "\n"
                "\n"
                "def export(rows, out):\n"
                "    writer = csv.writer(out)\n"
                "    page = []\n"
                "    for row in rows:\n"
                "        page.append(row)\n"
                "        if len(page) == PAGE_SIZE:\n"
                "            writer.writerows(page)\n"
                "            page = []\n"
                "    writer.writerows(page)\n",
            ),
            (
                "exporter/tables.py",
                "def read(connection, table):\n"
                "    cursor = connection.execute(f'select * from {table}')\n"
                "    return iter(cursor)\n",
            ),
        ),
        history=("Added the exporter.", "Added the table reader."),
        branch_work=(
            (
                "tests/test_export.py",
                "import io\n"
                "\n"
                "from exporter.export import export\n"
                "\n"
                "\n"
                "def test_every_row_is_written():\n"
                "    out = io.StringIO()\n"
                "    export(iter([(1, 'a'), (2, 'b')]), out)\n"
                "    assert out.getvalue().count('\\n') == 2\n",
            ),
        ),
        branch_subjects=("Wrote rows page by page.",),
    ),
    AdrFixture(
        name="order-platform",
        branch="split-out-notifier",
        summary="sending customer emails and texts moves out of the orders service into a new"
        " notifier service that orders calls over HTTP; keeping it in the orders process was"
        " weighed, but orders had to restart whenever a message template changed, and a message"
        " broker was dropped as too much to run for two senders",
        sort=Architectural("notifier service"),
        prior=(
            _habit(
                1,
                "orders-own-the-checkout",
                "Let the orders service own the checkout",
                "One team ships both the cart and the order, so one service keeps them in step.",
            ),
            _habit(
                2,
                "send-mail-from-the-order-code",
                "Send customer mail from the order code",
                "Only order confirmations went out, and a second sender was not planned.",
            ),
        ),
        source=(
            (
                "orders/service.py",
                "from orders.notify import notify_customer\n"
                "\n"
                "\n"
                "def place(order):\n"
                "    order['status'] = 'placed'\n"
                "    notify_customer(order['customer'], 'Your order is placed')\n"
                "    return order\n",
            ),
            (
                "orders/notify.py",
                "import json\n"
                "import urllib.request\n"
                "\n"
                "NOTIFIER_URL = 'http://notifier.internal/send'\n"
                "\n"
                "\n"
                "def notify_customer(customer, text):\n"
                "    body = json.dumps({'to': customer, 'text': text}).encode()\n"
                "    urllib.request.urlopen(urllib.request.Request(NOTIFIER_URL, body))\n",
            ),
            (
                "notifier/app.py",
                "TEMPLATES = {'placed': 'Thanks, {name}: your order is placed.'}\n"
                "\n"
                "\n"
                "def send(to, text, channel='email'):\n"
                "    return {'channel': channel, 'to': to, 'text': text}\n",
            ),
        ),
        history=(
            "Added the orders service.",
            "Sent mail from the order code.",
        ),
        branch_work=(
            (
                "tests/test_orders.py",
                "from orders.service import place\n"
                "\n"
                "\n"
                "def test_placing_marks_the_order_placed(monkeypatch):\n"
                "    monkeypatch.setattr('orders.service.notify_customer', lambda *args: None)\n"
                "    assert place({'customer': 'ann'})['status'] == 'placed'\n",
            ),
        ),
        branch_subjects=("Moved sending to its own service.",),
    ),
    AdrFixture(
        name="task-worker",
        branch="fold-in-scheduler",
        summary="the separate scheduler process is gone and the worker now runs its own timed jobs,"
        " so there is one process to deploy instead of two; keeping both and adding leader"
        " election was weighed and dropped as heavier than a single worker needs",
        sort=Architectural("scheduler"),
        prior=(
            _habit(
                1,
                "run-a-worker-per-queue",
                "Run one worker for each queue",
                "Queues differ in how long their tasks take, and a shared worker let slow ones starve fast ones.",
            ),
            _habit(
                2,
                "schedule-in-its-own-process",
                "Run the scheduler as its own process",
                "Timed jobs fire once a minute and the worker was busy at that moment.",
            ),
        ),
        source=(
            (
                "worker/main.py",
                "import time\n"
                "\n"
                "from worker.timers import due\n"
                "\n"
                "\n"
                "def loop(next_task, run):\n"
                "    while True:\n"
                "        for job in due(time.time()):\n"
                "            run(job)\n"
                "        task = next_task()\n"
                "        if task is not None:\n"
                "            run(task)\n",
            ),
            (
                "worker/timers.py",
                "SCHEDULE = {'cleanup': 3600, 'report': 86400}\n"
                "_last: dict = {}\n"
                "\n"
                "\n"
                "def due(now):\n"
                "    jobs = [name for name, every in SCHEDULE.items() if now - _last.get(name, 0) >= every]\n"
                "    _last.update({name: now for name in jobs})\n"
                "    return jobs\n",
            ),
        ),
        history=("Added the worker.", "Added a scheduler process."),
        branch_work=(
            (
                "tests/test_timers.py",
                "from worker.timers import due\n"
                "\n"
                "\n"
                "def test_a_job_is_due_the_first_time_it_is_asked():\n"
                "    assert 'cleanup' in due(10_000)\n",
            ),
        ),
        branch_subjects=("Folded the scheduler into the worker.",),
    ),
)

# Each request asks for the decision to be recorded and describes it, and states nothing of the
# rule; ``{summary}`` is the fixture's account of the decision and the options weighed.
WORDINGS: Sequence[tuple[str, str]] = (
    ("plain", "Please write a decision record for what this branch decided: {summary}."),
    (
        "finished",
        "I finished the work on this branch. In short, {summary}. Write that decision down as a"
        " decision record for the project.",
    ),
    (
        "explain",
        "Write up the decision behind this branch as a decision record so the next person"
        " understands it: {summary}.",
    ),
    ("adr", "Add an ADR for this branch's decision. What was decided: {summary}."),
    (
        "wrap-up",
        "Can you wrap up this branch by writing its decision record? The gist: {summary}."
        " I will push it later.",
    ),
    ("terse", "write the decision record ({summary})"),
)


# -- The tasks --------------------------------------------------------------------------------


def tasks(declaration: MoveDeclaration, seed: int) -> tuple[MoveTask, ...]:
    """The task list a run draws for ``seed``."""
    return draw(declaration, candidates(), seed)


def candidates() -> tuple[MoveTask, ...]:
    """Every task the kit can ask: each fixture under each wording."""
    return tuple(
        MoveTask(
            task_id=f"{fixture.name}-{variant}",
            fixture=fixture.name,
            fixture_kind=FIXTURE_KIND,
            wording_variant=variant,
            wording=template.format(summary=fixture.summary),
            named_files=(),
        )
        for fixture in FIXTURES
        for variant, template in WORDINGS
    )


def sort_of(task: MoveTask) -> DecisionSort:
    """The sort the moved rule's test gives the decision ``task`` asks to be recorded."""
    return _fixture_of(task).sort


# -- Building ---------------------------------------------------------------------------------


def build_fixture(declaration: MoveDeclaration, task: MoveTask, where: Path) -> Path:
    """Build ``task``'s repository at ``where`` (absent or empty) and return it.

    Raises ``ValueError`` for a task of no fixture here, for a declaration that does not admit a
    managed fixture, or for a ``where`` that holds something already.
    """
    fixture = _fixture_of(task)
    if not admits(declaration.fixture_scope, FIXTURE_KIND):
        raise ValueError(f"the declaration does not admit the {FIXTURE_KIND} fixture kind")
    where.mkdir(parents=True, exist_ok=True)
    if any(where.iterdir()):
        raise ValueError(f"{where} is not empty")
    git(where, "init", "--quiet", "-b", BASELINE_BRANCH)
    for key, value in IDENTITY:
        git(where, "config", key, value)
    _commit(where, fixture.committed(), fixture.history)
    git(where, "checkout", "--quiet", "-b", fixture.branch)
    _commit(where, fixture.branch_work, fixture.branch_subjects)
    git(where, "update-ref", BASELINE_REF, "HEAD")
    git(where, "symbolic-ref", BRANCH_REF, f"refs/heads/{fixture.branch}")
    return where


def _commit(where: Path, files: Files, subjects: tuple[str, ...]) -> None:
    """The first commit holds the files; the later ones only add to the run's length."""
    write_files(where, files)
    git(where, "add", "--all")
    first, *rest = subjects
    git(where, "commit", "--quiet", "-m", first)
    for subject in rest:
        git(where, "commit", "--quiet", "--allow-empty", "-m", subject)


def _fixture_of(task: MoveTask) -> AdrFixture:
    for fixture in FIXTURES:
        if fixture.name == task.fixture:
            return fixture
    raise ValueError(f"the adr-conventions kit has no fixture named {task.fixture!r}")
