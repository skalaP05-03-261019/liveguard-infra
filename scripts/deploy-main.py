#!/usr/bin/env python3
"""Deploy isolated clean origin/main sources; preserve existing worktrees and volumes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {"backend": "liveguard-be", "agent": "liveguard-agent", "frontend": "liveguard-fe"}


class DeploymentError(RuntimeError):
    pass


def run(command: list[str], *, input_text: str | None = None,
        timeout: float = 600, env: dict[str, str] | None = None,
        health_output: bool = False) -> str:
    try:
        result = subprocess.run(command, input=input_text, capture_output=True,
                                text=True, timeout=timeout, env=env, cwd=ROOT)
    except subprocess.TimeoutExpired:
        raise DeploymentError(f"{command[0]} exceeded its time limit; output withheld") from None
    if result.returncode:
        if health_output:
            errors = [line for line in result.stdout.splitlines() if line.startswith("HEALTH_ERROR: ")]
            if errors:
                raise DeploymentError(errors[-1])
        raise DeploymentError(
            f"{command[0]} failed (exit {result.returncode}); output withheld to protect credentials")
    return result.stdout.strip()


def git(source: Path, *args: str) -> str:
    return run(["git", "-C", str(source), *args])


def sync_source(source: Path, remote: str) -> str:
    if not source.exists():
        run(["git", "clone", "--branch", "main", "--single-branch", remote, str(source)])
    if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source.resolve():
        raise DeploymentError(f"Not a dedicated source checkout: {source}")
    if git(source, "status", "--porcelain", "--untracked-files=all"):
        raise DeploymentError(f"Dirty deployment checkout; preserve changes and resolve manually: {source}")
    if git(source, "remote", "get-url", "origin") != remote:
        raise DeploymentError(f"Deployment origin differs from sibling repository: {source}")
    git(source, "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
    git(source, "checkout", "main")
    git(source, "merge", "--ff-only", "origin/main")
    revision = git(source, "rev-parse", "HEAD")
    if revision != git(source, "rev-parse", "origin/main"):
        raise DeploymentError(f"Local main is ahead of origin/main: {source}")
    return revision


def compose_command(env_file: Path, project: str, runtime: Path, rabbit: bool) -> list[str]:
    command = ["docker", "compose", "--env-file", str(env_file),
               "--project-directory", str(ROOT), "-p", project]
    if rabbit:
        command += ["--profile", "rabbit"]
    return command + ["-f", str(ROOT / "compose.yaml"), "-f", str(runtime)]


def runtime_config(sources: dict[str, Path], revisions: dict[str, str]) -> dict:
    services = {}
    for service, repository in REPOSITORIES.items():
        services[service] = {
            "image": f"{repository}:main-{revisions[service]}",
            "build": {"context": str(sources[service])},
        }
    for service in ("business-mcp-1", "business-mcp-2", "rag-mcp"):
        services[service] = {
            "image": services["agent"]["image"],
            "build": {"context": str(sources["agent"])},
        }
    return {"services": services}


def check_containers(command: list[str], config: dict, env: dict[str, str],
                     images: dict[str, str]) -> None:
    for name in config["services"]:
        ids = run(command + ["ps", "-a", "-q", name], env=env).splitlines()
        if len(ids) != 1:
            raise DeploymentError(f"{name}: expected exactly one container")
        info = json.loads(run(["docker", "inspect", ids[0]]))[0]
        state = info["State"]
        if state["Status"] != "running" or state.get("Health", {}).get("Status", "healthy") != "healthy":
            raise DeploymentError(f"{name}: container is not running/healthy")
        if info["Image"] != images[name]:
            raise DeploymentError(f"{name}: running image differs from recorded deployment image")
    expected = config["services"]["agent"]["environment"]["MODEL_MAX_INPUT_TOKENS"]
    cid = run(command + ["ps", "-q", "agent"], env=env)
    info = json.loads(run(["docker", "inspect", cid]))[0]
    if f"MODEL_MAX_INPUT_TOKENS={expected}" not in info["Config"]["Env"]:
        raise DeploymentError("Agent runtime token limit differs from resolved Compose")


def wait_ready(command: list[str], config: dict, env: dict[str, str], timeout: int,
               images: dict[str, str]) -> None:
    probe = (ROOT / "scripts/deployment-health.py").read_text()
    deadline = time.monotonic() + timeout
    last_error = "Health checks not started"
    while time.monotonic() < deadline:
        try:
            check_containers(command, config, env, images)
            version = config["services"]["backend"]["environment"].get("LIVEGUARD_POLICY_VERSION") or "v3.2"
            output = run(command + ["exec", "-T", "-e", f"DEPLOYMENT_POLICY_VERSION={version}",
                                    "agent", "python", "-c", probe],
                         timeout=min(45, max(1, deadline - time.monotonic())), env=env,
                         health_output=True)
            print(output, flush=True)
            return
        except DeploymentError as error:
            last_error = str(error)
            print(f"WAIT: {last_error}", file=sys.stderr, flush=True)
        time.sleep(min(3, max(0, deadline - time.monotonic())))
    raise DeploymentError(f"Readiness deadline exceeded: {last_error}. No success recorded.")


def seed_participants(command: list[str], env: dict[str, str]) -> None:
    run(command + ["exec", "-T", "db", "sh", "-c",
        'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        input_text=(ROOT / "scripts/seed-demo-participants.sql").read_text(), env=env)
    print("PASS: local demo participants p001-p200 and channel A memberships", flush=True)


def index_policies(command: list[str], env: dict[str, str]) -> list[str]:
    discover = """
import json, os, psycopg
with psycopg.connect(os.environ["RAG_DB_URL"]) as conn:
    exists = conn.execute("SELECT to_regclass('rag.policy_chunks')").fetchone()[0]
    versions = [row[0] for row in conn.execute(
        "SELECT DISTINCT version FROM rag.policy_chunks")] if exists else []
print(json.dumps(versions))
"""
    prefix = command + ["run", "--rm", "--no-deps", "--pull", "never", "-T"]
    existing = json.loads(run(prefix + ["rag-mcp", "python", "-c", discover], env=env))
    versions = ([] if "v3.1" in existing else ["v3.1"]) + ["v3.2"]
    for version in versions:
        print(f"Indexing {version} once (OpenAI embedding request; output withheld)...", flush=True)
        run(prefix + ["-e", f"LIVEGUARD_POLICY_VERSION={version}",
                      "-e", f"POLICY_VERSION={version}", "rag-mcp",
                      "python", "-m", "app.rag_mcp.index"], env=env, timeout=600)
    return versions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--project", default=ROOT.name)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--rabbit", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--sync-only", action="store_true", help="Fetch main without building or deploying")
    modes.add_argument("--check-only", action="store_true", help="Check last attempted deployment; no fetch/build/up")
    parser.add_argument("--seed-demo-participants", action="store_true",
                        help="Explicit local-demo DB opt-in; never use on shared/production DB")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.seed_demo_participants and (args.check_only or args.sync_only):
        parser.error("Seeding requires a deployment, not --check-only/--sync-only")
    state_dir = ROOT / ".deploy" / args.project
    if (not args.project or args.project[0] not in "abcdefghijklmnopqrstuvwxyz0123456789"
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in args.project)):
        parser.error("--project must start with a lowercase letter/digit; only lowercase letters, digits, - and _ allowed")
    state_dir.mkdir(parents=True, exist_ok=True)
    # Prevent two deploy/check invocations from racing the same project manifest.
    import fcntl
    with (state_dir / "lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeploymentError("Another deployment/check is using this project") from None
        execute(args, state_dir)


def execute(args: argparse.Namespace, state_dir: Path) -> None:
    manifest_path = state_dir / "deployment.json"
    runtime = state_dir / "runtime.json"
    env_file = args.env_file.resolve()
    if args.check_only:
        manifest = json.loads(manifest_path.read_text())
        if str(env_file) != manifest["envFile"]:
            raise DeploymentError("--env-file must match the last deployment")
        rabbit = manifest["rabbit"]
    else:
        source_dir = (args.source_dir or state_dir / "sources").resolve()
        source_dir.mkdir(parents=True, exist_ok=True)
        sources, revisions = {}, {}
        for service, name in REPOSITORIES.items():
            sources[service] = source_dir / name
            if sources[service].resolve() == (ROOT.parent / name).resolve():
                raise DeploymentError("Deployment sources must not be the developer sibling checkouts")
            remote = git(ROOT.parent / name, "remote", "get-url", "origin")
            revisions[service] = sync_source(sources[service], remote)
            print(f"MAIN {name}: {revisions[service]}", flush=True)
        if args.sync_only:
            print("Sources synchronized; no deployment or readiness claim.")
            return
        manifest = {
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "infraRevision": git(ROOT, "rev-parse", "HEAD"),
            "infraDirty": bool(git(ROOT, "status", "--porcelain")),
            "sources": {name: {"path": str(sources[name]), "revision": revisions[name]}
                        for name in sources},
            "envFile": str(env_file), "rabbit": args.rabbit, "status": "PREPARING",
        }
        rabbit = args.rabbit
        runtime.write_text(json.dumps(runtime_config(sources, revisions), indent=2) + "\n")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if not env_file.is_file():
        raise DeploymentError("Deployment env file is missing")
    env = dict(os.environ)
    # MCP image is overridden by runtime.json, but Compose still expands the base required value.
    env["BUSINESS_MCP_IMAGE"] = "liveguard-agent:main-" + manifest["sources"]["agent"]["revision"]
    command = compose_command(env_file, args.project, runtime, rabbit)
    config = json.loads(run(command + ["config", "--format", "json"], env=env))
    if args.check_only:
        if not manifest.get("images"):
            raise DeploymentError("No built deployment images recorded; deployment did not reach startup")
        wait_ready(command, config, env, args.timeout, manifest["images"])
        return
    agent_env = config["services"]["agent"]["environment"]
    missing = [name for name in ("AGENT_GATEWAY_FACTORY", "MODEL_NAME", "MODEL_API_KEY")
               if not agent_env.get(name)]
    rag_env = config["services"]["rag-mcp"]["environment"]
    missing += [name for name in ("RAG_DB_URL", "OPENAI_API_KEY") if not rag_env.get(name)]
    if missing:
        manifest["status"] = "PREFLIGHT_FAILED"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        raise DeploymentError("Required readiness settings are missing: " + ", ".join(missing)
                              + ". Running containers were not changed.")
    if agent_env.get("AGENT_INBOX_BACKEND") == "postgres":
        raise DeploymentError("This Compose deploys a single Agent runtime, not API-only shared Inbox workers")
    manifest["status"] = "BUILDING"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    try:
        print("Building main images (build output withheld to protect configuration)...", flush=True)
        run(command + ["build", "backend", "frontend", "agent"], env=env, timeout=1800)
        # Shared Agent/MCP/RAG tag is built once; no second concurrent build of the same tag.
        for name in config["services"]:
            if name not in REPOSITORIES and "build" not in config["services"][name]:
                run(command + ["pull", "--policy", "missing", name], env=env, timeout=600)
        manifest["images"] = {
            name: json.loads(run(["docker", "image", "inspect", service["image"]]))[0]["Id"]
            for name, service in config["services"].items()
        }
        manifest["status"] = "STARTING"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        run(command + ["up", "-d", "--no-build", "--wait",
                       "--wait-timeout", str(args.timeout)], env=env)
        manifest["status"] = "INDEXING"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        manifest["indexedVersionsThisDeployment"] = index_policies(command, env)
        wait_ready(command, config, env, args.timeout, manifest["images"])
        if args.seed_demo_participants:
            seed_participants(command, env)
        manifest["status"] = "READY"
        manifest["demoParticipantsSeeded"] = args.seed_demo_participants
        print(f"READY: {args.project}; manifest: {manifest_path}", flush=True)
    except DeploymentError:
        manifest["status"] = "FAILED"
        raise
    finally:
        manifest["finishedAt"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (DeploymentError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None
