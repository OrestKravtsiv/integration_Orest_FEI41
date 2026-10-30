BEGIN;

ALTER TABLE orders
ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'pending';

UPDATE orders
SET status = CASE
    WHEN predicted_price IS NULL THEN 'failed'
    ELSE 'priced'
END;

COMMIT;
