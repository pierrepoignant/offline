#!/bin/bash
# Initialize Alembic and create initial migration

echo "Initializing Alembic..."

# Check if alembic is installed
if ! command -v alembic &> /dev/null; then
    echo "Alembic not found. Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Initialize Alembic (if not already initialized)
if [ ! -d "migrations/versions" ]; then
    echo "Creating migrations directory..."
    mkdir -p migrations/versions
fi

# Create initial migration
echo "Creating initial migration..."
alembic revision --autogenerate -m "Initial migration"

echo "✓ Alembic initialized!"
echo ""
echo "To apply migrations, run:"
echo "  alembic upgrade head"

