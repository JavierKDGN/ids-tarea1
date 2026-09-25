from fastapi import FastAPI
from app.database import engine, Base, get_db


try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Error creating tables: {e}")

app = FastAPI()

@app.get("")


@app.get("/")
def read_root():
    return {"Hello": "World"}
