CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  order_no TEXT NOT NULL UNIQUE,
  product_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending_payment','paid','shipped','delivered','refunding','refunded','cancelled')),
  amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_orders_user ON orders(user_id);

CREATE TABLE conversations (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  status TEXT NOT NULL CHECK(status IN ('active','waiting_order','handed_off','closed')),
  selected_order_id INTEGER REFERENCES orders(id),
  ticket_id INTEGER REFERENCES tickets(id),
  version INTEGER NOT NULL DEFAULT 1,
  prediction_source TEXT,
  prediction_model_version TEXT,
  prediction_label TEXT,
  prediction_mapping_version TEXT,
  prediction_integrity TEXT,
  prediction_score REAL NOT NULL DEFAULT 0,
  needs_manual BOOLEAN NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_conversations_user ON conversations(user_id);

CREATE TABLE conversation_messages (
  id INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_conversation_messages_conversation ON conversation_messages(conversation_id);
