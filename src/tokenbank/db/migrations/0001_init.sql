CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_units (
  work_unit_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  task_type TEXT NOT NULL,
  task_level TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_id TEXT PRIMARY KEY,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS route_plans (
  route_plan_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id)
);

CREATE TABLE IF NOT EXISTS route_plan_validations (
  validation_id TEXT PRIMARY KEY,
  route_plan_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (route_plan_id) REFERENCES route_plans(route_plan_id)
);

CREATE TABLE IF NOT EXISTS policy_decisions (
  policy_decision_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  route_plan_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (route_plan_id) REFERENCES route_plans(route_plan_id)
);

CREATE TABLE IF NOT EXISTS execution_attempts (
  attempt_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  route_plan_id TEXT NOT NULL,
  policy_decision_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (route_plan_id) REFERENCES route_plans(route_plan_id),
  FOREIGN KEY (policy_decision_id) REFERENCES policy_decisions(policy_decision_id)
);

CREATE TABLE IF NOT EXISTS assignments (
  assignment_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL,
  work_unit_id TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id),
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id)
);

CREATE TABLE IF NOT EXISTS worker_manifests (
  worker_id TEXT PRIMARY KEY,
  manifest_hash TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_health_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  worker_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  FOREIGN KEY (worker_id) REFERENCES worker_manifests(worker_id)
);

CREATE TABLE IF NOT EXISTS backend_registry (
  backend_id TEXT PRIMARY KEY,
  backend_class TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backend_manifests (
  backend_id TEXT PRIMARY KEY,
  backend_class TEXT NOT NULL,
  capacity_node_id TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backend_health_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  backend_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  FOREIGN KEY (backend_id) REFERENCES backend_manifests(backend_id)
);

CREATE TABLE IF NOT EXISTS backend_usage_records (
  usage_record_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  backend_id TEXT NOT NULL,
  actual_cost_micros INTEGER NOT NULL DEFAULT 0,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (backend_id) REFERENCES backend_manifests(backend_id)
);

CREATE TABLE IF NOT EXISTS backend_execution_logs (
  log_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL,
  backend_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS result_envelopes (
  result_envelope_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  status TEXT NOT NULL,
  output_hash TEXT NOT NULL,
  result_hash TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id)
);

CREATE TABLE IF NOT EXISTS verifier_reports (
  verifier_report_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  result_envelope_id TEXT NOT NULL,
  status TEXT NOT NULL,
  recommendation TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (result_envelope_id) REFERENCES result_envelopes(result_envelope_id)
);

CREATE TABLE IF NOT EXISTS verifier_check_results (
  check_result_id TEXT PRIMARY KEY,
  verifier_report_id TEXT NOT NULL,
  status TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (verifier_report_id) REFERENCES verifier_reports(verifier_report_id)
);

CREATE TABLE IF NOT EXISTS cost_quality_reports (
  cost_quality_report_id TEXT PRIMARY KEY,
  run_id TEXT,
  work_unit_id TEXT,
  actual_cost_micros INTEGER NOT NULL DEFAULT 0,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baseline_run_records (
  baseline_run_record_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS host_requests (
  host_request_id TEXT PRIMARY KEY,
  run_id TEXT,
  work_unit_id TEXT,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS host_result_summaries (
  host_result_summary_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id)
);

CREATE TABLE IF NOT EXISTS worker_tokens (
  token_id TEXT PRIMARY KEY,
  worker_id TEXT NOT NULL,
  token_prefix TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  rotated_at TEXT
);

CREATE TABLE IF NOT EXISTS host_tokens (
  token_id TEXT PRIMARY KEY,
  host_id TEXT NOT NULL,
  token_prefix TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  rotated_at TEXT
);

