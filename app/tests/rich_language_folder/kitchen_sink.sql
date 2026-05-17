-- ==============================================================================
-- Heavyweight SQL / PL-pgSQL AST Stress Test File.
-- Target: Tree-sitter SQL Grammar Validation.
-- Covers: Recursive CTEs, Window Functions, DDL, Upserts, and Procedural Blocks.
-- ==============================================================================

BEGIN;

-- 1. Complex DDL: Tables with Constraints, Auto-increments, and Data Types
DROP TABLE IF EXISTS analytics_pipeline_metrics CASCADE;
DROP TABLE IF EXISTS system_nodes CASCADE;

CREATE TABLE system_nodes (
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_name VARCHAR(128) NOT NULL UNIQUE,
    cluster_tier VARCHAR(32) CHECK (cluster_tier IN ('omega-north', 'omega-south', 'edge')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analytics_pipeline_metrics (
    metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id UUID REFERENCES system_nodes(node_id) ON DELETE CASCADE,
    batch_sequence INT NOT NULL,
    payload_data JSONB,
    processing_latency_ms NUMERIC(10, 2) NOT NULL,
    status_flag VARCHAR(16) DEFAULT 'IDLE',
    recorded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
);

-- 2. DML with Complex Subqueries, JSONB Manipulation, and Upsert (ON CONFLICT)
INSERT INTO system_nodes (node_name, cluster_tier)
VALUES ('edge-node-01', 'edge'), ('core-node-alpha', 'omega-north')
ON CONFLICT (node_name) 
DO UPDATE SET is_active = EXCLUDED.is_active;

-- 3. Advanced Window Functions & Conditional Aggregation
SELECT 
    node_id,
    batch_sequence,
    processing_latency_ms,
    -- Window partitions with explicit ordering frames
    AVG(processing_latency_ms) OVER(
        PARTITION BY node_id 
        ORDER BY batch_sequence 
        ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ) AS rolling_avg_latency,
    DENSE_RANK() OVER(
        PARTITION BY cluster_tier 
        ORDER BY processing_latency_ms DESC
    ) as latency_rank_in_tier,
    -- Conditional aggregation via CASE expressions
    COUNT(*) FILTER (WHERE status_flag = 'FAILED') as total_failures,
    SUM(CASE WHEN status_flag = 'COMPLETED' THEN 1 ELSE 0 END) AS total_successes
FROM analytics_pipeline_metrics m
JOIN system_nodes n USING (node_id)
WHERE n.is_active = TRUE;

-- 4. Complex Common Table Expressions (CTEs): Recursive Logic
-- Mocking a recursive node dependency tree parsing simulation
WITH RECURSIVE node_hierarchy AS (
    -- Anchor member
    SELECT node_id, node_name, CAST(NULL AS UUID) as parent_node_id, 1 AS depth
    FROM system_nodes
    WHERE cluster_tier = 'omega-north'
    
    UNION ALL
    
    -- Recursive member
    SELECT child.node_id, child.node_name, parent.node_id, parent.depth + 1
    FROM system_nodes child
    INNER JOIN node_hierarchy parent ON child.node_id = parent.node_id -- Simulated join predicate
    WHERE parent.depth < 5
)
SELECT * FROM node_hierarchy;

-- 5. Data Control Language (DCL) & Indexing Statements
CREATE INDEX idx_metrics_node_latency ON analytics_pipeline_metrics (node_id, processing_latency_ms DESC);
CREATE INDEX idx_metrics_payload_gin ON analytics_pipeline_metrics USING gin (payload_data);

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO indexer_service_role;

-- 6. Procedural Block Context: PL/pgSQL Function with Control Flow and Exception Handling
CREATE OR REPLACE FUNCTION process_execution_batch(
    target_node_id UUID, 
    max_threshold NUMERIC
) 
RETURNS VARCHAR AS $$
DECLARE
    avg_latency NUMERIC;
    result_status VARCHAR(64);
BEGIN
    -- Validating variable population via scalar queries
    SELECT AVG(processing_latency_ms) INTO avg_latency
    FROM analytics_pipeline_metrics
    WHERE node_id = target_node_id;

    -- Conditional branching control layout
    IF avg_latency IS NULL THEN
        result_status := 'NO_METRICS_FOUND';
    ELSIF avg_latency > max_threshold THEN
        result_status := 'THRESHOLD_EXCEEDED_HALT_PIPELINE';
        
        -- Update statement within control structure
        UPDATE analytics_pipeline_metrics 
        SET status_flag = 'FAILED' 
        WHERE node_id = target_node_id AND status_flag = 'PROCESSING';
    ELSE
        result_status := 'PERFORMANCE_BOUNDS_VALID';
    END IF;

    RETURN result_status;

-- Exception safety scope validation target
EXCEPTION
    WHEN division_by_zero THEN
        RAISE NOTICE 'Caught arithmetic operational error anomaly.';
        RETURN 'ERROR_ARITHMETIC';
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Fatal AST parsing state collapse inside procedural execution framework.';
END;
$$ LANGUAGE plpgsql;

COMMIT;