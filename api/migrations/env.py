from alembic import context
from app.database.connection import Base, engine
from app.models import Profile, User  # noqa: F401 - register migration metadata

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
