"""Fleet job errors are redacted before storage and reduced to a plain cause on the dashboard."""

from __future__ import annotations

from tradesync_core.job_errors import MAX_ERROR_CHARS, diagnose, redact


def test_redacts_token_shapes_webhooks_and_labelled_secrets() -> None:
    token = f"{'x' * 24}.abcdef.{'y' * 38}"
    text = (f"failed with {token} posting to https://discord.com/api/webhooks/123/abcDEF_-9 "
            "using Bearer abcdefghijklmnop and api_key=supersecretvalue1")
    out = redact(text)
    for secret in ("x" * 24, "abcDEF_-9", "abcdefghijklmnop", "supersecretvalue1"):
        assert secret not in out
    assert out.count("[redacted]") >= 4
    assert redact("") is None and redact(None) is None
    assert len(redact("z " * 5000)) == MAX_ERROR_CHARS


def test_windows_line_endings_are_named() -> None:
    shell = ("Script exited with code 2\nstderr:\n/home/x/scripts/strikezone_health_watchdog.sh: line 14: "
             "set: pipefail\r: invalid option name\n/home/x/s.sh: line 15: $'\\r': command not found")
    env = "Script exited with code 127\nstderr:\n/usr/bin/env: 'python3\r': No such file or directory"
    assert "CRLF" in diagnose(shell) and "CRLF" in diagnose(env)


def test_dns_failures_and_integrity_holds_are_named() -> None:
    dns = ("delivery error: Discord send failed: ClientConnectorDNSError: Cannot connect to host discord.com:443 "
           "ssl:default [Temporary failure in name resolution]")
    assert diagnose(dns) == "A network name lookup failed inside WSL for discord.com, so the job could not reach it."
    hold = ("Script exited with code 1\nstdout:\n## Hyperliquid Quant Integrity Hold\n\n"
            "- `funding_archive_stale`\n- `signal_ledger_stale`\n")
    assert diagnose(hold).startswith("Integrity hold (funding_archive_stale, signal_ledger_stale).")


def test_tracebacks_give_the_exception_or_say_it_was_cut_off() -> None:
    full = ('Script exited with code 1\nstderr:\nTraceback (most recent call last):\n  File "/a/b/weekly.py", line 3, '
            "in <module>\n    main()\nKeyError: 'members'")
    assert diagnose(full) == "Python error: KeyError: 'members'"
    cut = ('Script exited with code 1\nstderr:\nTraceback (most recent call last):\n'
           '  File "/home/x/scripts/strikezone/step6h_autonomous_cycle.py",')
    assert diagnose(cut) == "Python error in step6h_autonomous_cycle.py; the recorded error was cut off before the exception line."


def test_ok_reports_with_a_failing_exit_and_unknown_errors() -> None:
    ok_but_failed = 'Script exited with code 1\nstdout:\n{\n  "ok": true,\n  "dry_run": false\n}'
    assert diagnose(ok_but_failed) == "The script reported ok but exited with code 1."
    assert diagnose("Script exited with code 3\nstdout:\nsomething odd happened") == "something odd happened"
    assert diagnose(None) is None and diagnose("") is None
