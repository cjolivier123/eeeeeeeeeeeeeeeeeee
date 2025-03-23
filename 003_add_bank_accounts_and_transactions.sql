CREATE TABLE bank_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_number TEXT NOT NULL UNIQUE,
    balance REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    transaction_type TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES bank_accounts(id)
);