CREATE TABLE IF NOT EXISTS event_outbox (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  type TEXT NOT NULL,
  subject TEXT NOT NULL,
  run_id TEXT NULL,
  work_unit_id TEXT NULL,
  attempt_id TEXT NULL,
  assignment_id TEXT NULL,
  trace_id TEXT NOT NULL,
  span_id TEXT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','written','failed')),
  sequence INTEGER NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  written_at TEXT NULL,
  failure_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_event_outbox_sequence
  ON event_outbox(sequence);

CREATE INDEX IF NOT EXISTS idx_event_outbox_pending
  ON event_outbox(status, sequence);

CREATE INDEX IF NOT EXISTS idx_event_outbox_work_unit
  ON event_outbox(work_unit_id);

