from app.database.connection import engine
from sqlalchemy import text

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        print("Databáze je připojená!")
        print(result.scalar())

except Exception as error:
    print("Připojení k databázi selhalo:")
    print(error)
