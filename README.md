
# StockPilot

StockPilot is a multi-tenant inventory and business management
platform designed for small and medium-sized retailers.

The platform helps businesses manage products, inventory,
suppliers, purchases, sales, customers, payments, and reports
from one centralized application.

## Core Features

- Multi-tenant business accounts
- Role-based access control
- Product and category management
- Inventory movement tracking
- Supplier and purchase management
- Goods receiving and partial deliveries
- Customer and sales management
- Invoice generation
- Partial and full payment tracking
- Sales returns
- Business analytics and reporting
- Audit logging

## Technology Stack

### Backend
- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery

### Frontend
- React
- TypeScript
- Tailwind CSS
- TanStack Query

### Infrastructure
- Docker
- Docker Compose
- GitHub Actions

## Architecture

StockPilot follows a modular monolith architecture.
The backend exposes versioned REST APIs consumed by
the React frontend.

The application uses a shared PostgreSQL database with
organization-scoped business data.

## Project Structure

- backend/ - Django backend
- frontend/ - React frontend
- docs/ - Technical documentation

## Development Status

Currently in the requirements and system design phase.

## Documentation

- [Requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [Database Design](docs/database-design.md)
- [API Design](docs/api-design.md)
- [Development Guide](docs/development-guide.md)
- [Architecture Decision Records](docs/decisions/)

## License

License not yet selected.
