"""2026-09-16 진단 재현. 임시 Git 레포만 수정하며 현재 한계가 관찰되면 출력한다.

정상 동작을 보증하는 테스트가 아니다. 해당 문제를 수정하면 이 진단의 assert는 실패한다.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins/fullops-squad/scripts"


def run(script, *args):
    return subprocess.run(["python3", str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)


def repo_at(root, name):
    repo = root / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert run("setup.py", "--repo", repo, "--roles", "backend_dev", "--local-only").returncode == 0
    return repo, repo / ".fullops-squad"


def task(repo, key):
    return run("work.py", "new", "--repo", repo, "--role", "backend_dev",
               "--key", key, "--goal", "진단 과제")


def finish(repo, key):
    return run("work.py", "finish", "--repo", repo, "--role", "backend_dev", "--key", key)


def main():
    with tempfile.TemporaryDirectory(prefix="fullops-diagnosis-") as temp:
        root = Path(temp)
        repo, base = repo_at(root, "completion")
        assert task(repo, "AUDIT-1").returncode == 0
        inbox = base / "handovers/to_backend_dev.md"
        content = inbox.read_text().replace("- 상태: ready / running / blocked", "- 상태: blocked")
        content += "\n테스트 실패. 구현은 진행 중이며 완료하지 못했다.\n"
        inbox.write_text(content)
        assert finish(repo, "AUDIT-1").returncode == 0 and inbox.read_bytes() == b""
        print("OBSERVED: blocked + unchecked task was archived and inbox cleared")

        assert task(repo, "AUDIT-1").returncode == 0
        inbox.write_text(content)
        assert finish(repo, "AUDIT-1").returncode != 0 and inbox.read_text() == content
        print("OBSERVED: reused key accepted by new, rejected by finish")

        repo, base = repo_at(root, "empty-approved")
        index = base / "docs/deliverables/README.md"
        index.write_text(index.read_text().replace(
            "`docs/planning/product-specs/` | 미작성", "`docs/planning/product-specs/` | approved"))
        assert run("deliverables.py", "--repo", repo, "--id", "D02").returncode == 0
        assert not list((base / "docs/deliverables").glob("D02_*.md"))
        print("OBSERVED: approved empty source directory and absent D02 artifact passed")

        repo, base = repo_at(root, "anchor")
        source = base / "docs/planning/business-plan.md"
        source.write_text("# 실제 제목\n")
        index = base / "docs/deliverables/README.md"
        index.write_text(index.read_text().replace(
            "`docs/planning/business-plan.md` | 미작성", "`docs/planning/business-plan.md` | approved"))
        (base / "docs/deliverables/D01_business-plan.md").write_text(
            "[없는 절](../planning/business-plan.md#missing-section)\n")
        assert run("deliverables.py", "--repo", repo, "--id", "D01").returncode == 0
        print("OBSERVED: nonexistent source section anchor passed")

        repo, base = repo_at(root, "custom-template")
        template = base / "handovers/_TEMPLATE.md"
        template.write_text(template.read_text() + "\n## 프로젝트 고유 승인 근거\n")
        assert task(repo, "AUDIT-2").returncode == 0
        assert "프로젝트 고유 승인 근거" not in (base / "handovers/to_backend_dev.md").read_text()
        print("OBSERVED: repository handover template override ignored")

        repo, base = repo_at(root, "upgrade")
        guide = base / "FULLOPS.md"
        guide.write_text("# 이전 규약\nworkflows/handover.md를 읽는다.\n")
        marker = base / "fullops.json"
        marker.write_text('{"schema_version": 1, "plugin_version": "0.0.0"}')
        assert run("setup.py", "--repo", repo).returncode == 0
        assert "workflows/handover.md" in guide.read_text() and "0.0.0" in marker.read_text()
        print("OBSERVED: setup retained stale workflow pointer and old plugin_version")

        repo, base = repo_at(root, "marker")
        (base / "fullops.json").write_text("[]")
        assert run("setup.py", "--repo", repo).returncode != 0
        assert task(repo, "AUDIT-3").returncode == 0
        assert run("deliverables.py", "--repo", repo).returncode == 0
        print("OBSERVED: malformed marker rejected by setup, accepted by work and deliverables")


if __name__ == "__main__":
    main()
