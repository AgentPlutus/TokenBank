CREATE TABLE IF NOT EXISTS account_snapshots (
  account_snapshot_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  account_label TEXT NOT NULL,
  status TEXT NOT NULL,
  secret_ref TEXT NULL,
  snapshot_hash TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_account_snapshots_provider_label
  ON account_snapshots(provider, account_label);

CREATE TABLE IF NOT EXISTS usage_ledger_entries (
  usage_ledger_entry_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  route_plan_id TEXT NOT NULL,
  result_envelope_id TEXT NOT NULL,
  verifier_report_id TEXT NULL,
  account_snapshot_id TEXT NULL,
  usage_source TEXT NOT NULL,
  cost_source TEXT NOT NULL,
  billable_cost_micros INTEGER NOT NULL DEFAULT 0,
  entry_hash TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (route_plan_id) REFERENCES route_plans(route_plan_id),
  FOREIGN KEY (result_envelope_id) REFERENCES result_envelopes(result_envelope_id),
  FOREIGN KEY (verifier_report_id) REFERENCES verifier_reports(verifier_report_id),
  FOREIGN KEY (account_snapshot_id) REFERENCES account_snapshots(account_snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_entries_work_unit
  ON usage_ledger_entries(work_unit_id, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_entries_route_plan
  ON usage_ledger_entries(route_plan_id);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_entries_source
  ON usage_ledger_entries(usage_source, cost_source);

CREATE TABLE IF NOT EXISTS audit_receipts (
  audit_receipt_id TEXT PRIMARY KEY,
  work_unit_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  route_plan_id TEXT NOT NULL,
  result_envelope_id TEXT NOT NULL,
  verifier_report_id TEXT NOT NULL,
  usage_ledger_entry_id TEXT NULL,
  receipt_hash TEXT NOT NULL,
  previous_receipt_hash TEXT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (route_plan_id) REFERENCES route_plans(route_plan_id),
  FOREIGN KEY (result_envelope_id) REFERENCES result_envelopes(result_envelope_id),
  FOREIGN KEY (verifier_report_id) REFERENCES verifier_reports(verifier_report_id),
  FOREIGN KEY (usage_ledger_entry_id) REFERENCES usage_ledger_entries(usage_ledger_entry_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_receipts_receipt_hash
  ON audit_receipts(receipt_hash);

CREATE INDEX IF NOT EXISTS idx_audit_receipts_work_unit
  ON audit_receipts(work_unit_id, created_at);
