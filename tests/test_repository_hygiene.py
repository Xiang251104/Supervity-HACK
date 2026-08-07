from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_shell_scripts_are_checked_out_with_lf_line_endings() -> None:
    attributes_path = REPOSITORY_ROOT / ".gitattributes"

    assert attributes_path.exists(), ".gitattributes must define repository EOL policy"
    rules = {
        " ".join(line.split())
        for line in attributes_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "*.sh text eol=lf" in rules


def test_linux_startup_script_contains_no_crlf_line_endings() -> None:
    startup_script = (REPOSITORY_ROOT / "start_gunicorn.sh").read_bytes()

    assert b"\r\n" not in startup_script
