CREATE TABLE IF NOT EXISTS orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_no VARCHAR(64) NOT NULL UNIQUE,
  query_code_hash VARCHAR(128) NOT NULL,
  query_token_hash VARCHAR(128) NOT NULL UNIQUE,
  contact VARCHAR(255) NOT NULL,
  requirement TEXT NOT NULL,
  remark TEXT NULL,
  product_name VARCHAR(120) NOT NULL,
  amount_cents INT NOT NULL,
  currency VARCHAR(16) NOT NULL DEFAULT 'CNY',
  original_filename VARCHAR(255) NULL,
  stored_filename VARCHAR(255) NULL,
  content_type VARCHAR(120) NULL,
  file_size INT NULL,
  pay_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  delivery_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  delivery_result TEXT NULL,
  email_sent_at DATETIME NULL,
  email_error TEXT NULL,
  daxpay_order_no VARCHAR(128) NULL,
  pay_body TEXT NULL,
  pay_channel VARCHAR(64) NULL,
  payment_error TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  paid_at DATETIME NULL,
  INDEX ix_orders_order_no (order_no),
  INDEX ix_orders_pay_delivery_status (pay_status, delivery_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS payment_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  raw_payload TEXT NOT NULL,
  signature_valid INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX ix_payment_events_order_id (order_id),
  CONSTRAINT fk_payment_events_order_id
    FOREIGN KEY (order_id) REFERENCES orders(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS products (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  description TEXT NULL,
  amount_cents INT NOT NULL,
  currency VARCHAR(16) NOT NULL DEFAULT 'CNY',
  active INT NOT NULL DEFAULT 1,
  sort_order INT NOT NULL DEFAULT 100,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_products_active_sort (active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_settings (
  `key` VARCHAR(80) NOT NULL PRIMARY KEY,
  `value` TEXT NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inventory_items (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  order_id INT NULL,
  account VARCHAR(255) NOT NULL,
  password VARCHAR(255) NOT NULL,
  note TEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'available',
  reserved_at DATETIME NULL,
  sold_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_inventory_product_status (product_id, status),
  INDEX ix_inventory_items_product_id (product_id),
  INDEX ix_inventory_items_order_id (order_id),
  CONSTRAINT fk_inventory_items_product_id
    FOREIGN KEY (product_id) REFERENCES products(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_inventory_items_order_id
    FOREIGN KEY (order_id) REFERENCES orders(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
