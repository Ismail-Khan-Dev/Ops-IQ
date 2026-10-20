# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| < 0.2   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability within OpsIQ, please send an email to the maintainers. All security vulnerabilities will be promptly addressed.

**Please do NOT report security vulnerabilities through public GitHub issues.**

## Security Measures

### Authentication & Authorization
- API key authentication with SHA-256 hashed storage
- Role-Based Access Control (RBAC) with 4 roles: admin, analyst, operator, viewer
- JWT tokens for session management
- bcrypt password hashing for admin users

### Data Protection
- All API keys stored as bcrypt or SHA-256 hashed values
- No plain-text secrets in code or configuration
- Environment variables for all sensitive configuration
- CORS configured for specific origins only

### Infrastructure Security
- Rate limiting per IP (60 req/min production default)
- Request body size limiting (10MB max)
- Input sanitization middleware (XSS, SQL injection, path traversal prevention)
- Security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
- Non-root Docker containers
- HTTPS enforced in production

### Audit & Monitoring
- Comprehensive audit logging for all security events
- Structured JSON logging with request IDs
- Prometheus metrics for security events
- Alert rules for suspicious activity patterns

### Dependencies
- All dependencies pinned to exact versions
- Regular security updates via Dependabot
- Docker image vulnerability scanning

## Best Practices

1. **Environment Variables**: Never commit `.env` files. Use `.env.example` as template.
2. **API Keys**: Rotate keys periodically. Use different keys per environment.
3. **Database**: Use strong passwords. Enable SSL for PostgreSQL connections.
4. **Redis**: Set password authentication. Use non-default ports.
5. **Docker**: Keep images updated. Scan for vulnerabilities regularly.

## Contact

For security concerns, please contact the maintainers directly.
