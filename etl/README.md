# ETL / vývojový seed

`main.py` je jednorázový krok po vytvoření API tabulek a před spuštěním API.
Zatím ověřuje připravenost databáze; konkrétní data nejsou definovaná.
Seed doplň do `seed(connection)` a používej idempotentní inserty/upserty,
protože krok lze spustit opakovaně. Celý běh používá jednu transakci;
chyba způsobí rollback a nenulový exit code, který zablokuje start API.

```sh
make seed
```

V developu je adresář připojený do kontejneru, takže změny `main.py` nevyžadují
rebuild. Změny `requirements.txt` ano. Lokální vstupy patří do `etl/data/`,
výstupy do `etl/output/`; oba adresáře jsou ignorované Gitem i build kontextem.
