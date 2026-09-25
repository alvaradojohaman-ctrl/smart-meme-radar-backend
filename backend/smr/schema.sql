CREATE TABLE IF NOT EXISTS schema_versions(version integer PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS cases (
 id uuid PRIMARY KEY, chain text NOT NULL DEFAULT 'solana', address text NOT NULL,
 symbol text NOT NULL, entered_at timestamptz NOT NULL, entry_price double precision NOT NULL CHECK(entry_price > 0),
 market integer NOT NULL, risk integer NOT NULL, group_name text NOT NULL CHECK(group_name IN ('APROBADO','BLOQUEADO')),
 reasons jsonb NOT NULL, snapshot jsonb NOT NULL, pair_address text NOT NULL,
 model text NOT NULL, protocol text NOT NULL, cohort text NOT NULL DEFAULT 'v04e-prospective',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cases_address_time ON cases(chain,address,entered_at DESC);
CREATE TABLE IF NOT EXISTS checkpoints (
 id bigserial PRIMARY KEY, case_id uuid NOT NULL REFERENCES cases(id), horizon text NOT NULL,
 target_at timestamptz NOT NULL, deadline_at timestamptz NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','observed','missed')),
 observed_at timestamptz, delay_seconds double precision, price double precision, pct double precision,
 pair_address text, source text, source_quote_at timestamptz,
 attempts integer NOT NULL DEFAULT 0, last_error text, next_attempt_at timestamptz NOT NULL,
 lease_until timestamptz, lease_token uuid, finalized_at timestamptz,
 UNIQUE(case_id,horizon), CHECK(deadline_at >= target_at),
 CHECK((status='observed' AND observed_at IS NOT NULL AND observed_at>=target_at AND observed_at<=deadline_at
        AND delay_seconds IS NOT NULL AND delay_seconds>=0 AND price>0 AND pct IS NOT NULL)
    OR (status IN ('pending','missed') AND observed_at IS NULL AND delay_seconds IS NULL AND price IS NULL AND pct IS NULL))
);
CREATE INDEX IF NOT EXISTS checkpoints_due ON checkpoints(next_attempt_at) WHERE status='pending';
CREATE TABLE IF NOT EXISTS observations (
 id bigserial PRIMARY KEY, checkpoint_id bigint NOT NULL REFERENCES checkpoints(id),
 requested_at timestamptz NOT NULL, received_at timestamptz NOT NULL, price double precision,
 pair_address text, error text, accepted boolean NOT NULL, source text NOT NULL DEFAULT 'dexscreener',
 source_quote_at timestamptz, payload jsonb
);
CREATE TABLE IF NOT EXISTS historical_imports (
 id text PRIMARY KEY, imported_at timestamptz NOT NULL DEFAULT now(), case_count integer NOT NULL,
 payload jsonb NOT NULL, raw_cases text NOT NULL, cohort text NOT NULL UNIQUE DEFAULT 'v04d-historical'
);
CREATE TABLE IF NOT EXISTS historical_cases (
 id text PRIMARY KEY, batch_id text NOT NULL REFERENCES historical_imports(id), ordinal integer NOT NULL,
 payload jsonb NOT NULL, UNIQUE(batch_id,ordinal)
);
CREATE OR REPLACE FUNCTION reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Historical cohort is immutable'; END $$;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='history_frozen') THEN
 CREATE TRIGGER history_frozen BEFORE UPDATE OR DELETE ON historical_cases FOR EACH ROW EXECUTE FUNCTION reject_history_mutation();
 CREATE TRIGGER imports_frozen BEFORE UPDATE OR DELETE ON historical_imports FOR EACH ROW EXECUTE FUNCTION reject_history_mutation();
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS service_state(key text PRIMARY KEY, updated_at timestamptz NOT NULL DEFAULT now(), value jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS paper_account(id integer PRIMARY KEY CHECK(id=1), capital_gtq numeric NOT NULL DEFAULT 9000 CHECK(capital_gtq>=0), mode text NOT NULL DEFAULT 'virtual' CHECK(mode='virtual'));
INSERT INTO paper_account(id) VALUES(1) ON CONFLICT DO NOTHING;
INSERT INTO schema_versions(version) VALUES(1) ON CONFLICT DO NOTHING;
