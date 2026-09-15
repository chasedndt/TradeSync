#!/usr/bin/env python
"""Isolated, rolled-back SQL acceptance for migration 031 and the paper entry lock.

Two database connections, driven through psql:

* Session A runs one script inside one transaction: a throwaway schema, then 023,
  026 and 031 UP, 031 DOWN, 031 UP again. It checks the seeds, the append-only
  triggers and the check constraints, including funding adjustments. It then runs
  state-api's own statements, imported from its modules and prepared as they are,
  against seeded rows: reconciliation, marks and gaps, and the booking of a funding
  adjustment. That booking must move cash and funding by exactly the adjustment,
  once. Finally it takes advisory lock 230914 (the entry lock), holds it, and rolls
  back. ON_ERROR_STOP ends the session, uncommitted, on the first failed check.
* Session B, a separate connection per step, must see A holding the lock, fail to take
  it, block while waiting for it, acquire it only after A's rollback, and finally find
  the throwaway schema gone.

Unqualified names resolve only inside the throwaway schema (``SET LOCAL search_path``),
so nothing in the public schema is read or written; the advisory lock is the only shared
object touched, for a few seconds.

    python tools/qa_paper_risk_sql.py                  # docker exec into tradesync-full-postgres-1
    python tools/qa_paper_risk_sql.py --container qa-paper-risk-throwaway
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "services" / "state-api"), str(ROOT / "libs" / "tradesync_core")]

from app.paper_account_store import CLOSE_STATE_SQL, INSERT_ENTRY_SQL, POSITION_ENTRIES_SQL, STATES_AT_SQL, UPDATE_BALANCES_SQL  # noqa: E402
from app.paper_reconciliation_store import CLOSE_STATES_SQL, GAP_PAIRS_SQL, LAST_SEEN_SQL, LATEST_STATES_SQL, UPSERT_GAP_SQL  # noqa: E402
from ops.migrate import up_sql  # noqa: E402

ENTRY_LOCK = 230914
MIGRATIONS = ROOT / "ops" / "migrations"
P1, P2 = "aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"


def migration(name: str) -> tuple[str, str]:
    text = (MIGRATIONS / name).read_text(encoding="utf-8-sig")
    return up_sql(text), text.split("-- DOWN", 1)[1].strip()


def psql_command(args: argparse.Namespace) -> list[str]:
    flags = ["-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
    if args.local:
        host, port, user, database = args.local.split(":")
        return [args.psql_bin, *flags, "-h", host, "-p", port, "-U", user, "-d", database]
    return ["docker", "exec", "-i", args.container, "sh", "-c", "psql " + " ".join(flags) + ' -U "$POSTGRES_USER" -d "$POSTGRES_DB"']


def check(condition: str, failure: str) -> str:
    message = failure.replace("'", "''")
    return f"DO $$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'QA FAIL: {message}'; END IF; END $$;"


def refused(statement: str, sqlstate: str) -> str:
    return f"SELECT pg_temp.qa_refused($q${statement}$q$, '{sqlstate}');"


HELPERS = """CREATE FUNCTION pg_temp.qa_refused(statement text, expected text) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
  BEGIN
    EXECUTE statement;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = expected THEN RETURN; END IF;
    RAISE;
  END;
  RAISE EXCEPTION 'QA FAIL: expected SQLSTATE % from %', expected, statement;
END $f$;
CREATE FUNCTION pg_temp.qa_assert(ok boolean, message text) RETURNS void LANGUAGE plpgsql AS $f$
BEGIN
  IF ok IS NOT TRUE THEN RAISE EXCEPTION 'QA FAIL: %', message; END IF;
END $f$;"""


def seeds() -> list[str]:
    positions = (
        "INSERT INTO managed_paper_positions (id, opportunity_id, symbol, created_at, entry_evidence, evidence_sha256, initial_plan, position_state) VALUES "
        f"('{P1}', '11111111-1111-4111-8111-111111111111', 'BTC-PERP', now() - interval '1200 seconds', '{{}}', 'qa', '{{\"status\":\"open\"}}', '{{\"status\":\"open\",\"observations\":2,\"last_quote_time\":2}}'), "
        f"('{P2}', '22222222-2222-4222-8222-222222222222', 'ETH-PERP', now() - interval '1200 seconds', '{{}}', 'qa', '{{\"status\":\"open\"}}', '{{\"status\":\"closed\",\"observations\":1,\"last_quote_time\":1,\"exit_time\":1}}');")
    events = (
        "INSERT INTO managed_paper_events (id, position_id, kind, payload, created_at) VALUES "
        f"(gen_random_uuid(), '{P1}', 'opened', '{{\"status\":\"open\",\"observations\":0,\"last_quote_time\":0}}', now() - interval '1200 seconds'), "
        f"(gen_random_uuid(), '{P1}', 'observed', '{{\"position\":{{\"status\":\"open\",\"observations\":1,\"last_quote_time\":1}}}}', now() - interval '1195 seconds'), "
        f"(gen_random_uuid(), '{P1}', 'observed', '{{\"position\":{{\"status\":\"open\",\"observations\":2,\"last_quote_time\":2}}}}', now() - interval '1100 seconds'), "
        f"(gen_random_uuid(), '{P2}', 'opened', '{{\"status\":\"open\",\"observations\":0,\"last_quote_time\":0}}', now() - interval '1200 seconds'), "
        f"(gen_random_uuid(), '{P2}', 'closed', '{{\"position\":{{\"status\":\"closed\",\"observations\":1,\"last_quote_time\":1,\"exit_time\":1}}}}', now() - interval '1190 seconds');")
    return ["INSERT INTO opportunities VALUES ('11111111-1111-4111-8111-111111111111'), ('22222222-2222-4222-8222-222222222222');", positions, events]


def ledger_checks() -> list[str]:
    realised = ("INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, gross_pnl_usdc, fees_usdc, funding_usdc, "
                "balance_after_usdc) VALUES (gen_random_uuid(), 'realised', ")
    adjust = ("INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, funding_usdc, balance_after_usdc) "
              "VALUES (gen_random_uuid(), 'funding_adjustment', ")
    return [
        "INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc) VALUES (gen_random_uuid(), 'capital', clock_timestamp(), 10000, 10000);",
        "INSERT INTO paper_account (starting_capital_usdc, cash_usdc, last_sequence, peak_equity_usdc, peak_equity_at) SELECT 10000, 10000, max(sequence), 10000, clock_timestamp() FROM paper_account_ledger;",
        refused("UPDATE paper_account_ledger SET amount_usdc = 1", "P0001"),
        refused("DELETE FROM paper_account_ledger", "P0001"),
        refused("TRUNCATE paper_account_ledger", "P0001"),
        refused("INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc) VALUES (gen_random_uuid(), 'capital', clock_timestamp(), 1, 1)", "23505"),
        refused("INSERT INTO paper_account (starting_capital_usdc, cash_usdc, last_sequence, peak_equity_usdc, peak_equity_at) VALUES (1, 1, 1, 1, now())", "23505"),
        *seeds(),
        realised + f"'{P2}', clock_timestamp(), -1.5, -1, 0.4, 0.1, 9998.5);",
        refused(realised + f"'{P1}', clock_timestamp(), 5, 1, 0, 0, 1)", "23514"),
        refused(realised + f"'{P2}', clock_timestamp(), -1.5, -1, 0.4, 0.1, 9997)", "23505"),
        refused("INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, balance_after_usdc) VALUES (gen_random_uuid(), 'realised', clock_timestamp(), 1, 1)", "23514"),
        adjust + f"'{P2}', clock_timestamp(), -0.25, 0.25, 9998.25);",
        adjust + f"'{P2}', clock_timestamp(), 0.1, -0.1, 9998.35);",
        refused(adjust + f"'{P2}', clock_timestamp(), 0.25, 0.25, 1)", "23514"),
        refused(adjust + f"'{P2}', clock_timestamp(), 0, 0, 1)", "23514"),
        refused("INSERT INTO paper_account_ledger (id, kind, position_id, occurred_at, amount_usdc, gross_pnl_usdc, funding_usdc, balance_after_usdc) "
                f"VALUES (gen_random_uuid(), 'funding_adjustment', '{P2}', clock_timestamp(), 0.75, 1, 0.25, 1)", "23514"),
        refused("INSERT INTO paper_account_ledger (id, kind, occurred_at, amount_usdc, funding_usdc, balance_after_usdc) "
                "VALUES (gen_random_uuid(), 'funding_adjustment', clock_timestamp(), -0.25, 0.25, 1)", "23514"),
        "\\echo PASS ledger: append-only against UPDATE, DELETE and TRUNCATE; one capital row; one realised entry per position with amount "
        "equal to gross less fees and funding; any number of funding adjustments per position, each tied to it, with only funding and an amount of minus it",
    ]


def limit_and_kill_checks() -> list[str]:
    return [
        refused("UPDATE paper_risk_limits SET max_symbol_exposure_fraction = 0.5", "23514"),
        refused("UPDATE paper_risk_limits SET max_drawdown_fraction = 1", "23514"),
        refused("UPDATE paper_risk_limits SET max_concurrent_positions = 0", "23514"),
        refused("INSERT INTO paper_risk_limits (singleton) VALUES (false)", "23514"),
        refused("INSERT INTO paper_risk_limit_events (id, operator, reason, previous, updated) VALUES (gen_random_uuid(), 'qa', 'shrt', '{}', '{}')", "23514"),
        "INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES (gen_random_uuid(), 'kill', 'qa', 'Acceptance kill switch row');",
        refused("INSERT INTO paper_kill_switch_events (id, action, operator, reason) VALUES (gen_random_uuid(), 'close', 'qa', 'Close without a position')", "23514"),
        refused("UPDATE paper_kill_switch_events SET reason = 'Rewritten afterwards'", "P0001"),
        "\\echo PASS limits and kill switch: ordering and ranges enforced, singletons, audit rows append-only with meaningful reasons",
    ]


def prepared_reads() -> list[str]:
    return [
        f"PREPARE qa_upsert_gap(uuid, uuid, text, timestamptz, timestamptz) AS {UPSERT_GAP_SQL};",
        f"EXECUTE qa_upsert_gap(gen_random_uuid(), '{P1}', 'BTC-PERP', now() - interval '1195 seconds', NULL);",
        f"EXECUTE qa_upsert_gap(gen_random_uuid(), '{P1}', 'BTC-PERP', now() - interval '1195 seconds', now() - interval '1100 seconds');",
        f"EXECUTE qa_upsert_gap(gen_random_uuid(), '{P1}', 'BTC-PERP', now() - interval '1195 seconds', NULL);",
        check("(SELECT count(*) FROM paper_observation_gaps) = 1 AND (SELECT ended_at FROM paper_observation_gaps) = now() - interval '1100 seconds'",
              "gap upsert must gain its end once and never lose it"),
        refused(f"INSERT INTO paper_observation_gaps (id, position_id, symbol, started_at, ended_at) VALUES (gen_random_uuid(), '{P1}', 'BTC-PERP', now(), now() - interval '1 second')", "23514"),
        f"PREPARE qa_gap_pairs(float8) AS {GAP_PAIRS_SQL};",
        "CREATE TEMP TABLE qa_gaps AS EXECUTE qa_gap_pairs(45);",
        check("(SELECT count(*) FROM qa_gaps) = 1 AND (SELECT round((ended_s - started_s)::numeric) FROM qa_gaps) = 95", "gap pairs"),
        f"PREPARE qa_last_seen AS {LAST_SEEN_SQL};",
        "CREATE TEMP TABLE qa_seen AS EXECUTE qa_last_seen;",
        check("(SELECT count(*) FROM qa_seen) = 1 AND (SELECT symbol = 'BTC-PERP' AND last_at = now() - interval '1100 seconds' FROM qa_seen)", "last observation of open positions"),
        f"PREPARE qa_latest AS {LATEST_STATES_SQL};",
        "CREATE TEMP TABLE qa_latest_rows AS EXECUTE qa_latest;",
        check("(SELECT count(*) FROM qa_latest_rows) = 5", "latest lifecycle candidates"),
        f"PREPARE qa_closes AS {CLOSE_STATES_SQL};",
        "CREATE TEMP TABLE qa_close_rows AS EXECUTE qa_closes;",
        check("(SELECT count(*) FROM qa_close_rows) = 1", "closed-event states"),
        f"PREPARE qa_states_at(timestamptz, float8) AS {STATES_AT_SQL};",
        "CREATE TEMP TABLE qa_states AS EXECUTE qa_states_at(now() - interval '1150 seconds', extract(epoch FROM now() - interval '1150 seconds'));",
        check("(SELECT count(*) FROM qa_states) = 2", "states at a day boundary"),
        "\\echo PASS state-api reads as prepared: gap upsert, one 95-second gap, last observation, lifecycle candidates, closed-event states, boundary states",
    ]


def prepared_booking() -> list[str]:
    return [
        "SELECT last_sequence AS qa_last FROM paper_account \\gset",
        f"PREPARE qa_position_entries AS {POSITION_ENTRIES_SQL};",
        f"PREPARE qa_close_state AS {CLOSE_STATE_SQL};",
        f"PREPARE qa_insert_entry AS {INSERT_ENTRY_SQL};",
        f"PREPARE qa_update_balances AS {UPDATE_BALANCES_SQL};",
        f"CREATE TEMP TABLE qa_close_state_row AS EXECUTE qa_close_state('{P2}');",
        check("(SELECT count(*) FROM qa_close_state_row) = 1", "a position's closed-event state"),
        # An INSERT ... RETURNING cannot feed CREATE TABLE AS; psql captures its one row instead (qa_sequence).
        f"EXECUTE qa_insert_entry(gen_random_uuid(), 'funding_adjustment', '{P2}', 1789.5, -0.3, 0, 0, 0.3, 0, 9999.7, "
        "'{\"funding_source\": \"settled\"}') \\gset qa_",
        "EXECUTE qa_update_balances(9999.7, -0.3, 0, 0, 0.3, 0, 0, :qa_sequence, :qa_last);",
        "EXECUTE qa_update_balances(9999.4, -0.3, 0, 0, 0.3, 0, 0, :qa_sequence, :qa_last);",
        "SELECT pg_temp.qa_assert((SELECT cash_usdc = 9999.7 AND funding_usdc = 0.3 AND realised_pnl_usdc = -0.3 AND closed_positions = 0 "
        "AND last_sequence = :qa_sequence FROM paper_account), 'a booked adjustment moves cash, funding and realised by exactly its amount, and only once');",
        f"CREATE TEMP TABLE qa_booked AS EXECUTE qa_position_entries('{P2}');",
        check("(SELECT count(*) FROM qa_booked) = 4 AND (SELECT sum(funding_usdc) FROM qa_booked) = 0.55", "a position's booked funding"),
        "\\echo PASS state-api booking as prepared: a funding adjustment appended and the balances moved by exactly it, a repeat against the old sequence refused, the position's booked funding read back",
    ]


def session_a_script(schema: str, application: str, hold_s: float) -> str:
    up23, _ = migration("023_managed_paper_positions.sql")
    up26, _ = migration("026_paper_control.sql")
    up31, down31 = migration("031_paper_risk_engine.sql")
    return "\n".join([
        f"SET application_name = '{application}';",
        "BEGIN;",
        f"CREATE SCHEMA {schema};",
        f"SET LOCAL search_path TO {schema};",
        "CREATE TABLE opportunities (id uuid PRIMARY KEY);",
        up23 + ";", up26 + ";", up31 + ";",
        "\\echo PASS 031 UP applied after 023 and 026 in an isolated schema",
        down31,
        check("to_regclass('paper_account') IS NULL AND to_regclass('paper_risk_limits') IS NULL AND NOT EXISTS (SELECT 1 FROM information_schema.columns "
              "WHERE table_schema = current_schema() AND table_name = 'managed_paper_control_events' AND column_name = 'operator')",
              "031 DOWN left objects behind"),
        "\\echo PASS 031 DOWN removed its tables, function and the operator column",
        up31 + ";",
        "\\echo PASS 031 UP applied again",
        HELPERS,
        check("(SELECT count(*) FROM paper_risk_limits) = 1 AND (SELECT daily_loss_limit_usdc = 200 AND max_drawdown_fraction = 0.06 AND max_concurrent_positions = 3 FROM paper_risk_limits)",
              "limit seeds"),
        check("(SELECT active FROM paper_kill_switch) IS FALSE AND (SELECT entries_paused FROM managed_paper_control) IS TRUE", "kill and pause seeds"),
        "INSERT INTO managed_paper_control_events (id, entries_paused, reason) VALUES (gen_random_uuid(), true, 'Earlier route without an operator');",
        check("(SELECT operator FROM managed_paper_control_events) = 'unrecorded'", "operator default on pause audit rows"),
        "\\echo PASS seeds: conservative limits, kill switch disengaged, entries paused, pause audit operator defaults to unrecorded",
        *ledger_checks(),
        *limit_and_kill_checks(),
        *prepared_reads(),
        *prepared_booking(),
        f"SELECT pg_advisory_xact_lock({ENTRY_LOCK});",
        f"SELECT pg_sleep({hold_s});",
        "SELECT 'A_RELEASE_AT ' || extract(epoch FROM clock_timestamp());",
        "ROLLBACK;",
        "\\echo PASS session A rolled back",
    ])


def one_shot(command: list[str], sql: str, timeout: float = 90) -> tuple[int, str]:
    result = subprocess.run(command, input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return result.returncode, (result.stdout + result.stderr).strip()


def lock_rows(command: list[str], application: str, granted: bool) -> int:
    code, out = one_shot(command, "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                  f"WHERE l.locktype = 'advisory' AND l.objid = {ENTRY_LOCK} AND l.objsubid = 1 "
                                  f"AND l.granted = {str(granted).lower()} AND a.application_name = '{application}';")
    return int(out.splitlines()[-1]) if code == 0 and out else -1


def a_lock_state(command: list[str], application: str) -> str:
    """'true' while session A holds the entry lock, 'false' while it waits for it, 'none' before it asks."""
    code, out = one_shot(command, "SELECT coalesce(bool_or(l.granted)::text, 'none') FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                  f"WHERE l.locktype = 'advisory' AND l.objid = {ENTRY_LOCK} AND l.objsubid = 1 AND a.application_name = '{application}';")
    return out.splitlines()[-1].strip() if code == 0 and out else "unknown"


def other_holders(command: list[str], application: str) -> str:
    code, out = one_shot(command, "SELECT coalesce(string_agg(l.pid || ' ' || coalesce(nullif(a.application_name, ''), 'unnamed client') || ', ' || a.state "
                                  "|| ' for ' || date_trunc('second', now() - a.xact_start), '; '), 'nobody') FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                                  f"WHERE l.locktype = 'advisory' AND l.objid = {ENTRY_LOCK} AND l.objsubid = 1 AND l.granted "
                                  f"AND a.application_name <> '{application}';")
    return out.splitlines()[-1] if code == 0 and out else "unknown"


def terminate_own(command: list[str], application: str) -> None:
    """End this run's own backend, whose transaction then rolls back. No other session is touched."""
    one_shot(command, f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = '{application}';")


class Background:
    def __init__(self, command: list[str], sql: str):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace")
        self.lines: list[str] = []
        self.reader = threading.Thread(target=lambda: self.lines.extend(line.rstrip("\r\n") for line in self.proc.stdout), daemon=True)
        self.reader.start()
        self.proc.stdin.write(sql)
        self.proc.stdin.close()

    def finish(self, timeout: float) -> int:
        code = self.proc.wait(timeout=timeout)
        self.reader.join(timeout=5)
        return code

    def value(self, prefix: str) -> float:
        return float(next(line for line in self.lines if line.startswith(prefix)).split()[1])


def wait_for(predicate, timeout: float, alive=lambda: True) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and alive():
        if predicate():
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--container", default="tradesync-full-postgres-1")
    parser.add_argument("--local", help="host:port:user:database for a throwaway local cluster")
    parser.add_argument("--psql-bin", default="psql")
    parser.add_argument("--hold", type=float, default=12.0, help="seconds session A holds the entry lock")
    parser.add_argument("--lock-wait", type=float, default=420.0, help="seconds session A may queue behind another holder of the entry lock")
    args = parser.parse_args()
    command = psql_command(args)
    run = uuid.uuid4().hex[:12]
    schema, app_a, app_b = f"qa_paper_risk_{run}", f"qa_paper_risk_a_{run}", f"qa_paper_risk_b_{run}"
    failures: list[str] = []

    session_a = Background(command, session_a_script(schema, app_a, args.hold))
    queued = []

    def holding() -> bool:
        state = a_lock_state(command, app_a)
        if state == "false" and not queued:
            queued.append(True)  # another session holds the entry lock; wait behind it rather than contend
            print("WAIT session A is queued for entry lock 230914 behind: " + other_holders(command, app_a), flush=True)
        return state == "true"

    if not wait_for(holding, args.lock_wait, alive=lambda: session_a.proc.poll() is None):
        if session_a.proc.poll() is None:
            terminate_own(command, app_a)  # the client alone may not end psql inside a container
            session_a.proc.kill()
        session_a.finish(120)
        print("\n".join(session_a.lines))
        print("FAIL: session A did not hold the entry lock (a check above failed, or the wait ran out); nothing was committed")
        return 1
    print("PASS session A holds entry lock 230914 inside its uncommitted transaction")

    code, out = one_shot(command, f"SELECT pg_try_advisory_xact_lock({ENTRY_LOCK});")
    (print if out.endswith("f") else failures.append)("PASS session B cannot take the entry lock while A holds it" if out.endswith("f") else f"B try-lock: {out}")
    code, out = one_shot(command, f"SET lock_timeout = '500ms'; SELECT pg_advisory_xact_lock({ENTRY_LOCK});")
    ok = code != 0 and "lock timeout" in out
    (print if ok else failures.append)("PASS session B's blocking attempt times out while A holds it" if ok else f"B lock timeout: {code} {out}")

    waiter = Background(command, f"SET application_name = '{app_b}';\n"
                                 f"SELECT pg_advisory_xact_lock({ENTRY_LOCK});\nSELECT 'B_ACQUIRED_AT ' || extract(epoch FROM clock_timestamp());\n")
    blocked = wait_for(lambda: lock_rows(command, app_b, False) == 1, 60, alive=lambda: waiter.proc.poll() is None)
    (print if blocked else failures.append)("PASS session B waits for the entry lock" if blocked else "B was never seen waiting for the lock")

    a_code = session_a.finish(args.hold + 120)
    b_code = waiter.finish(120)
    print("\n".join(line for line in session_a.lines if line.startswith("PASS")))
    if a_code != 0:
        failures.append("session A: " + " | ".join(session_a.lines[-8:]))
    else:
        acquired, released = waiter.value("B_ACQUIRED_AT"), session_a.value("A_RELEASE_AT")
        ok = b_code == 0 and acquired >= released
        (print if ok else failures.append)(f"PASS session B acquired the lock {acquired - released:.3f}s after A released it" if ok else f"B acquired {acquired} before release {released}")

    code, out = one_shot(command, f"SELECT pg_try_advisory_xact_lock({ENTRY_LOCK});")
    (print if out.endswith("t") else failures.append)("PASS the entry lock is free after A's rollback" if out.endswith("t") else f"final try-lock: {out}")
    code, out = one_shot(command, f"SELECT count(*) FROM pg_namespace WHERE nspname = '{schema}';")
    (print if out.endswith("0") else failures.append)("PASS throwaway schema is gone: nothing was committed" if out.endswith("0") else f"schema still present: {out}")

    for failure in failures:
        print("FAIL: " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
