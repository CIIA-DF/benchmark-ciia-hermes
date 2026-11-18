-- Migração aditiva para registros experimentais; não altera tabelas existentes.
CREATE TABLE experiment_runs (
    run_id VARCHAR PRIMARY KEY,
    payload JSON NOT NULL
);

CREATE TABLE experiment_run_revisions (
    run_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (run_id, revision),
    FOREIGN KEY (run_id) REFERENCES experiment_runs (run_id)
);
