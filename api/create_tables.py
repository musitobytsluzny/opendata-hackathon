from app.database.connection import Base, engine
from app.models import Profile, User

Base.metadata.create_all(bind=engine)

print("Databázové tabulky byly vytvořeny!")
