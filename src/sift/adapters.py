from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .errors import SiftError
from .util import contained_path, safe_id, sha256_file, write_json


@dataclass(frozen=True)
class ArtifactRef:
    sha256: str
    name: str
    store: str


class ArtifactStore(Protocol):
    def put(self, source: Path) -> ArtifactRef: ...
    def get(self, reference: ArtifactRef, destination: Path) -> Path: ...


class LocalArtifactStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def put(self, source: Path) -> ArtifactRef:
        if not source.is_file():
            raise SiftError("Artifact stores accept files; export directory bundles separately.")
        digest = sha256_file(source)
        target = contained_path(self.root, digest)
        self.root.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(".pending")
            shutil.copy2(source, temporary)
            temporary.replace(target)
        if sha256_file(target) != digest:
            raise SiftError("Stored artifact content is corrupted.")
        reference = ArtifactRef(digest, source.name, str(self.root))
        write_json(self.root / f"{digest}.json", asdict(reference))
        return reference

    def get(self, reference: ArtifactRef, destination: Path) -> Path:
        source = contained_path(self.root, safe_id(reference.sha256))
        if not source.is_file() or sha256_file(source) != reference.sha256:
            raise SiftError("Artifact is unavailable or corrupted.")
        if destination.exists():
            raise SiftError("Artifact destination already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination


class CommandArtifactStore:
    def __init__(self, put_command: list[str], get_command: list[str]):
        self.put_command, self.get_command = put_command, get_command

    def _run(self, template: list[str], **values) -> None:
        command = [part.format(**values) for part in template]
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            raise SiftError(f"Artifact adapter exited with status {completed.returncode}.")

    def put(self, source: Path) -> ArtifactRef:
        reference = ArtifactRef(sha256_file(source), source.name, "command")
        self._run(self.put_command, source=str(source), sha256=reference.sha256)
        return reference

    def get(self, reference: ArtifactRef, destination: Path) -> Path:
        if destination.exists():
            raise SiftError("Artifact destination already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._run(self.get_command, destination=str(destination), sha256=reference.sha256)
        if not destination.is_file() or sha256_file(destination) != reference.sha256:
            raise SiftError("Artifact adapter returned different content.")
        return destination


class Runner(Protocol):
    def argv(self, command: str) -> list[str]: ...


class LocalRunner:
    def argv(self, command: str) -> list[str]:
        if os.name == "nt":
            return [
                sys.executable,
                "-c",
                "import os,re,shutil,subprocess,sys\n"
                "command=sys.argv[1]\n"
                'match=re.match(r\'^\\s*(?:"([^"]+)"|(\\S+))\',command)\n'
                "program=shutil.which((match[1] or match[2])) if match else None\n"
                "operators=any(t in ('&','|','<','>') for t in "
                're.findall(r\'"[^"]*"|[^"&|<>]+|[&|<>]\',command))\n'
                "direct=program and not operators "
                "and not program.lower().endswith(('.cmd','.bat'))\n"
                "if direct:\n"
                "    command=subprocess.list2cmdline([program])+command[match.end():]\n"
                "    sys.exit(subprocess.call(command))\n"
                "cwd=os.getcwd()\n"
                "if cwd.startswith('\\\\\\\\?\\\\UNC\\\\'):\n"
                "    cwd='\\\\\\\\'+cwd[8:]\n"
                "elif cwd.startswith('\\\\\\\\?\\\\'):\n"
                "    cwd=cwd[4:]\n"
                "sys.exit(subprocess.call(command,shell=True,cwd=cwd))",
                command,
            ]
        return ["/bin/sh", "-c", command]


class CommandRunner:
    def __init__(self, prefix: list[str]):
        self.prefix = prefix

    def argv(self, command: str) -> list[str]:
        return [*self.prefix, *LocalRunner().argv(command)]


def runner_for(launcher: str | None) -> Runner:
    return CommandRunner(shlex.split(launcher)) if launcher else LocalRunner()
