
# StockPilot - System Architecture

## 1. Architecture Style

StockPilot uses a modular monolith architecture.

The backend is a single Django application divided into
independent business modules.

The frontend is a separate React application.

## 2. High-Level Components

### Frontend
React + TypeScript

Responsibilities:
- User interface
- Client-side navigation
- Form validation
- API communication
- Data presentation
- Client-side state management

### Backend
Django + Django REST Framework

Responsibilities:
- Authentication
- Authorization
- Business rules
- Request validation
- Transaction management
- API responses

### Database
PostgreSQL

Responsibilities:
- Persistent business data
- Relational integrity
- Transactions
- Constraints
- Indexes

### Background Processing
Redis + Celery

Responsibilities:
- Asynchronous notifications
- Scheduled reports
- Background imports and exports

## 3. Backend Module Boundaries

- accounts: users and authentication
- organizations: businesses and memberships
- products: products, variants and categories
- inventory: stock and movements
- suppliers: supplier management
- purchasing: purchase orders and receiving
- customers: customer management
- sales: sales, items and returns
- payments: payment records
- reports: business analytics

## 4. Request Lifecycle

1. User interacts with React.
2. React sends an HTTP request.
3. Django authenticates the request.
4. Permissions are checked.
5. The request is validated.
6. Business logic is executed.
7. Database operations are committed.
8. Django returns a JSON response.
9. React updates the interface.

## 5. Multi-Tenant Architecture

StockPilot uses a shared database and shared schema.

Business-owned records are associated with an organization.

All relevant queries must be scoped to the
authenticated user's authorized organization.

## 6. Business Logic

Complex business operations belong in dedicated
service functions or modules.

API views should coordinate requests and responses,
not contain all business logic.

Database transactions protect operations that
must succeed or fail as a single unit.

## 7. Deployment Architecture

Production deployment will contain:

- React frontend
- Django application server
- PostgreSQL database
- Redis
- Celery worker
- Celery scheduler where required

Docker will provide reproducible application
environments.
