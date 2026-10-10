import { Pool } from 'pg';
import { env } from './env';

/**
 * Read-only database probe used to verify persisted state behind the API.
 * Only SELECT statements are issued, and every session is forced read-only, so the suite cannot
 * corrupt data even if a query is written incorrectly.
 */
let pool: Pool | undefined;

function getPool(): Pool {
  pool ??= new Pool({
    connectionString: env.databaseUrl,
    max: 2,
    options: '-c default_transaction_read_only=on',
  });
  return pool;
}

export interface OrderRow {
  id: string;
  status: string;
  total: string;
  customer_ref: string;
  idempotency_key: string | null;
}

export interface OrderItemRow {
  product_id: number;
  sku: string;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export const db = {
  async productInventory(productId: number): Promise<number | undefined> {
    const result = await getPool().query<{ inventory: number }>('SELECT inventory FROM products WHERE id = $1', [
      productId,
    ]);
    return result.rows[0]?.inventory;
  },

  async order(orderId: string): Promise<OrderRow | undefined> {
    const result = await getPool().query<OrderRow>(
      'SELECT id::text, status, total::text, customer_ref, idempotency_key FROM orders WHERE id = $1',
      [orderId],
    );
    return result.rows[0];
  },

  async orderItems(orderId: string): Promise<OrderItemRow[]> {
    const result = await getPool().query<OrderItemRow>(
      `SELECT product_id, sku, quantity, unit_price::text, line_total::text
         FROM order_items WHERE order_id = $1 ORDER BY id`,
      [orderId],
    );
    return result.rows;
  },

  async orderCountForProduct(productId: number): Promise<number> {
    const result = await getPool().query<{ count: string }>(
      'SELECT count(DISTINCT order_id) AS count FROM order_items WHERE product_id = $1',
      [productId],
    );
    return Number(result.rows[0]?.count ?? 0);
  },

  async ordersForCustomer(customerRef: string): Promise<number> {
    const result = await getPool().query<{ count: string }>(
      'SELECT count(*) AS count FROM orders WHERE customer_ref = $1',
      [customerRef],
    );
    return Number(result.rows[0]?.count ?? 0);
  },

  async close(): Promise<void> {
    await pool?.end();
    pool = undefined;
  },
};
