# Offline Team Utilities

Flask application for the offline team with user authentication and management.

## Features

- User authentication and session management
- User management (create, edit, deactivate users)
- Admin role-based access control
- PostgreSQL database integration with SQLAlchemy ORM
- Alembic for database migrations
- Blueprint-based architecture for easy extension
- Core models: Brands, Categories, Channels, Locations, Items
- Sellthrough data management

## Project Structure

```
offline/
├── app.py                 # Main Flask application
├── db_utils.py            # Database utilities
├── config.ini            # Configuration file
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker configuration
├── auth/                 # Auth blueprint
│   ├── __init__.py
│   ├── blueprint.py      # Auth routes and logic
│   └── templates/        # Auth templates
│       └── auth/
│           ├── login.html
│           ├── users_list.html
│           └── edit_user.html
├── templates/            # Base templates
│   └── base.html
├── database/             # Database scripts
│   ├── create_users_table.sql
│   └── init_database.py
└── k8s/                  # Kubernetes deployment files
    ├── configmap.yaml
    ├── secret.yaml
    ├── deployment.yaml
    ├── service.yaml
    ├── ingress.yaml
    └── kustomization.yaml
```

## Setup

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure database in `config.ini` (use `[postgre-local]` section for local development)

3. Initialize the database:
```bash
python database/init_database.py
```

4. Initialize Alembic and create initial migration:
```bash
./init_alembic.sh
# Or manually:
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

5. Run the application:
```bash
python app.py
```

The app will be available at `http://localhost:5000`

### Docker

1. Build the Docker image:
```bash
docker build -t offline-app .
```

2. Run the container:
```bash
docker run -p 5000:5000 \
  -e DB_HOST=your_db_host \
  -e DB_PORT=5432 \
  -e DB_USER=your_db_user \
  -e DB_PASSWORD=your_db_password \
  -e DB_NAME=offline \
  offline-app
```

### Kubernetes Deployment

1. Update secrets in `k8s/secret.yaml`:
   - Database credentials
   - Flask secret key (generate a secure random key)

2. Update config in `k8s/configmap.yaml` if needed

3. Deploy to Kubernetes:
```bash
kubectl apply -k k8s/
```

The application will be deployed in the `offline` namespace.

## Default Admin User

The initial admin user is created from `config.ini`:
- Username: `admin` (from `[auth]` section)
- Password: `12345678` (from `[auth]` section)

**Important**: Change the default password after first login!

## Adding New Blueprints

To add a new blueprint:

1. Create a new directory (e.g., `my_feature/`)
2. Create `__init__.py` and `blueprint.py` files
3. Register the blueprint in `app.py`:
```python
from my_feature.blueprint import my_feature_bp
app.register_blueprint(my_feature_bp, url_prefix='/my-feature')
```

## Database

The application uses PostgreSQL with SQLAlchemy ORM. The database name is `offline`.

### Models

- `Brand`: Brands
- `Category`: Categories of products within a brand
- `Channel`: Sales channels (e.g., Walmart)
- `ChannelLocation`: Locations within channels
- `Item`: Specific products with Essor codes
- `SellthroughData`: Sellthrough data with date, revenues, units, stores
- `users`: User accounts with authentication information (legacy table)

### Database Migrations

The application uses Alembic for database migrations:

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

## Environment Variables

- `DB_HOST`: Database host
- `DB_PORT`: Database port (default: 5432)
- `DB_USER`: Database user
- `DB_PASSWORD`: Database password
- `DB_NAME`: Database name (default: offline)
- `FLASK_PORT`: Flask port (default: 5000)
- `FLASK_SECRET_KEY`: Secret key for session management

