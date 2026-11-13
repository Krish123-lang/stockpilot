
# StockPilot - Database Design

## 1. Database

PostgreSQL.

## 2. Primary Key Strategy

UUID primary keys will be used for application entities
where appropriate.

## 3. Core Entities

### Accounts and Organizations
- User
- Organization
- Membership

### Product Catalogue
- Category
- Product
- ProductVariant
- SerializedUnit

### Inventory
- StockMovement

### Purchasing
- Supplier
- PurchaseOrder
- PurchaseOrderItem
- GoodsReceipt
- GoodsReceiptItem

### Customers and Sales
- Customer
- Sale
- SaleItem
- SalesReturn
- SalesReturnItem

### Payments and Auditing
- Payment
- AuditLog

## 4. Relationship Rules

- A user can belong to multiple organizations.
- An organization can have multiple members.
- An organization owns its business records.
- A category can contain multiple products.
- A product can have multiple variants.
- A supplier can have multiple purchase orders.
- A purchase order can have multiple goods receipts.
- A customer can have multiple sales.
- A sale can contain multiple sale items.
- A sale can have multiple payments.
- A sale can have multiple returns.
- A product can have multiple stock movements.

## 5. Data Integrity

- Enforce organization-level SKU uniqueness.
- Use foreign key constraints.
- Use DecimalField for financial values.
- Use database transactions for critical operations.
- Preserve historical financial records.
- Validate organization relationships.
- Prevent unauthorized cross-organization references.

## 6. Inventory

Inventory history will be represented through stock
movement records.

Current inventory will be maintained through a
transactionally updated balance mechanism, with
movement history providing traceability.

The balance and movement records must remain
consistent.

## 7. Financial Data

Store monetary amounts using decimal precision.

Store currency explicitly where necessary.

Never use floating-point arithmetic for financial
calculations.

## 8. Design Status

Initial logical design.

Detailed model fields, constraints, indexes, and
relationship cardinalities will be finalized before
the corresponding implementation.
