"""Exercise a built wheel without the repository on its import path."""

import json
import os
import subprocess
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    wheels = list((root / "dist").glob(f"sift_research-{version}-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one wheel for version {version}, found {len(wheels)}.")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for required in (
            "sift/bundled_skill/SKILL.md",
            "sift/bundled_skill/agents/openai.yaml",
            "sift/bundled_skill/references/workflows.md",
            "sift/bundled_harness/policy.json",
            "sift/cli.py",
            "sift/api.py",
            "sift/templates/notebook.py.txt",
        ):
            assert required in names, required
    with tempfile.TemporaryDirectory(prefix="sift-wheel-") as directory:
        temporary = Path(directory)
        environment = temporary / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], check=True)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        def run(*arguments):
            result = subprocess.run(
                [str(python), "-I", "-m", "sift", *arguments],
                cwd=temporary,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            return result.stdout

        assert f"sift {version}" in run("--version")
        help_text = run("--help")
        for command in ("status", "review", "reproduce", "propose", "archive"):
            assert command in help_text
        assert "--editor" in run("review", "--help")
        assert "--reviewer" in run("review", "--help")
        assert "--terminal" in run("review", "--help")
        run("skill", "install", "--target", str(temporary / "skills"))
        assert (temporary / "skills/sift/SKILL.md").is_file()
        assert json.loads(run("harness", "policy"))["actor"] == "agent"
        project = temporary / "research"
        run("init", str(project))
        result = subprocess.run(
            [str(python), "-I", "-m", "sift", "--json", "explore", "wheel-test"],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(result.stdout)["result"]["path"]
        status = subprocess.run(
            [str(python), "-I", "-m", "sift", "--json", "status"],
            cwd=project,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(status.stdout)["result"]["explorations"] == ["wheel-test"]
    print("Wheel install, isolated import, CLI, bundled skill, and harness passed.")


if __name__ == "__main__":
    main()
