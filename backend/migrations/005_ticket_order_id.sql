ALTER TABLE tickets ADD COLUMN order_id INTEGER REFERENCES orders(id);
CREATE INDEX ix_tickets_order ON tickets(order_id);
