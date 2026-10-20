# Contributing to OpsIQ

Thank you for your interest in contributing to OpsIQ! This document provides guidelines and information for contributors.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Setup](#development-setup)
4. [Contributing Process](#contributing-process)
5. [Coding Standards](#coding-standards)
6. [Testing](#testing)
7. [Documentation](#documentation)
8. [Pull Request Process](#pull-request-process)
9. [Issue Guidelines](#issue-guidelines)
10. [Community](#community)

## Code of Conduct

### Our Pledge

We pledge to make participation in our project a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity and expression, level of experience, nationality, personal appearance, race, religion, or sexual identity and orientation.

### Our Standards

Examples of behavior that contributes to creating a positive environment:

- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

Examples of unacceptable behavior:

- The use of sexualized language or imagery and unwelcome sexual attention or advances
- Trolling, insulting/derogatory comments, and personal or political attacks
- Public or private harassment
- Publishing others' private information without explicit permission
- Other conduct which could reasonably be considered inappropriate in a professional setting

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Git
- PostgreSQL 16+
- Redis 7+

### Fork and Clone

```bash
# Fork the repository on GitHub

# Clone your fork
git clone https://github.com/your-username/ecom-ops-automation-system.git
cd ecom-ops-automation-system

# Add upstream remote
git remote add upstream https://github.com/Ismail-2001/ecom-ops-automation-system.git

# Create a feature branch
git checkout -b feature/your-feature-name
```

## Development Setup

### Environment Variables

```bash
# Copy environment file
cp .env.example .env

# Edit with your API keys
nano .env
```

### Docker Development

```bash
# Start development environment
docker compose -f docker-compose.dev.yml up -d

# Run migrations
docker compose exec app alembic upgrade head

# Seed demo data
docker compose exec app python -m ecommerce_ops.demo.seed

# Access application
open http://localhost:8000
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Start PostgreSQL and Redis
docker compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start development server
uvicorn ecommerce_ops.api.app:app --reload
```

## Contributing Process

### 1. Find or Create an Issue

- Check existing [issues](https://github.com/Ismail-2001/ecom-ops-automation-system/issues)
- Create a new issue if needed
- Comment on the issue you're working on

### 2. Create a Branch

```bash
# Update main branch
git fetch upstream
git checkout main
git merge upstream/main

# Create feature branch
git checkout -b feature/your-feature-name
```

### 3. Make Changes

- Follow coding standards
- Write tests for new functionality
- Update documentation as needed
- Keep commits atomic and well-described

### 4. Test Your Changes

```bash
# Run tests
pytest

# Run linting
ruff check .

# Run type checking
mypy ecommerce_ops

# Run security checks
bandit -r ecommerce_ops
```

### 5. Submit a Pull Request

- Push your branch to your fork
- Create a pull request
- Fill out the PR template
- Wait for review

## Coding Standards

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/)
- Use [Black](https://black.readthedocs.io/) for formatting
- Use [Ruff](https://docs.astral.sh/ruff/) for linting
- Maximum line length: 88 characters

### Type Hints

```python
# Good
def process_order(order_id: str, priority: int = 0) -> Order:
    """Process an order."""
    pass

# Bad
def process_order(order_id, priority=0):
    pass
```

### Docstrings

```python
def calculate_risk_score(order: Order) -> float:
    """Calculate fraud risk score for an order.

    Args:
        order: The order to analyze.

    Returns:
        Risk score between 0 and 1.

    Raises:
        ValueError: If order is invalid.
    """
    pass
```

### Import Order

```python
# Standard library
import os
from datetime import datetime
from typing import Optional

# Third-party
import pytest
from fastapi import APIRouter
from sqlalchemy import select

# Local
from ecommerce_ops.config import settings
from ecommerce_ops.models import Order
```

### Error Handling

```python
# Good
try:
    result = await process_order(order_id)
except ValueError as e:
    logger.error("Invalid order: %s", e)
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.exception("Unexpected error processing order")
    raise HTTPException(status_code=500, detail="Internal server error")

# Bad
try:
    result = await process_order(order_id)
except:
    pass
```

## Testing

### Test Structure

```
tests/
├── unit/
│   ├── test_agents/
│   ├── test_api/
│   ├── test_models/
│   └── test_services/
├── integration/
│   ├── test_database.py
│   ├── test_redis.py
│   └── test_shopify.py
├── e2e/
│   └── test_workflows.py
├── conftest.py
└── __init__.py
```

### Writing Tests

```python
import pytest
from ecommerce_ops.agents.fraud_detection import FraudDetectionAgent

class TestFraudDetectionAgent:
    """Test fraud detection agent."""

    @pytest.mark.asyncio
    async def test_detect_fraud(self, mock_order):
        """Test fraud detection."""
        agent = FraudDetectionAgent()
        result = await agent.analyze(mock_order)

        assert result.risk_score >= 0
        assert result.risk_score <= 1
        assert result.decision in ["approve", "flag", "reject"]

    @pytest.mark.asyncio
    async def test_high_risk_order(self, high_risk_order):
        """Test high risk order detection."""
        agent = FraudDetectionAgent()
        result = await agent.analyze(high_risk_order)

        assert result.risk_score > 0.7
        assert result.decision == "reject"
```

### Test Coverage

```bash
# Run with coverage
pytest --cov=ecommerce_ops --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Test Markers

```python
@pytest.mark.unit
def test_unit():
    pass

@pytest.mark.integration
def test_integration():
    pass

@pytest.mark.e2e
def test_e2e():
    pass

@pytest.mark.slow
def test_slow():
    pass
```

## Documentation

### Code Documentation

- Write docstrings for all public functions
- Include type hints
- Document complex algorithms
- Add examples for non-obvious usage

### API Documentation

- Update OpenAPI schema
- Add examples for new endpoints
- Document error responses

### README Updates

- Update feature list if adding new features
- Update API endpoints if adding new routes
- Update configuration if adding new settings

## Pull Request Process

### PR Template

```markdown
## Description

Brief description of changes.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist

- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
- [ ] Tests pass locally
```

### Review Process

1. **Automated Checks**
   - CI/CD pipeline passes
   - Tests pass
   - Linting passes
   - Type checking passes

2. **Code Review**
   - At least 1 approval required
   - Address all review comments
   - No unresolved conversations

3. **Merge**
   - Squash and merge to main
   - Delete feature branch

### Commit Messages

```
feat: add new fraud detection algorithm

- Implement machine learning model for fraud detection
- Add training pipeline
- Update API endpoints

Closes #123
```

## Issue Guidelines

### Bug Reports

```markdown
## Bug Description

Describe the bug.

## Steps to Reproduce

1. Go to '...'
2. Click on '...'
3. See error

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened.

## Environment

- OS: [e.g., Windows 10]
- Python: [e.g., 3.11.0]
- Browser: [e.g., Chrome 120]
```

### Feature Requests

```markdown
## Feature Description

Describe the feature.

## Use Case

Why is this feature needed?

## Proposed Solution

How you think it should work.

## Alternatives Considered

Other solutions you considered.
```

## Community

### Communication Channels

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and ideas
- **Discord**: For real-time chat (if applicable)

### Getting Help

1. Check documentation
2. Search existing issues
3. Create a new issue
4. Ask in discussions

### Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

If you have questions about contributing, please open a discussion or issue.
