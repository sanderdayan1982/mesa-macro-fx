"""t333u: Netlify ignore builds on HTML/netlify.toml changes and on an unsafe diff.

Exit 0 = cancel deploy, exit != 0 = build. Only cancel when the diff can be
compared and says, with certainty, that no *.html and no netlify.toml changed.
New test; no existing tests, thresholds or formulas are edited.
  python3 -m ingest.tests_netlify_ignore_t333u
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOML = ROOT / "netlify.toml"


def check(cond, msg, fails):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def load_ignore():
    cfg = tomllib.loads(TOML.read_text(encoding="utf-8"))
    return cfg["build"]["ignore"]


def run_ignore(repo: Path, cached: str | None, commit: str | None, ignore: str, extra_env=None) -> int:
    env = os.environ.copy()
    env.pop("CACHED_COMMIT_REF", None)
    env.pop("COMMIT_REF", None)
    if cached is not None:
        env["CACHED_COMMIT_REF"] = cached
    if commit is not None:
        env["COMMIT_REF"] = commit
    if extra_env:
        env.update(extra_env)
    r = subprocess.run(
        ["bash", "-c", ignore],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    return r.returncode


def git(repo: Path, *args, **kw):
    r = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=kw.get("check", True),
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t333u", "GIT_AUTHOR_EMAIL": "t333u@test",
             "GIT_COMMITTER_NAME": "t333u", "GIT_COMMITTER_EMAIL": "t333u@test"},
    )
    return r


def make_repo():
    td = Path(tempfile.mkdtemp(prefix="t333u-nf-"))
    git(td, "init", "-q")
    git(td, "config", "user.email", "t333u@test")
    git(td, "config", "user.name", "t333u")
    (td / "cad").mkdir()
    (td / "data" / "cad").mkdir(parents=True)
    (td / "js").mkdir()
    (td / "cad" / "index.html").write_text("cad-v1\n", encoding="utf-8")
    (td / "index.html").write_text("root-v1\n", encoding="utf-8")
    (td / "netlify.toml").write_text("ignore = \"old\"\n", encoding="utf-8")
    (td / "data" / "cad" / "fiscal.json").write_text('{"v":1}\n', encoding="utf-8")
    (td / "js" / "app.js").write_text("v1\n", encoding="utf-8")
    git(td, "add", ".")
    git(td, "commit", "-q", "-m", "base")
    base = git(td, "rev-parse", "HEAD").stdout.strip()
    return td, base


def commit_change(repo: Path, rel: str, text: str, msg: str) -> str:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", rel)
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def test_ignore_text(fails):
    ignore = load_ignore()
    check("*.html" in ignore, "ignore pathspec includes '*.html'", fails)
    check("netlify.toml" in ignore, "ignore pathspec includes netlify.toml", fails)
    check("test $? -eq 0" in ignore, "fail-safe test $? -eq 0 is present (exit 0 only if diff is surely empty)", fails)
    check("git diff --quiet" in ignore, "uses git diff --quiet", fails)
    check("js" not in ignore and "css" not in ignore and "data" not in ignore.split("netlify.toml")[-1],
          "ignore is not expanded to js/css/data (none were in the previous rule)", fails)
    # data may appear in comments; the command path list must stay html + toml
    # strip comments is hard inside the quoted command; check the command lists only those paths after --
    after = ignore.split(" -- ", 1)[-1] if " -- " in ignore else ignore
    check("'*.html' netlify.toml" in after and "data" not in after,
          "path list after -- is '*.html' netlify.toml only", fails)


def test_behaviors(fails):
    ignore = load_ignore()
    repo, base = make_repo()

    html_sha = commit_change(repo, "cad/index.html", "cad-v2\n", "html nested")
    rc = run_ignore(repo, base, html_sha, ignore)
    check(rc != 0, f"cad/index.html change → build (rc={rc})", fails)

    root_sha = commit_change(repo, "index.html", "root-v2\n", "html root")
    prev = git(repo, "rev-parse", "HEAD~1").stdout.strip()
    rc = run_ignore(repo, prev, root_sha, ignore)
    check(rc != 0, f"root index.html change → build (rc={rc})", fails)

    toml_sha = commit_change(repo, "netlify.toml", "ignore = \"new\"\n", "toml")
    prev = git(repo, "rev-parse", "HEAD~1").stdout.strip()
    rc = run_ignore(repo, prev, toml_sha, ignore)
    check(rc != 0, f"netlify.toml change → build (rc={rc})", fails)

    data_sha = commit_change(repo, "data/cad/fiscal.json", '{"v":2}\n', "data only")
    prev = git(repo, "rev-parse", "HEAD~1").stdout.strip()
    rc = run_ignore(repo, prev, data_sha, ignore)
    check(rc == 0, f"data-only commit → cancel (rc={rc})", fails)

    js_sha = commit_change(repo, "js/app.js", "v2\n", "js only")
    prev = git(repo, "rev-parse", "HEAD~1").stdout.strip()
    rc = run_ignore(repo, prev, js_sha, ignore)
    check(rc == 0, f"js-only commit (not in previous rule) → cancel (rc={rc})", fails)

    # cannot compare safely
    rc = run_ignore(repo, "", data_sha, ignore)
    check(rc != 0, f"empty CACHED_COMMIT_REF → build (rc={rc})", fails)

    rc = run_ignore(repo, None, data_sha, ignore)
    check(rc != 0, f"unset CACHED_COMMIT_REF → build (rc={rc})", fails)

    rc = run_ignore(repo, data_sha, data_sha, ignore)
    check(rc != 0, f"CACHED_COMMIT_REF equals COMMIT_REF → build (rc={rc})", fails)

    rc = run_ignore(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", data_sha, ignore)
    check(rc != 0, f"CACHED_COMMIT_REF missing from clone → build (rc={rc})", fails)

    # a git diff failure (bad revision format) also builds thanks to test $? -eq 0
    rc = run_ignore(repo, "not-a-commit", data_sha, ignore)
    check(rc != 0, f"git diff failure (bad rev) → build (rc={rc})", fails)


def main():
    fails = []
    test_ignore_text(fails)
    test_behaviors(fails)
    print("fails=%d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
