# Contributing to Sentinel

Thank you for your interest in contributing to Sentinel! This document provides guidelines for contributing.

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/sentinel.git
   cd sentinel
   ```

2. Run the setup script:
   ```bash
   bash setup.sh
   ```

3. Copy the environment template and add your API key:
   ```bash
   cp .env.example .env
   # Edit .env and add your GOOGLE_API_KEY
   ```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python tests/red_team_test.py
python tests/test_command_auditor.py
```

## Adding New Security Rules

Follow this workflow when adding new laws to the constitution:

### 1. Update the Constitution

Add or modify rules in `Sentinel-Constitution.yaml`:

```yaml
hard_kill:
  blocked_strings:
    - your_new_blocked_string
```

### 2. Implement Deterministic Checks

If the rule can be checked deterministically, add it to `sentinel/command_auditor.py`:

```python
def _hard_kill_filter(self, command: str) -> Optional[AuditDecision]:
    # Add your check here
    if self._your_new_check(command):
        return AuditDecision.reject("Your rejection reason", risk_score=10)
```

### 3. Add Tests

Add a test case in `tests/test_command_auditor.py`:

```python
def test_your_new_rule() -> None:
    """Description of what your rule does."""
    constitution = {...}
    auditor = CommandAuditor(constitution)
    
    decision = auditor.audit("command that should be blocked")
    assert not decision.allowed
    assert "expected reason" in decision.reason
```

### 4. Verify

```bash
python -m pytest tests/ -v
```

## Code Style

- Use type hints for all function signatures
- Follow PEP 8 guidelines
- Keep functions focused and single-purpose
- Add docstrings for public methods

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests to ensure they pass
5. Commit with clear messages
6. Push to your fork
7. Open a Pull Request

## Security Considerations

- **Never commit `.env` files or API keys**
- All new rules should default to **fail-closed** behavior
- Ambiguous commands should be rejected, not allowed
- Test bypass attempts in `tests/red_team_test.py`

## Questions?

Open an issue on GitHub for questions or discussions.
