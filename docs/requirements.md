
# StockPilot - Software Requirements Specification

## 1. Introduction

StockPilot is an inventory and business management SaaS
application for small and medium-sized retail businesses.

The initial target customer is an electronics retailer
operating in Nepal.

## 2. Problem Statement

Small retailers frequently manage inventory, purchases,
sales, and payments using spreadsheets and manual records.

This creates inaccurate stock information, poor transaction
traceability, and inefficient business reporting.

StockPilot aims to centralize these operations.

## 3. Target Users

- Business owners
- Managers
- Sales employees
- Inventory employees

## 4. Functional Requirements

### Authentication
- User registration
- Login and logout
- Password reset
- Organization membership

### Organization Management
- Create business organization
- Invite employees
- Assign employee roles
- Enforce organization data isolation

### Product Management
- Create, update, list, and archive products
- Manage categories
- Enforce organization-level SKU uniqueness
- Support product variants
- Support optional serial-number tracking

### Inventory Management
- Record inventory movements
- Track sellable and damaged stock
- Prevent unauthorized stock changes
- Maintain inventory history

### Purchasing
- Manage suppliers
- Create purchase orders
- Confirm purchase orders
- Receive full or partial deliveries

### Sales
- Manage customers
- Create and complete sales
- Generate invoices
- Support sales returns

### Payments
- Record payments
- Support partial payments
- Calculate outstanding balances

### Reporting
- Sales summaries
- Inventory summaries
- Low-stock reports
- Business performance dashboard

## 5. Non-Functional Requirements

- Secure authentication and authorization
- Organization-level data isolation
- Transaction-safe inventory operations
- Reliable financial calculations
- Maintainable modular architecture
- Responsive user interface
- Automated testing
- Production deployment and backups

## 6. Business Rules

1. Every business-owned record belongs to an organization.
2. A SKU must be unique within its organization.
3. Purchase orders do not increase stock by themselves.
4. Actual goods receipts increase stock.
5. Completed sales decrease sellable stock.
6. Negative stock is prohibited by default.
7. Completed financial transactions cannot be silently deleted.
8. Payments must reference valid sales.
9. Returns must reference original sales.
10. All important stock changes must be traceable.

## 7. MVP Scope

Included:
- Multi-tenancy
- Four business roles
- Products and categories
- Inventory
- Suppliers and purchases
- Customers and sales
- Payments
- Returns
- Reports
- Audit logs

Deferred:
- Multiple warehouses
- Advanced accounting
- AI forecasting
- Mobile applications
- Subscription billing

## 8. Initial Market

Nepal.

Initial business scenario:
Electronics retail shop.
