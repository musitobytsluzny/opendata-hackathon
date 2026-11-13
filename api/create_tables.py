from app.database.connection import Base, engine
from app.models import User, Profile

Base.metadata.create_all(bind=engine)

print("Databázové tabulky byly vytvořeny!")