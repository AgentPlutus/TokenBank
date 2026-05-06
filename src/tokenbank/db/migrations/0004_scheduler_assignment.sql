ALTER TABLE execution_attempts
  ADD COLUMN attempt_number INTEGER NOT NULL DEFAULT 1;

ALTER TABLE execution_attempts
  ADD COLUMN started_at TEXT NULL;

ALTER TABLE execution_attempts
  ADD COLUMN completed_at TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN capacity_node_id TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN backend_id TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN lease_token_hash TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN lease_token_prefix TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN lease_version INTEGER NOT NULL DEFAULT 0;

ALTER TABLE assignments
  ADD COLUMN effective_constraints_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE assignments
  ADD COLUMN assigned_at TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN lease_expires_at TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN accepted_at TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN completed_at TEXT NULL;

ALTER TABLE assignments
  ADD COLUMN updated_at TEXT NULL;

CREATE TABLE IF NOT EXISTS result_quarantine (
  quarantine_id TEXT PRIMARY KEY,
  result_envelope_id TEXT NULL,
  work_unit_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  assignment_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (work_unit_id) REFERENCES work_units(work_unit_id),
  FOREIGN KEY (attempt_id) REFERENCES execution_attempts(attempt_id),
  FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_attempts_work_unit_attempt
  ON execution_attempts(work_unit_id, attempt_number);

CREATE INDEX IF NOT EXISTS idx_assignments_worker_status
  ON assignments(worker_id, status, assigned_at);

CREATE INDEX IF NOT EXISTS idx_assignments_attempt
  ON assignments(attempt_id);

