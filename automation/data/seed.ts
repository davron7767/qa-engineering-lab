/**
 * Mirror of the application's deterministic seed data (app/db/seed.py).
 *
 * Tests look seed products up by SKU, never by numeric id, and NEVER mutate them (no orders,
 * no inventory changes). Anything a test needs to change is created fresh via `testData`.
 */
export const seedProducts = {
  keyboard: { sku: 'QA-KB-001', name: 'Mechanical Keyboard', price: '89.99', inventory: 25 },
  mouse: { sku: 'QA-MS-002', name: 'Wireless Mouse', price: '29.99', inventory: 50 },
  monitor: { sku: 'QA-MN-003', name: '27-inch Monitor', price: '249.00', inventory: 3 },
  hub: { sku: 'QA-HB-004', name: 'USB-C Hub', price: '39.95', inventory: 0 },
  cableTies: { sku: 'QA-CT-005', name: 'Cable Ties (10 pack)', price: '0.29', inventory: 1000 },
  webcam: { sku: 'QA-WC-006', name: 'HD Webcam', price: '59.50', inventory: 10 },
  laptopStand: {
    sku: 'QA-LS-007',
    name: 'Laptop Stand (Discontinued)',
    price: '45.00',
    inventory: 12,
    isActive: false,
  },
} as const;

export const seedProductCount = Object.keys(seedProducts).length;
