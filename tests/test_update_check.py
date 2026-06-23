from types import SimpleNamespace

from eddy import update_check


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_update_check_is_notify_only(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run(root, args, timeout=20):
        calls.append(args)
        if args == ["rev-parse", "HEAD"]:
            return _proc(stdout="localsha\n")
        if args == ["remote", "get-url", "origin"]:
            return _proc(stdout="git@example.com:lennoxsaint/eddy.git\n")
        if args == ["ls-remote", "origin", "refs/heads/main"]:
            return _proc(stdout="remotesha\trefs/heads/main\n")
        raise AssertionError(args)

    monkeypatch.setattr(update_check, "_run", fake_run)
    result = update_check.check_for_update(repo)

    assert result["status"] == "update_available"
    assert result["mutated"] is False
    assert ["fetch"] not in calls
    assert ["pull"] not in calls
    assert calls == [
        ["rev-parse", "HEAD"],
        ["remote", "get-url", "origin"],
        ["ls-remote", "origin", "refs/heads/main"],
    ]
