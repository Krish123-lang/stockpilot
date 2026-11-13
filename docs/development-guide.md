
# StockPilot - Development Guide

## 1. Git Branching

main:
Stable and reviewed code.

feature/<name>:
New features.

fix/<name>:
Bug fixes.

docs/<name>:
Documentation changes.

## 2. Commit Convention

Use conventional commit prefixes:

feat: New functionality
fix: Bug fixes
docs: Documentation changes
refactor: Code restructuring
test: Tests
chore: Maintenance

Examples:

feat: add organization membership model
fix: prevent duplicate inventory movements
docs: document database architecture

## 3. Development Principles

- Keep business logic outside API views.
- Prefer explicit and readable code.
- Avoid unnecessary abstractions.
- Validate input at system boundaries.
- Use database constraints for data integrity.
- Write tests for business rules.
- Never commit secrets.
- Review changes before merging.

## 4. Testing

Backend:
Django testing framework and API tests.

Frontend:
Vitest and React Testing Library.

## 5. Code Review

Before merging:

- Check functionality.
- Check permissions.
- Check tenant isolation.
- Check validation.
- Check tests.
- Check database integrity.
- Check readability.

## 6. Development Environment

Windows 11
Visual Studio Code
PowerShell
Python
Node.js
PostgreSQL
Git
Docker
