"""SQLite storage. Tables are created on first connect; `user_version` tracks the schema."""
import sqlite3
from datetime import UTC, datetime

from .config import ROOT, env

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS repositories (
  id INTEGER PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL, default_branch TEXT,
  last_sync_sha TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(owner, name));

CREATE TABLE IF NOT EXISTS problems (
  id INTEGER PRIMARY KEY,
  repository_id INTEGER NOT NULL REFERENCES repositories(id),
  problem_key TEXT NOT NULL,          -- e.g. boj-10026, programmers-12914, two-sum
  source TEXT NOT NULL,               -- boj | programmers | native | ...
  external_id TEXT,
  title TEXT NOT NULL,
  statement TEXT NOT NULL,            -- markdown
  difficulty TEXT NOT NULL,           -- easy | medium | hard (normalised)
  tier TEXT,                          -- original label: "Gold V", "level 2"
  language TEXT NOT NULL DEFAULT 'python',
  judge TEXT NOT NULL,                -- function | stdio
  entrypoint TEXT NOT NULL DEFAULT 'solution',
  tags_json TEXT NOT NULL DEFAULT '[]',   -- labels as written in the repo
  topics_json TEXT NOT NULL DEFAULT '[]', -- canonical topics used for learning/theory
  hints_json TEXT NOT NULL DEFAULT '[]',
  url TEXT,
  solved_at TEXT,                     -- original submission time of the past solution
  past_performance TEXT,
  github_path TEXT NOT NULL,
  github_sha TEXT NOT NULL,
  reference_solution TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(repository_id, problem_key));

CREATE TABLE IF NOT EXISTS tests (
  id INTEGER PRIMARY KEY,
  problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  input_json TEXT NOT NULL,           -- function judge: JSON args list; stdio judge: JSON string
  expected_json TEXT NOT NULL,
  origin TEXT NOT NULL,               -- repo (replaced on sync) | user | generated
  created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS theory (
  id INTEGER PRIMARY KEY, repository_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
  UNIQUE(repository_id, name));

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY, problem_id INTEGER NOT NULL REFERENCES problems(id), code TEXT NOT NULL,
  submitted_at TEXT NOT NULL, status TEXT NOT NULL, runtime_ms REAL, peak_memory_kb REAL,
  passed_count INTEGER, failed_count INTEGER, stdout TEXT, stderr TEXT, results_json TEXT);

CREATE TABLE IF NOT EXISTS analyses (
  id INTEGER PRIMARY KEY, attempt_id INTEGER NOT NULL REFERENCES attempts(id),
  complexity_time TEXT, complexity_space TEXT, complexity_confidence REAL, algorithm_family TEXT,
  data_structures_json TEXT, code_quality_json TEXT, bugs_json TEXT, theory_topics_json TEXT,
  comparison_json TEXT, report_markdown TEXT, created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS learning_events (
  id INTEGER PRIMARY KEY, problem_id INTEGER, attempt_id INTEGER, event_type TEXT NOT NULL,
  topic TEXT, score REAL, detail_json TEXT, created_at TEXT NOT NULL);

CREATE INDEX IF NOT EXISTS idx_attempts_problem ON attempts(problem_id);
CREATE INDEX IF NOT EXISTS idx_tests_problem ON tests(problem_id);
CREATE INDEX IF NOT EXISTS idx_learning_topic ON learning_events(topic);
"""


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path=None):
    path = path or env("DATABASE_PATH", str(ROOT / "algoreplay.db"))
    # ponytail: one shared connection for a local single-user app; use a pool/server DB for multi-user hosting.
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    has_tables = db.execute("SELECT 1 FROM sqlite_master WHERE name='problems'").fetchone()
    if has_tables and version < SCHEMA_VERSION:
        raise RuntimeError(f"{path} was created by a pre-release AlgoReplay (schema {version}). "
                           "Delete the file and sync again.")
    db.executescript(SCHEMA)
    db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return db
