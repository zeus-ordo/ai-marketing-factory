CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS llm_usage (
    usage_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id       UUID NOT NULL,
    model            VARCHAR(100) NOT NULL,
    provider         VARCHAR(50) NOT NULL,
    prompt_tokens    BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    request_count    INTEGER NOT NULL DEFAULT 1,
    raw_response_id  VARCHAR(255),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_company_created
    ON llm_usage (company_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_model_created
    ON llm_usage (model, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_company_model
    ON llm_usage (company_id, model, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_model_pricing (
    pricing_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model                   VARCHAR(100) UNIQUE NOT NULL,
    provider                VARCHAR(50) NOT NULL,
    prompt_price_per_m      DECIMAL(10,4) NOT NULL DEFAULT 0,
    completion_price_per_m  DECIMAL(10,4) NOT NULL DEFAULT 0,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO llm_model_pricing (model, provider, prompt_price_per_m, completion_price_per_m)
VALUES ('deepseek-v3', 'deepseek', 0.27, 1.10)
ON CONFLICT (model) DO NOTHING;

INSERT INTO llm_model_pricing (model, provider, prompt_price_per_m, completion_price_per_m)
VALUES ('minimax-video-01', 'minimax', 0, 0)
ON CONFLICT (model) DO NOTHING;
