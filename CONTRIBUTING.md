# Contributing to Kahani

We love your input! We want to make contributing to Kahani as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features
- Becoming a maintainer

## 🚀 Quick Start for Contributors

1. **Fork the repository**
2. **Clone your fork**: `git clone https://github.com/yourusername/kahani.git`
3. **Set up development environment**: Follow the [Development Setup](#development-setup) below
4. **Create a branch**: `git checkout -b feature/amazing-feature`
5. **Make changes and test**
6. **Submit a pull request**

## 🛠️ Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Git
- Docker (optional, for containerized development)

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies

# Set up environment
cp ../.env.template ../.env
# Edit .env with your configuration

# Initialize database
python -c "from app.database import init_db; init_db()"

# Run tests
python -m pytest tests/

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install

# Run tests
npm test

# Run linting
npm run lint

# Start development server
npm run dev
```

## 📝 Development Workflow

### Branch Naming
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring
- `test/description` - Test improvements

### Commit Messages
We follow conventional commit format:
```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or modifying tests
- `chore`: Maintenance tasks

Examples:
```
feat(auth): add JWT token refresh functionality
fix(stories): resolve scene deletion bug
docs(readme): update installation instructions
```

## 🧪 Testing

### Backend Tests
```bash
cd backend
python -m pytest tests/ -v
python -m pytest tests/ --cov=app --cov-report=html
```

### Frontend Tests
```bash
cd frontend
npm test
npm run test:coverage
```

### Integration Tests
```bash
# Start services
docker-compose up -d

# Run health checks
./health-check.sh

# Run integration tests
npm run test:integration
```

## 🎨 Code Style

### Python (Backend)
We use Black for code formatting and flake8 for linting:
```bash
cd backend
black app/ tests/
flake8 app/ tests/
```

### TypeScript/JavaScript (Frontend)
We use ESLint and Prettier:
```bash
cd frontend
npm run lint
npm run lint:fix
npm run format
```

## 📋 Pull Request Process

1. **Ensure your code follows our style guidelines**
2. **Add tests for new functionality**
3. **Update documentation as needed**
4. **Ensure all tests pass**
5. **Update the CHANGELOG.md if applicable**

### Pull Request Template
When creating a PR, please include:
- **Description**: What does this PR do?
- **Type of change**: Bug fix, feature, docs, etc.
- **Testing**: How was this tested?
- **Checklist**: 
  - [ ] Tests pass
  - [ ] Code follows style guidelines
  - [ ] Documentation updated
  - [ ] CHANGELOG.md updated (if applicable)

## 🐛 Reporting Bugs

We use GitHub Issues to track bugs. Report a bug by [opening a new issue](https://github.com/yourusername/kahani/issues/new).

**Great Bug Reports** tend to have:
- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening)

### Bug Report Template
```markdown
**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Environment:**
 - OS: [e.g. iOS]
 - Browser [e.g. chrome, safari]
 - Version [e.g. 22]

**Additional context**
Add any other context about the problem here.
```

## 💡 Feature Requests

We use GitHub Issues to track feature requests. Suggest a feature by [opening a new issue](https://github.com/yourusername/kahani/issues/new).

**Great Feature Requests** include:
- A clear description of the problem you're trying to solve
- A description of your proposed solution
- Any additional context or screenshots

## 🏗️ Architecture Guidelines

### Backend (FastAPI)
- Use SQLAlchemy models for database entities
- Follow dependency injection patterns
- Implement proper error handling
- Use Pydantic models for API validation
- Write comprehensive docstrings

### Frontend (Next.js)
- Use TypeScript for type safety
- Follow React best practices
- Use Zustand for state management
- Implement proper error boundaries
- Use Tailwind CSS for styling

### Database
- Always create migrations for schema changes
- Use descriptive names for tables and columns
- Add proper indexes for performance
- Document complex queries

## 🔒 Security

If you discover a security vulnerability, please send an email to [security@yourdomain.com] instead of using the issue tracker. All security vulnerabilities will be promptly addressed.

## 📚 Documentation

- Update README.md for user-facing changes
- Update API documentation for backend changes
- Add inline comments for complex logic
- Update type definitions for TypeScript changes

### Documentation Guidelines
- Use clear, concise language
- Include code examples where helpful
- Keep documentation up-to-date with code changes
- Use proper Markdown formatting

## 🎯 Coding Standards

### General Principles
- Write self-documenting code
- Follow SOLID principles
- Prefer composition over inheritance
- Write tests for new functionality
- Keep functions small and focused

### Python Standards
- Follow PEP 8 style guide
- Use type hints where appropriate
- Write docstrings for public functions
- Use meaningful variable names
- Handle exceptions appropriately

### TypeScript Standards
- Use strict TypeScript configuration
- Define proper interfaces and types
- Use meaningful component and function names
- Follow React hooks guidelines
- Implement proper error handling

## 🤝 Code Review Guidelines

### For Authors
- Keep PRs focused and small
- Write clear commit messages
- Add tests for your changes
- Update documentation as needed
- Be responsive to feedback

### For Reviewers
- Be constructive and kind
- Focus on the code, not the person
- Provide specific, actionable feedback
- Approve when changes look good
- Request changes if issues need addressing

## 🏷️ Release Process

1. **Update version numbers** in package.json and setup.py
2. **Update CHANGELOG.md** with changes
3. **Create a release branch**: `release/v1.0.0`
4. **Test thoroughly** in staging environment
5. **Create a pull request** to main
6. **Tag the release** after merging
7. **Deploy to production**

## ❓ Questions?

Don't hesitate to ask questions! You can:
- Open a [GitHub Discussion](https://github.com/yourusername/kahani/discussions)
- Join our community chat
- Email the maintainers

## 📄 License

By contributing, you agree that your contributions will be licensed under the same MIT License that covers the project.