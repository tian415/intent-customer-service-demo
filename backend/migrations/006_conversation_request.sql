ALTER TABLE conversations ADD COLUMN current_request TEXT;
ALTER TABLE conversations ADD COLUMN intent_category_id INTEGER REFERENCES categories(id);
ALTER TABLE conversations ADD COLUMN next_action TEXT CHECK(next_action IN ('ask_order','clarify','answer','handoff'));
