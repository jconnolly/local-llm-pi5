"""dsgbench — concrete wall-clock on REAL-shaped DSG infra tasks: LOCAL vs cloud.

Three tasks chosen to span the bounded -> open-ended axis, all modeled on
a typical internal web-app stack (ECS/ALB/Cognito-OIDC, Terraform):

  1. ecr_module     bounded   — write a small self-contained ECR TF module
  2. ecs_service    build     — scaffold a multi-file ECS Fargate service module
  3. oidc_debug     debug     — fix a planted bug in an ALB x-amzn-oidc-data parser
                                (has a failing pytest -> real iterate loop)

SAFETY (hard guarantees, no prod impact):
  - every run executes in a throwaway tempfile.TemporaryDirectory()
  - ALL AWS creds are STRIPPED and AWS_EC2_METADATA_DISABLED=true for BOTH backends,
    so terraform apply / aws CLI cannot authenticate to any account
  - prompts forbid terraform apply/plan/init, AWS calls, and deploys
  - tasks 1-2 are greenfield generation; task 3 is a synthetic snippet, NOT the real repo

Usage:
    python run.py                       # all tasks, both backends
    python run.py --backends local      # local only (no cloud cost)
    DSGBENCH_LOCAL_MODEL=gpt-oss:20b python run.py
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).parent
CLAUDE = "/Users/john.connolly/.local/bin/claude"
STUDIO = "studio.local:11434"
LOCAL_MODEL = os.environ.get("DSGBENCH_LOCAL_MODEL", "qwen3.6:27b-mtp-q8_0")

# AWS creds neutralized for BOTH backends so nothing can touch a real account.
AWS_NEUTRALIZE_STRIP = ["AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                        "AWS_SESSION_TOKEN", "AWS_DEFAULT_PROFILE", "AWS_VAULT"]
AWS_NEUTRALIZE_SET = {"AWS_EC2_METADATA_DISABLED": "true",
                      "AWS_ACCESS_KEY_ID": "", "AWS_SECRET_ACCESS_KEY": ""}

BACKENDS = {
    "local": {
        "ANTHROPIC_BASE_URL": f"http://{STUDIO}",
        "ANTHROPIC_AUTH_TOKEN": "ollama",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_MODEL": LOCAL_MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": LOCAL_MODEL,
        "CLAUDE_CODE_DISABLE_THINKING": "1",
    },
    "cloud": {"__strip__": ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN",
                            "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"]},
}

NO_DEPLOY = ("\n\nIMPORTANT: write the code ONLY. Do NOT run `terraform apply`, "
             "`terraform plan`, or `terraform init`. Do NOT call the AWS CLI or any AWS API. "
             "Do NOT deploy anything. Just create the files.")

OIDC_BUG = '''import base64, json

def parse_oidc_data(header: str) -> dict:
    """Decode an ALB x-amzn-oidc-data JWT (header.payload.signature) into its claims."""
    parts = header.split(".")
    payload = parts[0]                      # decode the payload segment
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))
'''
OIDC_TEST = '''import base64, json
from auth import parse_oidc_data

def _seg(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

def test_extracts_email_and_sub():
    hdr = ".".join([_seg({"alg": "ES256"}), _seg({"email": "a@b.com", "sub": "u-123"}), "sigbytes"])
    out = parse_oidc_data(hdr)
    assert out["email"] == "a@b.com"
    assert out["sub"] == "u-123"
'''

TASKS = [
    {"id": "ecr_module", "kind": "bounded", "timeout": 360,
     "prompt": ("Create a reusable Terraform MODULE in this directory for an AWS ECR repository. "
                "Files: main.tf, variables.tf, outputs.tf. The repository must enable image scanning "
                "on push and have a lifecycle policy that expires all but the 10 most recent images. "
                "Expose a `name` variable; output the repository URL." + NO_DEPLOY),
     "files": {},
     "score": lambda d: any("aws_ecr_repository" in p.read_text() and "lifecycle_policy" in (p.read_text() + _read_siblings(p))
                            for p in d.glob("*.tf"))},
    {"id": "ecs_service", "kind": "build", "timeout": 480,
     "prompt": ("Scaffold a reusable Terraform MODULE in this directory for an AWS ECS Fargate service. "
                "Include: an aws_ecs_task_definition (Fargate / awsvpc), an aws_ecs_service wired to an "
                "aws_lb_target_group, and an IAM task-execution role attached to the AmazonECSTaskExecutionRolePolicy. "
                "Expose variables for image, cpu, memory, container_port, desired_count, subnets, and security_groups. "
                "Files: main.tf, variables.tf, outputs.tf." + NO_DEPLOY),
     "files": {},
     "score": lambda d: _all_in(d, ["aws_ecs_task_definition", "aws_ecs_service", "aws_lb_target_group"])},
    {"id": "oidc_debug", "kind": "debug", "timeout": 600,
     "prompt": ("This directory has a bug. `auth.py` parses an ALB `x-amzn-oidc-data` JWT but returns the "
                "wrong claims. A test file `test_task.py` is present — run `python -m pytest -q test_task.py` "
                "and iterate until ALL tests pass. Do not edit the test file." + NO_DEPLOY),
     "files": {"auth.py": OIDC_BUG, "test_task.py": OIDC_TEST},
     "score": None},  # scored by pytest
]


def _read_siblings(p: Path) -> str:
    return "".join(q.read_text() for q in p.parent.glob("*.tf"))


def _all_in(d: Path, needles) -> bool:
    blob = "".join(p.read_text() for p in d.glob("*.tf"))
    return all(n in blob for n in needles)


def run_one(task: dict, backend: str) -> dict:
    with tempfile.TemporaryDirectory() as dd:
        root = Path(dd)
        for rel, content in task["files"].items():
            (root / rel).write_text(content)

        env = dict(os.environ)
        # 1) neutralize AWS for BOTH backends
        for k in AWS_NEUTRALIZE_STRIP:
            env.pop(k, None)
        env.update(AWS_NEUTRALIZE_SET)
        # 2) apply backend overlay
        cfg = BACKENDS[backend]
        for k in cfg.get("__strip__", []):
            env.pop(k, None)
        for k, v in cfg.items():
            if k != "__strip__":
                env[k] = v
        env["CLAUDE_PROJECT_DIR"] = str(root)

        t0 = time.time()
        try:
            r = subprocess.run(
                [CLAUDE, "-p", task["prompt"], "--output-format", "json",
                 "--dangerously-skip-permissions"],
                cwd=root, env=env, capture_output=True, text=True, timeout=task["timeout"],
            )
        except subprocess.TimeoutExpired:
            return {"backend": backend, "success": False, "note": f"timeout({task['timeout']}s)",
                    "duration_ms": task["timeout"] * 1000}
        wall = (time.time() - t0) * 1000

        res = {}
        try:
            data = json.loads(r.stdout)
            res = (data[-1] if isinstance(data, list) else data) or {}
        except Exception:
            res = {}

        if task["score"] is None:  # pytest-scored debug task
            try:
                tr = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_task.py"],
                                    cwd=root, capture_output=True, text=True, timeout=60)
                passed = tr.returncode == 0
            except subprocess.TimeoutExpired:
                passed = False
        else:
            try:
                passed = bool(task["score"](root))
            except Exception:
                passed = False

        u = res.get("usage", {}) or {}
        return {
            "backend": backend, "success": passed,
            "duration_ms": res.get("duration_ms", round(wall)),
            "num_turns": res.get("num_turns"),
            "out_tokens": u.get("output_tokens"),
            "cost_usd": res.get("total_cost_usd"),
        }


def warmup_local() -> None:
    """One untimed local call to load the model into the Studio's RAM before timing."""
    env = dict(os.environ)
    for k in AWS_NEUTRALIZE_STRIP:
        env.pop(k, None)
    env.update(AWS_NEUTRALIZE_SET)
    env.update({k: v for k, v in BACKENDS["local"].items() if k != "__strip__"})
    try:
        subprocess.run([CLAUDE, "-p", "Reply with exactly: ok", "--output-format", "json"],
                       env=env, capture_output=True, text=True, timeout=240)
    except Exception:
        pass


def main() -> int:
    import statistics
    ap = argparse.ArgumentParser()
    ap.add_argument("--task")
    ap.add_argument("--backends", default="local,cloud")
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    tasks = [t for t in TASKS if not args.task or t["id"] == args.task]
    backends = args.backends.split(",")
    print(f"local model: {LOCAL_MODEL}   |   AWS creds: NEUTRALIZED (no prod reachable)   |   "
          f"repeat={args.repeat}\n", flush=True)

    if "local" in backends:
        print("warming up local model (untimed) ...", flush=True)
        warmup_local()

    rows = []           # every individual run
    agg = {}            # (task, backend) -> list of duration_ms
    for t in tasks:
        for b in backends:
            for i in range(args.repeat):
                print(f"running {t['id']:<14} ({t['kind']:<7}) [{b}] rep {i+1}/{args.repeat} ...", flush=True)
                row = run_one(t, b); row.update(task=t["id"], kind=t["kind"], rep=i + 1)
                rows.append(row)
                agg.setdefault((t["id"], b), []).append((row["duration_ms"] or 0) / 1000)
                sec = (row["duration_ms"] or 0) / 1000
                print(f"  {'PASS' if row['success'] else 'FAIL'}  {sec:6.1f}s  "
                      f"turns={row.get('num_turns')}  out={row.get('out_tokens')}", flush=True)

    (HERE / "dsgbench_results.json").write_text(json.dumps(rows, indent=2))

    def stat(vals):
        return (statistics.mean(vals), min(vals), max(vals),
                statistics.pstdev(vals) if len(vals) > 1 else 0.0)

    print(f"\n=== SUMMARY: wall-clock mean of {args.repeat} runs (local vs cloud) ===")
    print(f"{'task':<14}{'kind':<9}{'backend':<8}{'pass':>6}{'mean_s':>9}{'min':>7}{'max':>7}{'sd':>7}")
    for (tid, b), vals in agg.items():
        passes = sum(1 for r in rows if r["task"] == tid and r["backend"] == b and r["success"])
        m, lo, hi, sd = stat(vals)
        print(f"{tid:<14}{next(r['kind'] for r in rows if r['task']==tid):<9}{b:<8}"
              f"{passes:>3}/{len(vals):<2}{m:>9.1f}{lo:>7.1f}{hi:>7.1f}{sd:>7.1f}")

    print("\n=== mean local : cloud wall-clock ratio ===")
    for tid in dict.fromkeys(r["task"] for r in rows):
        if (tid, "local") in agg and (tid, "cloud") in agg:
            ml = statistics.mean(agg[(tid, "local")]); mc = statistics.mean(agg[(tid, "cloud")])
            if mc:
                print(f"  {tid:<14} {mc:6.1f}s cloud  {ml:7.1f}s local  = {ml/mc:.1f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
