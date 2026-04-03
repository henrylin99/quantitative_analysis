CREATE TABLE IF NOT EXISTS data_job_run (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    job_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    progress DOUBLE NOT NULL DEFAULT 0,
    params_json JSON NOT NULL,
    result_json JSON NULL,
    error_message TEXT NULL,
    log_text LONGTEXT NULL,
    queued_at DATETIME NOT NULL,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    KEY idx_data_job_run_job_type (job_type),
    KEY idx_data_job_run_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS data_job_cursor (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    job_type VARCHAR(64) NOT NULL,
    cursor_key VARCHAR(128) NOT NULL,
    cursor_value VARCHAR(255) NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_data_job_cursor_job_key (job_type, cursor_key),
    KEY idx_data_job_cursor_job_type (job_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
