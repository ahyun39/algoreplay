"""Run untrusted code in a throwaway Docker container. Code is never executed on the host.

Three judges (sql: see run_sql_tests):
* function – import the file and call `entrypoint(*args)`; compare the JSON-normalised return value (프로그래머스 style)
* stdio    – run the file as a script with the test input on stdin; compare stdout, ignoring trailing
             whitespace on each line and trailing blank lines (백준 style)

A test whose `expected` is None is run in "record" mode: its output is returned without judging. This is how
the past (accepted) solution produces expected outputs for new test inputs.
"""
import ast
import base64
import csv
import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

from .config import env

OUTPUT_LIMIT = 100_000  # characters kept per output for display; judging always uses the full output

# Runs inside the container. Tests arrive on stdin so the solution cannot read the expected answers from disk.
HARNESS = r'''
import contextlib, copy, io, json, resource, signal, subprocess, sys, time, traceback, tracemalloc
mode, entry, per_test = sys.argv[1], sys.argv[2], float(sys.argv[3])
tests = json.loads(sys.stdin.read())
LIMIT = 100000
def norm(s):
    return "\n".join(line.rstrip() for line in s.rstrip().splitlines())
results, peak_kb = [], 0.0
if mode == "stdio":
    for t in tests:
        r = {"name": t.get("name")}
        start = time.perf_counter()
        try:
            p = subprocess.run([sys.executable, "/work/solution.py"], input=t["input"], capture_output=True,
                               text=True, timeout=per_test, cwd="/tmp")
            r["ms"] = (time.perf_counter() - start) * 1000
            r["output"], r["truncated"] = p.stdout[:LIMIT], len(p.stdout) > LIMIT
            if p.returncode != 0:
                lines = p.stderr.strip().splitlines()
                r["error"] = (lines[-1] if lines else "exit code %d" % p.returncode)[:300]
                r["stderr"] = p.stderr[-LIMIT:]
            elif t.get("expected") is not None:
                r["ok"] = norm(p.stdout) == norm(t["expected"])
        except subprocess.TimeoutExpired:
            r["timeout"], r["ms"] = True, per_test * 1000
        results.append(r)
    peak_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss  # KiB on Linux
else:
    sys.path.insert(0, "/work")
    def on_alarm(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, on_alarm)
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            import solution
        fn = getattr(solution, entry)
    except BaseException:
        print(json.dumps({"fatal": traceback.format_exc(limit=3)[-LIMIT:]}))
        sys.exit(0)
    for t in tests:
        r = {"name": t.get("name")}
        tracemalloc.start()
        signal.setitimer(signal.ITIMER_REAL, per_test)
        start = time.perf_counter()
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                got = fn(*copy.deepcopy(t["input"]))
            signal.setitimer(signal.ITIMER_REAL, 0)
            try:
                r["value"] = json.loads(json.dumps(got))
                r["output"] = json.dumps(r["value"], ensure_ascii=False)[:LIMIT]
            except (TypeError, ValueError):
                r["output"] = repr(got)[:LIMIT]
            if t.get("expected") is not None:
                r["ok"] = "value" in r and r["value"] == t["expected"]
        except TimeoutError:
            r["timeout"] = True
        except BaseException as e:
            signal.setitimer(signal.ITIMER_REAL, 0)
            r["error"] = ("%s: %s" % (type(e).__name__, e))[:300]
            r["stderr"] = traceback.format_exc(limit=3)[-LIMIT:]
        r["ms"] = (time.perf_counter() - start) * 1000
        r["stdout"] = printed.getvalue()[:LIMIT]
        peak_kb = max(peak_kb, tracemalloc.get_traced_memory()[1] / 1024)
        tracemalloc.stop()
        results.append(r)
    results.append({"stdout": captured.getvalue()[-LIMIT:]})
print("\n" + json.dumps({"results": results, "peak_kb": peak_kb}))
'''


def docker_available():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_tests(code, tests, judge="function", entrypoint="solution"):
    """tests: [{"name", "input", "expected"}]. Returns a dict whose `status` is decided by the runner only:
    PASS | FAIL | TIMEOUT | RUNTIME_ERROR | SYNTAX_ERROR | RECORDED | NO_TESTS | SANDBOX_UNAVAILABLE"""
    try:
        if judge != "sql":
            ast.parse(code)  # parse only, nothing is executed on the host
    except SyntaxError as e:
        return {"status": "SYNTAX_ERROR", "stderr": f"line {e.lineno}: {e.msg}", "results": []}
    if not tests:
        return {"status": "NO_TESTS", "stderr": "이 문제에는 아직 테스트가 없습니다.", "results": []}
    if not docker_available():
        return {"status": "SANDBOX_UNAVAILABLE", "results": [],
                "stderr": "Docker가 실행 중이 아닙니다. 제출 코드는 호스트에서 실행하지 않습니다."}
    if judge == "sql":
        return run_sql_tests(code, tests)

    per_test = float(env("EXEC_TIMEOUT_SEC", "3"))
    name = f"algoreplay-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "solution.py").write_text(code, encoding="utf-8")
        Path(tmp, "harness.py").write_text(HARNESS, encoding="utf-8")
        Path(tmp).chmod(0o755)
        cmd = ["docker", "run", "--rm", "-i", "--name", name, "--network", "none",
               "--cpus", env("EXEC_CPU", "1"), "--memory", f"{env('EXEC_MEMORY_MB', '256')}m",
               "--pids-limit", "64", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
               "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONIOENCODING=utf-8",
               "-v", f"{tmp}:/work:ro", env("DOCKER_IMAGE", "python:3.11-slim"),
               "python", "/work/harness.py", judge, entrypoint, str(per_test)]
        try:
            p = subprocess.run(cmd, input=json.dumps(tests), capture_output=True, text=True,
                               timeout=per_test * len(tests) + 20)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            return {"status": "TIMEOUT", "stderr": f"실행 시간 초과 (테스트당 {per_test}s)", "results": []}

    stderr = p.stderr[-OUTPUT_LIMIT:]
    if p.returncode == 137:
        return {"status": "RUNTIME_ERROR", "stderr": "killed — memory limit exceeded?\n" + stderr, "results": []}
    try:
        data = json.loads(p.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"status": "RUNTIME_ERROR", "stderr": stderr or p.stdout[-OUTPUT_LIMIT:], "results": []}
    if "fatal" in data:
        return {"status": "RUNTIME_ERROR", "stderr": data["fatal"], "results": []}

    results = data["results"]
    stdout = results.pop()["stdout"] if results and "stdout" in results[-1] else ""
    judged = [r for r in results if "ok" in r]
    if any(r.get("timeout") for r in results):
        status = "TIMEOUT"
    elif any("error" in r for r in results):
        status = "RUNTIME_ERROR"
    elif not judged:
        status = "RECORDED"
    else:
        status = "PASS" if all(r["ok"] for r in judged) else "FAIL"
    for r, t in zip(results, tests, strict=True):
        r["input"] = t["input"] if isinstance(t["input"], str) else json.dumps(t["input"], ensure_ascii=False)
        r["expected"] = t.get("expected")
        r.setdefault("ok", False)
    return {"status": status, "results": results, "runtime_ms": sum(r.get("ms", 0) for r in results),
            "peak_memory_kb": data["peak_kb"], "passed": sum(r["ok"] for r in results),
            "failed": sum(not r["ok"] for r in results), "stdout": stdout,
            "stderr": "\n".join(r["stderr"] for r in results if r.get("stderr"))[-OUTPUT_LIMIT:] or stderr}


# ---------------------------------------------------------------- SQL judge (PostgreSQL)
# One throwaway postgres container per run. Each test gets a fresh database built from the example tables;
# the submitted SQL runs as an unprivileged role. Expected tables never enter the container: results are
# compared here.

SQL_IMAGE_DEFAULT = "postgres:16-alpine"
PG_TYPES = [(r"enum|char|text", "TEXT"), (r"int", "BIGINT"), (r"dec|num|float|double|real", "NUMERIC"),
            (r"datetime|timestamp", "TIMESTAMP"),
            (r"^date$", "DATE"), (r"bool", "BOOLEAN")]


def _ident(name):
    return '"' + name.lower().replace('"', "") + '"'  # LeetCode's unquoted names fold to lower case


def _setup_sql(tables):
    out = []
    for t in tables:
        cols = ", ".join(f"{_ident(c)} " + next((pg for rx, pg in PG_TYPES if re.search(rx, typ.lower())), "TEXT")
                         for c, typ in t["columns"])
        out.append(f"CREATE TABLE {_ident(t['name'])} ({cols});")
        for row in t["rows"]:
            vals = ", ".join("NULL" if v is None else "'" + str(v).replace("'", "''") + "'" for v in row)
            out.append(f"INSERT INTO {_ident(t['name'])} VALUES ({vals});")
    return "\n".join(out + ["GRANT ALL ON ALL TABLES IN SCHEMA public TO solver;"])


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def _sql_script(code, tests, per_test):
    psql = "psql -qX -v ON_ERROR_STOP=1"
    run = f"{psql} --csv -P null=@@NULL@@ -U solver"
    lines = ["export PGHOST=/tmp PGUSER=postgres",
             "initdb -D /tmp/pg -U postgres -A trust -E UTF8 >/tmp/init.log 2>&1 "
             "|| { echo '@@FATAL'; cat /tmp/init.log; exit 0; }",
             "pg_ctl -D /tmp/pg -w -s -l /tmp/pg.log -o \"-c listen_addresses='' -c unix_socket_directories=/tmp "
             "-c fsync=off -c shared_buffers=16MB\" start || { echo '@@FATAL'; cat /tmp/pg.log; exit 0; }",
             f"{psql} -c 'CREATE ROLE solver LOGIN' >/dev/null",
             f"echo {_b64(code)} | base64 -d > /tmp/sol.sql"]
    for i, t in enumerate(tests):
        after = t["input"].get("result_table")
        lines += [f"{psql} -c 'CREATE DATABASE t{i}' >/dev/null",
                  f"if echo {_b64(_setup_sql(t['input']['tables']))} | base64 -d | {psql} -d t{i} >/dev/null 2>/tmp/e; then",
                  f"PGOPTIONS='-c statement_timeout={int(per_test * 1000)}' {run} -d t{i} -c '\\timing on' "
                  f"-f /tmp/sol.sql >/tmp/o 2>/tmp/e; rc=$?"]
        if after:  # DELETE / UPDATE problems: the answer is the table afterwards
            lines.append(f"[ $rc = 0 ] && {{ {run} -d t{i} -c 'SELECT * FROM {_ident(after)}' >/tmp/o 2>>/tmp/e; rc=$?; }}")
        lines += ["else rc=setup; : >/tmp/o; fi", f'echo "@@T|{i}|$rc|$(base64 -w0 /tmp/o)|$(base64 -w0 /tmp/e)"']
    return "\n".join(lines) + "\n"


def _cell(v):
    if v is None or v == "@@NULL@@":
        return None
    try:
        return round(float(v), 4)  # 0.5 == 0.50, 1 == 1.00
    except ValueError:
        return v.strip()


def _same_table(got_cols, got_rows, exp):
    if [c.lower() for c in got_cols] != [c.lower() for c in exp["columns"]]:
        return False
    a, b = ([[_cell(v) for v in r] for r in rows] for rows in (got_rows, exp["rows"]))
    if not exp["ordered"]:
        a, b = sorted(a, key=repr), sorted(b, key=repr)
    return a == b


def _as_text(cols, rows):
    return "\n".join(" | ".join("null" if v in (None, "@@NULL@@") else str(v) for v in r) for r in [cols, *rows])


def run_sql_tests(code, tests):
    image = env("SQL_DOCKER_IMAGE", SQL_IMAGE_DEFAULT)
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        return {"status": "SANDBOX_UNAVAILABLE", "results": [],
                "stderr": f"SQL 채점용 Docker 이미지가 없습니다. 터미널에서 `docker pull {image}`를 실행하세요."}
    per_test = float(env("EXEC_TIMEOUT_SEC", "3"))
    name = f"algoreplay-{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "-i", "--name", name, "--network", "none",
           "--cpus", env("EXEC_CPU", "1"), "--memory", f"{env('EXEC_MEMORY_MB', '256')}m", "--pids-limit", "64",
           "--read-only", "--tmpfs", "/tmp:rw,size=64m", "--tmpfs", "/var/run/postgresql",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "postgres",
           image, "sh", "-c", "cat > /tmp/job.sh && sh /tmp/job.sh </dev/null"]
    try:
        p = subprocess.run(cmd, input=_sql_script(code, tests, per_test), capture_output=True, text=True,
                           timeout=per_test * len(tests) + 30)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        return {"status": "TIMEOUT", "stderr": f"실행 시간 초과 (테스트당 {per_test}s)", "results": []}
    if "@@FATAL" in p.stdout or p.returncode != 0:
        return {"status": "RUNTIME_ERROR", "stderr": (p.stdout + p.stderr)[-OUTPUT_LIMIT:], "results": []}

    lines = [ln.split("|") for ln in p.stdout.splitlines() if ln.startswith("@@T|")]
    results = []
    for t, (_, _, rc, out, err) in zip(tests, lines, strict=True):
        out, err = (base64.b64decode(x).decode("utf-8", "replace") for x in (out, err))
        timing = [float(m) for m in re.findall(r"^Time: ([\d.]+) ms", out, re.M)]
        csv_rows = list(csv.reader(ln for ln in out.splitlines() if not re.match(r"Time: [\d.]+ ms", ln)))
        exp = t["expected"]
        r = {"name": t["name"], "ms": sum(timing), "input": ", ".join(x["name"] for x in t["input"]["tables"]),
             "expected": _as_text(exp["columns"], exp["rows"])}
        if rc == "setup":
            r["error"], r["stderr"] = "예제 표로 테이블을 만들지 못했습니다 (README 파싱 문제)", err[-OUTPUT_LIMIT:]
        elif rc != "0":
            msg = [ln for ln in err.splitlines() if "ERROR:" in ln] or err.strip().splitlines()
            r["error"], r["stderr"] = (msg[-1].split("ERROR:")[-1].strip() if msg else f"exit code {rc}")[:300], \
                err[-OUTPUT_LIMIT:]
            r["timeout"] = "statement timeout" in err or None
        elif not csv_rows:
            r["error"] = "결과 표가 없습니다 (SELECT 문이 필요합니다)"
        else:
            r["output"] = _as_text(csv_rows[0], csv_rows[1:])[:OUTPUT_LIMIT]
            r["ok"] = _same_table(csv_rows[0], csv_rows[1:], exp)
        results.append(r)
    if any(r.get("timeout") for r in results):
        status = "TIMEOUT"
    elif any("error" in r for r in results):
        status = "RUNTIME_ERROR"
    else:
        status = "PASS" if all(r["ok"] for r in results) else "FAIL"
    for r in results:
        r.setdefault("ok", False)
    return {"status": status, "results": results, "runtime_ms": sum(r["ms"] for r in results), "peak_memory_kb": None,
            "passed": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results), "stdout": "",
            "stderr": "\n".join(r["stderr"] for r in results if r.get("stderr"))[-OUTPUT_LIMIT:]}


def record_expected(reference_code, inputs, judge, entrypoint="solution"):
    """Use the past accepted solution as an oracle. Returns (tests_with_expected, rejected_inputs)."""
    run = run_tests(reference_code, [{"name": f"case {i}", "input": x, "expected": None}
                                     for i, x in enumerate(inputs, 1)], judge, entrypoint)
    if run["status"] in ("SANDBOX_UNAVAILABLE", "SYNTAX_ERROR", "NO_TESTS") or not run["results"]:
        raise RuntimeError(run.get("stderr") or run["status"])
    accepted, rejected = [], []
    for x, r in zip(inputs, run["results"], strict=True):
        if r.get("error") or r.get("timeout") or r.get("truncated") or (judge == "function" and "value" not in r):
            rejected.append((x, r.get("error") or ("timeout" if r.get("timeout") else "output too large")))
        else:
            accepted.append({"input": x, "expected": r["value"] if judge == "function" else r["output"]})
    return accepted, rejected
