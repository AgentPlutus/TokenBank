CREATE TABLE IF NOT EXISTS capacity_nodes (
  capacity_node_id TEXT PRIMARY KEY,
  node_type TEXT NOT NULL,
  status TEXT NOT NULL,
  worker_id TEXT NULL,
  backend_id TEXT NULL,
  backend_class TEXT NULL,
  execution_location TEXT NOT NULL,
  trust_level TEXT NOT NULL,
  allowed_task_types_json TEXT NOT NULL,
  allowed_privacy_levels_json TEXT NOT NULL,
  allowed_data_labels_json TEXT NOT NULL,
  backend_ids_json TEXT NOT NULL,
  manifest_hash TEXT NOT NULL,
  health_summary_json TEXT NOT NULL,
  body_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capacity_node_health_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  capacity_node_id TEXT NOT NULL,
  worker_id TEXT NULL,
  backend_id TEXT NULL,
  status TEXT NOT NULL,
  health_json TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  body_json TEXT NOT NULL,
  FOREIGN KEY (capacity_node_id) REFERENCES capacity_nodes(capacity_node_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_capacity_nodes_status
  ON capacity_nodes(status);

CREATE INDEX IF NOT EXISTS idx_capacity_nodes_backend
  ON capacity_nodes(backend_id);

CREATE INDEX IF NOT EXISTS idx_capacity_node_health_node
  ON capacity_node_health_snapshots(capacity_node_id, captured_at);

