# Changelog

All notable changes to OpsIQ will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-01-28

### Added
- 7 AI agents with LLM-first, rule-based fallback architecture
- PostgreSQL-backed RBAC with async SQLAlchemy
- Vector memory store for agent context persistence
- Request body size limiting middleware (10MB max)
- Production-grade Docker Compose with health checks
- GitHub Actions CI/CD pipeline
- Prometheus metrics + Grafana dashboards
- 222 test cases (unit, E2E, performance, security)
- Frontend with 11 fully-wired pages
- WebSocket real-time updates
- Typed API client with TanStack Query hooks
- Zustand auth store with localStorage persistence
- OpenAPI/Swagger documentation at /docs and /redoc
- Locust load testing with realistic user scenarios
- Production deployment and backup scripts

### Changed
- All dependencies pinned to exact versions for reproducible builds
- API Dockerfile updated to version 0.2.0
- Dashboard service uses production Next.js build
- Middleware registration cleaned up (no duplicates)

### Fixed
- Duplicate middleware registration in app.py
- Version mismatch between pyproject.toml and Dockerfile
- Missing LOG_LEVEL configuration
- Missing environment variable documentation
- Frontend .gitignore completeness

## [0.1.0] - 2025-01-01

### Added
- Initial project setup
- Basic API endpoints
- PostgreSQL database integration
- Redis caching layer
- Docker support
- Basic authentication
