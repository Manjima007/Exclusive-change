# Exclusive-Change

**Enterprise Feature Flag Service**

A high-concurrency, multi-tenant SaaS backend for managing feature flags with percentage-based rollout.

## 🚀 Features

- **Percentage Rollout**: Gradually roll out features to a percentage of users
- **Deterministic Hashing**: MD5(user_id + flag_key) ensures consistent results
- **Multi-Tenant**: Complete data isolation between tenants
- **High Performance**: Async I/O with Redis caching
- **Audit Logging**: Track all flag changes for compliance
- **Multiple Environments**: dev, staging, production per tenant

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                               │
│  ┌─────────────────────┐       ┌─────────────────────────────┐ │
│  │   Management API    │       │      Evaluation API         │ │
│  │   (JWT Auth)        │       │      (API Key Auth)         │ │
│  │   POST /flags       │       │      POST /evaluate         │ │
│  │   GET /flags        │       │      POST /evaluate/bulk    │ │
│  │   PATCH /flags      │       │      GET /flags/config      │ │
│  └──────────┬──────────┘       └───────────────┬─────────────┘ │
└─────────────┼──────────────────────────────────┼───────────────┘
              │                                  │
┌─────────────┼──────────────────────────────────┼───────────────┐
│             ▼           Service Layer          ▼               │
│  ┌─────────────────────┐       ┌─────────────────────────────┐ │
│  │   FlagService       │       │      FlagEvaluator          │ │
│  │   - CRUD Logic      │       │      - Hash Computation     │ │
│  │   - Validation      │       │      - Rollout Logic        │ │
│  │   - Audit Logging   │       │      - Cache-First Lookup   │ │
│  └──────────┬──────────┘       └───────────────┬─────────────┘ │
└─────────────┼──────────────────────────────────┼───────────────┘
              │                                  │
┌─────────────┼──────────────────────────────────┼───────────────┐
│             ▼        Data Access Layer         ▼               │
│  ┌─────────────────────┐       ┌─────────────────────────────┐ │
│  │     CRUD Layer      │       │      Redis Cache            │ │
│  │   - Tenant Filter   │       │      - TTL: 30s             │ │
│  │   - Pagination      │       │      - Pub/Sub Invalidation │ │
│  └──────────┬──────────┘       └───────────────┬─────────────┘ │
└─────────────┼──────────────────────────────────┼───────────────┘
              │                                  │
              ▼                                  ▼
     ┌─────────────────┐               ┌─────────────────┐
     │   PostgreSQL    │               │     Redis       │
     │   (Supabase)    │               │                 │
     └─────────────────┘               └─────────────────┘
```

## 📁 Project Structure

```
Exclusive-Change/
├── app/
│   ├── api/                    # FastAPI routes
│   │   └── v1/
│   │       └── endpoints/
│   │           ├── flags.py        # Flag CRUD
│   │           ├── evaluate.py     # Flag evaluation
│   │           └── environments.py # Environment management
│   ├── core/                   # Core configuration
│   │   ├── config.py           # Settings
│   │   ├── security.py         # JWT & API Key auth
│   │   └── exceptions.py       # Custom exceptions
│   ├── crud/                   # Data Access Layer
│   ├── db/                     # Database setup
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # Business logic
│   │   ├── evaluator.py        # Flag evaluation
│   │   └── flag_service.py     # Flag management
│   ├── cache/                  # Redis caching
│   └── main.py                 # FastAPI app
├── alembic/                    # Database migrations
├── tests/                      # Test suite
├── .env.example                # Environment template
└── pyproject.toml              # Dependencies
```

## 🛠️ Setup

### Prerequisites

- Python 3.11+
- PostgreSQL (Supabase)
- Redis

### Installation

1. **Clone and install dependencies:**
   ```bash
   cd Exclusive-Change
   pip install -e ".[dev]"
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Supabase and Redis credentials
   ```

3. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

4. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Open API docs:**
   http://localhost:8000/docs

## 🔐 Authentication

### Management API (JWT)

```bash
# Include Supabase JWT token
curl -X POST http://localhost:8000/api/v1/flags \
  -H "Authorization: Bearer <jwt_token>" \
  -H "X-Tenant-ID: <tenant_uuid>" \
  -H "Content-Type: application/json" \
  -d '{"key": "dark-mode", "name": "Dark Mode", "rollout_percentage": 50}'
```

### Evaluation API (API Key)

```bash
# Include API key
curl -X POST http://localhost:8000/api/v1/evaluate \
  -H "X-API-Key: xc_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{"flag_key": "dark-mode", "context": {"user_id": "user-123"}}'
```

## 📊 Flag Evaluation Logic

The evaluation uses deterministic hashing for consistent user experiences:

```python
# Algorithm
hash_value = MD5(user_id + flag_key) % 100

if hash_value < rollout_percentage:
    return True   # Feature is ON for this user
else:
    return False  # Feature is OFF for this user
```

**Example:**
- Flag `dark-mode` with `rollout_percentage=25`
- User `user-123` gets `hash_value=42`
- Since 42 >= 25, user sees the OLD experience
- User `user-456` gets `hash_value=12`
- Since 12 < 25, user sees the NEW feature

## 🗃️ Database Schema

```
tenants
├── id (UUID, PK)
├── name
├── slug (unique)
└── is_active

environments
├── id (UUID, PK)
├── tenant_id (FK)
├── name
├── key (unique per tenant)
└── is_default

flags
├── id (UUID, PK)
├── tenant_id (FK)
├── key (unique per tenant)
├── name
├── rollout_percentage (0-100)
├── is_enabled
└── status (active/inactive/archived)

api_keys
├── id (UUID, PK)
├── tenant_id (FK)
├── environment_id (FK)
├── key_hash (SHA-256)
└── is_active
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific tests
pytest tests/test_evaluator.py -v
```

## 🚢 Deployment

### Docker

```bash
# Build the image
docker build -t exclusive-change:latest .

# Run locally
docker run -p 8000:8000 --env-file .env exclusive-change:latest
```

### Kubernetes

The project uses Kustomize for Kubernetes deployments with staging and production overlays.

```bash
# Preview staging manifests
kubectl kustomize k8s/overlays/staging

# Deploy to staging
kubectl apply -k k8s/overlays/staging

# Deploy to production
kubectl apply -k k8s/overlays/production
```

### CI/CD with GitHub Actions

The project includes automated CI/CD pipelines:

1. **CI Pipeline** (`.github/workflows/ci-cd.yml`):
   - Runs on every push to `main` or `develop`
   - Runs tests with PostgreSQL and Redis services
   - Builds and pushes Docker image to GitHub Container Registry
   - Deploys to staging (develop branch) or production (main branch)

2. **Security Scanning** (`.github/workflows/security.yml`):
   - Dependency vulnerability scanning (pip-audit, Safety)
   - Static code analysis (Bandit, Semgrep)
   - Container image scanning (Trivy)
   - Secret scanning (Gitleaks)

#### Required GitHub Secrets

Set these secrets in your repository settings:

| Secret | Description |
|--------|-------------|
| `KUBE_CONFIG_STAGING` | Base64-encoded kubeconfig for staging cluster |
| `KUBE_CONFIG_PRODUCTION` | Base64-encoded kubeconfig for production cluster |

#### Environments

Configure GitHub Environments for deployment protection:
- **staging**: Auto-deploy from `develop` branch
- **production**: Requires approval, deploys from `main` branch

### Manual Deployment

```bash
# 1. Build and push image
docker build -t ghcr.io/your-org/exclusive-change:latest .
docker push ghcr.io/your-org/exclusive-change:latest

# 2. Update image in kustomization
cd k8s/overlays/production
kustomize edit set image exclusive-change=ghcr.io/your-org/exclusive-change:latest

# 3. Apply to cluster
kubectl apply -k .

# 4. Verify rollout
kubectl rollout status deployment/exclusive-change -n exclusive-change
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_JWT_SECRET` | JWT secret for token validation | Yes |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Yes |
| `APP_ENV` | Environment (development/staging/production) | No |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | No |

## 📝 License

MIT
