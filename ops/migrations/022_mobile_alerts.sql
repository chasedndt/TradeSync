-- UP
CREATE TABLE IF NOT EXISTS mobile_alert_devices (
 id uuid PRIMARY KEY,
 label text NOT NULL,
 platform text NOT NULL CHECK (platform IN ('android','ios')),
 topic text NOT NULL UNIQUE,
 enabled boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 operator_confirmed_at timestamptz
);
CREATE TABLE IF NOT EXISTS mobile_alert_outbox (
 id uuid PRIMARY KEY,
 device_id uuid NOT NULL REFERENCES mobile_alert_devices(id),
 dedupe_key text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('test','attention')),
 status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sending','retry','provider_accepted','operator_confirmed','failed','expired')),
 attempts integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz,
 provider_id text,
 last_error text,
 accepted_at timestamptz,
 confirmed_at timestamptz,
 UNIQUE (device_id,dedupe_key)
);
CREATE INDEX IF NOT EXISTS mobile_alert_pending ON mobile_alert_outbox(status,next_attempt_at);
-- DOWN
DROP TABLE IF EXISTS mobile_alert_outbox;
DROP TABLE IF EXISTS mobile_alert_devices;
