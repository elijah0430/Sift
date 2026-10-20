"""Exercise a built wheel without the repository on its import path."""

import json
import os
import subprocess
import tempfile
import venv
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    wheel = next((root / "dist").glob("sift_research-*.whl"))
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

        assert "sift" in run("--version")
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
    print("Wheel install, isolated import, CLI, bundled skill, and harness passed.")


if __name__ == "__main__":
    main()
