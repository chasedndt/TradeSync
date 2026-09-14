-- UP
ALTER TABLE mobile_alert_devices ADD COLUMN notification_preferences jsonb NOT NULL DEFAULT '{}';
ALTER TABLE mobile_alert_devices ADD COLUMN paper_events_enabled_at timestamptz;
-- DOWN
ALTER TABLE mobile_alert_devices DROP COLUMN paper_events_enabled_at;
ALTER TABLE mobile_alert_devices DROP COLUMN notification_preferences;
