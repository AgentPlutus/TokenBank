"""Typer CLI for TokenBank Phase 0 bootstrap and schemas."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from tokenbank import PHASE_0_NAME, PRODUCT_NAME, __version__
from tokenbank.app.api import create_app
from tokenbank.app.bootstrap import rebuild_capacity_projection_from_config_and_db
from tokenbank.capacity.discovery import discover_capacity_nodes
from tokenbank.config_runtime.loader import load_config_dir
from tokenbank.config_runtime.validator import validate_config_dir
from tokenbank.db.bootstrap import initialize_database
from tokenbank.demo.private_capacity import PrivateCapacityDemoRunner
from tokenbank.host_adapter import HostAdapterCore, MCPStdioServer
from tokenbank.host_adapter.normalizer import HostAdapterInputError
from tokenbank.observability.report_generator import (
    generate_capacity_report,
    generate_cost_quality_report,
)
from tokenbank.schemas.export import export_schema_files
from tokenbank.worker.config import load_worker_config
from tokenbank.worker.daemon import run_worker_from_config

app = typer.Typer(
    add_completion=False,
    help=(
        f"{PRODUCT_NAME} Phase 0: {PHASE_0_NAME}. "
        "VS0 url_check, VS1a dedup, VS1b webpage_extraction, "
        "VS1c topic_classification, and VS1d claim_extraction are "
        "end-to-end; WP11 observability, WP12 MCP, WP-RB1 route "
        "explanation, WP-RB2 task analysis, WP-RB3 route scoring, "
        "and WP-LEDGER1 local ledger/audit receipts are implemented."
    ),
    no_args_is_help=True,
)
schemas_app = typer.Typer(
    add_completion=False,
    help="JSON Schema wire contract commands.",
)
config_app = typer.Typer(
    add_completion=False,
    help="Runtime config validation commands.",
)
daemon_app = typer.Typer(
    add_completion=False,
    help="Control-plane daemon commands.",
)
worker_app = typer.Typer(
    add_completion=False,
    help="Foreground worker daemon commands.",
)
host_app = typer.Typer(
    add_completion=False,
    help="Minimal host adapter commands.",
)
workunit_app = typer.Typer(
    add_completion=False,
    help="Schema-bound Work Unit commands through HostAdapterCore.",
)
route_app = typer.Typer(
    add_completion=False,
    help="Route planning and explanation commands.",
)
capacity_app = typer.Typer(
    add_completion=False,
    help="Capacity discovery commands.",
)
report_app = typer.Typer(
    add_completion=False,
    help="Derived cost and quality report commands.",
)
accounts_app = typer.Typer(
    add_completion=False,
    help="Local account snapshot commands.",
)
usage_app = typer.Typer(
    add_completion=False,
    help="Local usage ledger commands.",
)
audit_app = typer.Typer(
    add_completion=False,
    help="Hash-backed audit receipt commands.",
)
mcp_app = typer.Typer(
    add_completion=False,
    help="P0 MCP stdio stub commands.",
)
demo_app = typer.Typer(
    add_completion=False,
    help="Private capacity demo commands.",
)
demo_capacity_app = typer.Typer(
    add_completion=False,
    help="Private Capacity Network demo runner.",
)
SCHEMA_OUTPUT_DIR_OPTION = typer.Option(
    Path("schemas"),
    "--output-dir",
    "-o",
    help="Directory where JSON Schema artifacts are written.",
)
CONFIG_DIR_OPTION = typer.Option(
    Path("config"),
    "--config-dir",
    "-c",
    help="Directory containing TokenBank YAML config files.",
)
DB_PATH_OPTION = typer.Option(
    Path(".tokenbank/tokenbank.db"),
    "--db-path",
    help="SQLite control-plane database path.",
)
HOST_OPTION = typer.Option("127.0.0.1", "--host", help="Daemon bind host.")
PORT_OPTION = typer.Option(8765, "--port", help="Daemon bind port.")
SMOKE_TEST_OPTION = typer.Option(
    False,
    "--smoke-test",
    help="Validate config and bootstrap DB, then exit without serving.",
)
WORKER_CONFIG_OPTION = typer.Option(
    ...,
    "--config",
    "-c",
    help="Worker YAML config path.",
)
WORKUNIT_INPUT_OPTION = typer.Option(
    ...,
    "--input",
    "-i",
    help="Explicit JSON file containing the Work Unit input.",
)
ROUTEBOOK_V1_DIR_OPTION = typer.Option(
    Path("packs/base-routing/routebook"),
    "--routebook-v1-dir",
    help="Routebook V1 package directory.",
)
DEMO_DIR_OPTION = typer.Option(
    Path("examples/private_capacity_demo"),
    "--demo-dir",
    help="Directory containing private capacity demo fixtures.",
)


@app.callback(invoke_without_command=True)
def root(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the TokenBank package version.",
    ),
) -> None:
    """Private Agent Capacity Network control-plane bootstrap."""
    if version:
        typer.echo(f"{PRODUCT_NAME} {__version__}")
        raise typer.Exit()


@app.command()
def about() -> None:
    """Print the Phase 0 product boundary."""
    typer.echo(f"{PRODUCT_NAME} Phase 0 is a {PHASE_0_NAME}.")
    typer.echo(
        "This VS0 foundation submits url_check WorkUnits, routes, schedules, "
        "executes worker-local LocalToolAdapter results, verifies them, and "
        "produces HostResultSummary. VS1a extends the same path to dedup via "
        "local_script; VS1b extends it to webpage_extraction via browser_fetch. "
        "VS1c extends it to topic_classification through the control-plane "
        "api_model_gateway deterministic stub. VS1d extends it to "
        "claim_extraction through the same control-plane gateway stub. "
        "WP11 adds derived cost/quality memory; WP12 adds HostAdapterCore "
        "and a bounded MCP stdio stub; WP-RB1 adds Routebook V1 profiles "
        "and route explanation without changing route selection. WP-RB2 adds "
        "deterministic task analysis and token/cost/privacy estimates. "
        "WP-RB3 applies deterministic route scoring. WP-LEDGER1 records "
        "local account snapshots, usage ledger entries, and redacted audit "
        "receipts."
    )


@schemas_app.command("export")
def export_schemas(
    output_dir: Path = SCHEMA_OUTPUT_DIR_OPTION,
) -> None:
    """Export deterministic JSON Schema artifacts from Pydantic DTOs."""
    written = export_schema_files(output_dir)
    typer.echo(f"Exported {len(written)} schema files to {output_dir}")


@config_app.command("validate")
def validate_config(
    config_dir: Path = CONFIG_DIR_OPTION,
) -> None:
    """Validate runtime config, policy, and registry consistency."""
    result = validate_config_dir(config_dir)
    if result.ok:
        typer.echo(f"Config valid: {config_dir}")
        return

    for issue in result.issues:
        typer.echo(f"{issue.code}: {issue.message}", err=True)
    raise typer.Exit(code=1)


@daemon_app.command("start")
def daemon_start(
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
    host: str = HOST_OPTION,
    port: int = PORT_OPTION,
    smoke_test: bool = SMOKE_TEST_OPTION,
) -> None:
    """Start the single-process FastAPI control-plane daemon."""
    validation = validate_config_dir(config_dir)
    if not validation.ok:
        for issue in validation.issues:
            typer.echo(f"{issue.code}: {issue.message}", err=True)
        raise typer.Exit(code=1)

    loaded_config = load_config_dir(config_dir)
    conn = initialize_database(db_path)
    try:
        count = rebuild_capacity_projection_from_config_and_db(conn, loaded_config)
    finally:
        conn.close()

    if smoke_test:
        typer.echo(f"Daemon smoke test ok: capacity_node_count={count}")
        return

    import uvicorn

    app_instance = create_app(config_dir=config_dir, db_path=db_path)
    uvicorn.run(app_instance, host=host, port=port)


@worker_app.command("run")
def worker_run(
    config: Path = WORKER_CONFIG_OPTION,
    once: bool = typer.Option(
        False,
        "--once",
        help="Register, replay completed spool, heartbeat, poll once, then exit.",
    ),
    max_iterations: int | None = typer.Option(
        None,
        "--max-iterations",
        help="Stop after this many poll-loop iterations.",
    ),
) -> None:
    """Run a foreground worker against the control-plane API."""
    worker_config = load_worker_config(config)
    result = run_worker_from_config(
        worker_config,
        once=once,
        max_iterations=max_iterations,
    )
    if result is not None:
        typer.echo(result)


@host_app.command("url-check")
def host_url_check(
    url: str = typer.Argument(..., help="Explicit http or https URL to check."),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Submit a VS0 url_check WorkUnit and create its first assignment."""
    try:
        result = _host_adapter(config_dir, db_path).submit_work_unit(
            task_type="url_check",
            input_payload={"url": url},
        )
    except HostAdapterInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, sort_keys=True))


@host_app.command("dedup")
def host_dedup(
    items_json: str = typer.Argument(..., help="JSON array of items to deduplicate."),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Submit a VS1a dedup WorkUnit and create its first assignment."""
    try:
        items = json.loads(items_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("items_json must be a JSON array") from exc
    if not isinstance(items, list):
        raise typer.BadParameter("items_json must be a JSON array")

    try:
        result = _host_adapter(config_dir, db_path).submit_work_unit(
            task_type="dedup",
            input_payload={"items": items},
        )
    except HostAdapterInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, sort_keys=True))


@host_app.command("webpage-extract")
def host_webpage_extract(
    url: str = typer.Argument(..., help="Explicit http or https webpage URL."),
    html: str | None = typer.Option(
        None,
        "--html",
        help="Optional explicit static HTML fixture to extract without fetching.",
    ),
    text: str | None = typer.Option(
        None,
        "--text",
        help="Optional explicit page text fixture to extract without fetching.",
    ),
    title: str | None = typer.Option(
        None,
        "--title",
        help="Optional explicit page title fixture.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Submit a VS1b webpage_extraction WorkUnit."""
    input_payload: dict[str, object] = {"url": url}
    if html is not None:
        input_payload["html"] = html
    if text is not None:
        input_payload["text"] = text
    if title is not None:
        input_payload["title"] = title
    try:
        result = _host_adapter(config_dir, db_path).submit_work_unit(
            task_type="webpage_extraction",
            input_payload=input_payload,
        )
    except HostAdapterInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, sort_keys=True))


@host_app.command("topic-classify")
def host_topic_classify(
    text: str = typer.Argument(..., help="Text to classify into an allowed topic."),
    allowed_labels_json: str | None = typer.Option(
        None,
        "--allowed-labels-json",
        help="Optional JSON array of allowed topic labels.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Submit a VS1c topic_classification WorkUnit."""
    allowed_labels = _parse_allowed_labels(allowed_labels_json)
    input_payload: dict[str, object] = {"text": text}
    if allowed_labels is not None:
        input_payload["allowed_labels"] = allowed_labels
    try:
        result = _host_adapter(config_dir, db_path).submit_work_unit(
            task_type="topic_classification",
            input_payload=input_payload,
        )
    except HostAdapterInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, sort_keys=True))


@host_app.command("claim-extract")
def host_claim_extract(
    text: str = typer.Argument(..., help="Text containing a factual claim."),
    source_id: str = typer.Option(
        "src_claim_1",
        "--source-id",
        help="Fixture source id referenced by emitted source_post_refs.",
    ),
    entity: str | None = typer.Option(
        None,
        "--entity",
        help="Optional entity override for the deterministic claim stub.",
    ),
    allowed_claim_types_json: str | None = typer.Option(
        None,
        "--allowed-claim-types-json",
        help="Optional JSON array of allowed claim_type values.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Submit a VS1d claim_extraction WorkUnit."""
    allowed_claim_types = _parse_string_list(
        allowed_claim_types_json,
        parameter_name="allowed_claim_types_json",
    )
    input_payload: dict[str, object] = {"text": text, "source_id": source_id}
    if entity is not None:
        input_payload["entity"] = entity
    if allowed_claim_types is not None:
        input_payload["allowed_claim_types"] = allowed_claim_types
    try:
        result = _host_adapter(config_dir, db_path).submit_work_unit(
            task_type="claim_extraction",
            input_payload=input_payload,
        )
    except HostAdapterInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(result, sort_keys=True))


@workunit_app.command("submit")
def workunit_submit(
    task_type: str = typer.Option(..., "--task-type", help="Supported task type."),
    input_path: Path = WORKUNIT_INPUT_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Accepted for MCP/CLI parity; P0 does not execute directly.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Submit a schema-bound Work Unit through HostAdapterCore."""
    try:
        result = _host_adapter(config_dir, db_path).submit_from_file(
            task_type=task_type,
            input_path=input_path,
            wait=wait,
        )
    except (HostAdapterInputError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@workunit_app.command("status")
def workunit_status(
    work_unit_id: str = typer.Argument(..., help="Work Unit id."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Fetch Work Unit status through HostAdapterCore."""
    result = _host_adapter(config_dir, db_path).get_work_unit_status(
        work_unit_id=work_unit_id
    )
    _emit_payload(result, json_output=json_output)


@workunit_app.command("result")
def workunit_result(
    work_unit_id: str = typer.Argument(..., help="Work Unit id."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Fetch HostResultSummary through HostAdapterCore."""
    result = _host_adapter(config_dir, db_path).get_work_unit_result(
        work_unit_id=work_unit_id
    )
    _emit_payload(result, json_output=json_output)


@route_app.command("explain")
def route_explain(
    task_type: str = typer.Option(..., "--task-type", help="Supported task type."),
    input_path: Path = WORKUNIT_INPUT_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
    routebook_v1_dir: Path = ROUTEBOOK_V1_DIR_OPTION,
) -> None:
    """Explain a Routebook V1 route without scheduling work."""
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        result = _host_adapter(config_dir, db_path).explain_route(
            task_type=task_type,
            input_payload=payload,
            routebook_v1_dir=routebook_v1_dir,
        )
    except (HostAdapterInputError, json.JSONDecodeError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@route_app.command("analyze")
def route_analyze(
    task_type: str = typer.Option(..., "--task-type", help="Supported task type."),
    input_path: Path = WORKUNIT_INPUT_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
    routebook_v1_dir: Path = ROUTEBOOK_V1_DIR_OPTION,
) -> None:
    """Analyze a task without scheduling work or calling a model."""
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        result = _host_adapter(config_dir, db_path).analyze_route(
            task_type=task_type,
            input_payload=payload,
            routebook_v1_dir=routebook_v1_dir,
        )
    except (HostAdapterInputError, json.JSONDecodeError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@route_app.command("score")
def route_score(
    task_type: str = typer.Option(..., "--task-type", help="Supported task type."),
    input_path: Path = WORKUNIT_INPUT_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
    routebook_v1_dir: Path = ROUTEBOOK_V1_DIR_OPTION,
) -> None:
    """Score RoutePlan candidates without scheduling work or calling a model."""
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        result = _host_adapter(config_dir, db_path).score_route(
            task_type=task_type,
            input_payload=payload,
            routebook_v1_dir=routebook_v1_dir,
        )
    except (HostAdapterInputError, json.JSONDecodeError, FileNotFoundError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@capacity_app.command("list")
def capacity_list(
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """List host-safe capacity node projections."""
    loaded_config = load_config_dir(config_dir)
    conn = initialize_database(db_path)
    try:
        rebuild_capacity_projection_from_config_and_db(conn, loaded_config)
        nodes = discover_capacity_nodes(conn)
    finally:
        conn.close()
    _emit_payload({"status": "ok", "nodes": nodes}, json_output=json_output)


@report_app.command("summary")
def report_summary(
    run_id: str = typer.Option(..., "--run-id", help="Run id to summarize."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    baseline_mode: str = typer.Option(
        "none",
        "--baseline-mode",
        help="Baseline mode: measured, estimated, or none.",
    ),
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Generate a run-level CostQualityReport from persisted objects."""
    conn = initialize_database(db_path)
    try:
        report = generate_cost_quality_report(
            conn,
            run_id=run_id,
            baseline_mode=baseline_mode,
        )
    finally:
        conn.close()
    _emit_report(report, json_output=json_output)


@report_app.command("capacity")
def report_capacity(
    run_id: str = typer.Option(..., "--run-id", help="Run id to summarize."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Generate capacity-node performance summaries for a run."""
    conn = initialize_database(db_path)
    try:
        report = generate_capacity_report(conn, run_id=run_id)
    finally:
        conn.close()
    _emit_report(report, json_output=json_output)


@accounts_app.command("list")
def accounts_list(
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="Optional provider filter.",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        help="Optional account snapshot status filter.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """List local account snapshots without exposing raw credentials."""
    result = _host_adapter(config_dir, db_path).list_account_snapshots(
        provider=provider,
        status=status,
    )
    _emit_payload(result, json_output=json_output)


@accounts_app.command("snapshot")
def accounts_snapshot(
    provider: str = typer.Option(..., "--provider", help="Provider id."),
    account_label: str = typer.Option(
        ...,
        "--account-label",
        help="Local account label.",
    ),
    secret_ref: str | None = typer.Option(
        None,
        "--secret-ref",
        help="Local secret reference such as keychain:, env:, vault:, manual:, none:.",
    ),
    status: str = typer.Option(
        "configured",
        "--status",
        help="Snapshot status: configured, unconfigured, error, unknown.",
    ),
    balance_source: str = typer.Option(
        "manual",
        "--balance-source",
        help="provider_api, tokenbank_ledger, or manual.",
    ),
    available_micros: int | None = typer.Option(
        None,
        "--available-micros",
        help="Optional available balance in integer micros.",
    ),
    monthly_spend_micros: int | None = typer.Option(
        None,
        "--monthly-spend-micros",
        help="Optional monthly spend in integer micros.",
    ),
    monthly_budget_micros: int | None = typer.Option(
        None,
        "--monthly-budget-micros",
        help="Optional monthly budget in integer micros.",
    ),
    requests_per_minute: int | None = typer.Option(
        None,
        "--requests-per-minute",
        help="Optional local rate-limit hint.",
    ),
    tokens_per_minute: int | None = typer.Option(
        None,
        "--tokens-per-minute",
        help="Optional local token rate-limit hint.",
    ),
    visible_models: str | None = typer.Option(
        None,
        "--visible-models",
        help="Comma-separated model ids visible to this local account.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Create or update a local account snapshot using refs only."""
    try:
        result = _host_adapter(config_dir, db_path).upsert_manual_account_snapshot(
            provider=provider,
            account_label=account_label,
            secret_ref=secret_ref,
            status=status,
            balance_source=balance_source,
            available_micros=available_micros,
            monthly_spend_micros=monthly_spend_micros,
            monthly_budget_micros=monthly_budget_micros,
            requests_per_minute=requests_per_minute,
            tokens_per_minute=tokens_per_minute,
            visible_models=_parse_csv_list(visible_models),
        )
    except ValueError as exc:
        raise typer.BadParameter(
            "invalid account snapshot: raw credential-like values are not allowed"
        ) from exc
    _emit_payload(result, json_output=json_output)


@accounts_app.command("refresh")
def accounts_refresh(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Refresh the local account view without provider API calls."""
    result = _host_adapter(config_dir, db_path).refresh_account_snapshots()
    _emit_payload(result, json_output=json_output)


@usage_app.command("record")
def usage_record(
    work_unit_id: str = typer.Option(..., "--work-unit-id", help="Work Unit id."),
    account_snapshot_id: str | None = typer.Option(
        None,
        "--account-snapshot-id",
        help="Optional local account snapshot id.",
    ),
    routebook_v1_dir: Path = ROUTEBOOK_V1_DIR_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Record a usage ledger entry for a completed WorkUnit."""
    try:
        result = _host_adapter(config_dir, db_path).record_usage_ledger_entry(
            work_unit_id=work_unit_id,
            account_snapshot_id=account_snapshot_id,
            routebook_v1_dir=routebook_v1_dir,
        )
    except (KeyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@usage_app.command("ledger")
def usage_ledger(
    work_unit_id: str | None = typer.Option(
        None,
        "--work-unit-id",
        help="Optional Work Unit id filter.",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Optional run id filter.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """List redacted usage ledger entries."""
    result = _host_adapter(config_dir, db_path).list_usage_ledger_entries(
        work_unit_id=work_unit_id,
        run_id=run_id,
    )
    _emit_payload(result, json_output=json_output)


@audit_app.command("receipt")
def audit_receipt(
    work_unit_id: str = typer.Option(..., "--work-unit-id", help="Work Unit id."),
    usage_ledger_entry_id: str | None = typer.Option(
        None,
        "--usage-ledger-entry-id",
        help="Optional existing usage ledger entry id.",
    ),
    account_snapshot_id: str | None = typer.Option(
        None,
        "--account-snapshot-id",
        help="Optional local account snapshot id used if usage must be recorded.",
    ),
    routebook_v1_dir: Path = ROUTEBOOK_V1_DIR_OPTION,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Create or return a redacted audit receipt for an accepted result."""
    try:
        result = _host_adapter(config_dir, db_path).create_audit_receipt(
            work_unit_id=work_unit_id,
            usage_ledger_entry_id=usage_ledger_entry_id,
            account_snapshot_id=account_snapshot_id,
            routebook_v1_dir=routebook_v1_dir,
        )
    except (KeyError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@audit_app.command("list")
def audit_list(
    work_unit_id: str | None = typer.Option(
        None,
        "--work-unit-id",
        help="Optional Work Unit id filter.",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Optional run id filter.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """List redacted audit receipts."""
    result = _host_adapter(config_dir, db_path).list_audit_receipts(
        work_unit_id=work_unit_id,
        run_id=run_id,
    )
    _emit_payload(result, json_output=json_output)


@demo_capacity_app.command("run")
def demo_capacity_run(
    task: str | None = typer.Option(
        None,
        "--task",
        help="Run one demo task type.",
    ),
    all_tasks: bool = typer.Option(
        False,
        "--all",
        help="Run all five demo task types.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
    demo_dir: Path = DEMO_DIR_OPTION,
) -> None:
    """Run the Private Capacity Network demo through HostAdapterCore."""
    try:
        result = PrivateCapacityDemoRunner(
            config_dir=config_dir,
            db_path=db_path,
            demo_dir=demo_dir,
        ).run(task=task, all_tasks=all_tasks)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _emit_payload(result, json_output=json_output)


@mcp_app.command("serve")
def mcp_serve(
    config_dir: Path = CONFIG_DIR_OPTION,
    db_path: Path = DB_PATH_OPTION,
) -> None:
    """Serve the bounded WP12 MCP stdio stub."""
    MCPStdioServer(core=_host_adapter(config_dir, db_path)).serve()


demo_app.add_typer(demo_capacity_app, name="capacity")

app.add_typer(schemas_app, name="schemas")
app.add_typer(config_app, name="config")
app.add_typer(daemon_app, name="daemon")
app.add_typer(worker_app, name="worker")
app.add_typer(host_app, name="host")
app.add_typer(workunit_app, name="workunit")
app.add_typer(route_app, name="route")
app.add_typer(capacity_app, name="capacity")
app.add_typer(report_app, name="report")
app.add_typer(accounts_app, name="accounts")
app.add_typer(usage_app, name="usage")
app.add_typer(audit_app, name="audit")
app.add_typer(mcp_app, name="mcp")
app.add_typer(demo_app, name="demo")


def main() -> None:
    """Console script entry point."""
    app()


__all__ = ["app", "main"]


def _parse_allowed_labels(value: str | None) -> list[str] | None:
    return _parse_string_list(value, parameter_name="allowed_labels_json")


def _parse_string_list(
    value: str | None,
    *,
    parameter_name: str,
) -> list[str] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(
            f"{parameter_name} must be a JSON string array"
        ) from exc
    if not isinstance(parsed, list) or not all(
        isinstance(item, str) and item for item in parsed
    ):
        raise typer.BadParameter(
            f"{parameter_name} must be a JSON string array"
        )
    return parsed


def _parse_csv_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _emit_report(report: dict, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(report, sort_keys=True))
        return
    typer.echo(
        f"{report['report_type']} run_id={report['run_id']} "
        f"generated_at={report['generated_at']}"
    )


def _host_adapter(config_dir: Path, db_path: Path) -> HostAdapterCore:
    return HostAdapterCore(config_dir=config_dir, db_path=db_path)


def _emit_payload(payload: dict, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
        return
    typer.echo(json.dumps(payload, sort_keys=True))
