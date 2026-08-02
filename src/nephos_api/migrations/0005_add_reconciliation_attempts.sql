-- ADR 20260518 called for simple capped retry and allowed it to be deferred.
-- It was deferred and then forgotten, which made `blocked` terminal in
-- practice: the claim query selected only `pending`, so a request that blocked
-- once was never re-run and fixing the underlying cause changed nothing.
ALTER TABLE reconciliation_requests ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
