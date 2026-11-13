
# ADR-001: Use Modular Monolith Architecture

## Status

Accepted.

## Context

StockPilot contains several business domains:

- Products
- Inventory
- Purchasing
- Sales
- Payments
- Organizations

A distributed microservices architecture would introduce
unnecessary infrastructure and operational complexity
for the initial product.

## Decision

Use a modular monolith built with Django.

Each business domain will be represented by a dedicated
Django application with clear responsibilities.

Modules may communicate through explicit service
interfaces and shared domain models where appropriate.

## Consequences

Positive:
- Simpler deployment
- Easier debugging
- Strong database transactions
- Lower infrastructure complexity
- Clear module boundaries

Trade-offs:
- Modules share the same application runtime.
- Developers must maintain boundaries carefully.
- Independent service deployment is not available.

## Future Considerations

Individual modules may be extracted into services
if real scaling or organizational requirements justify it.

Microservices are not part of the initial MVP.
