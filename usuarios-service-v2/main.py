from fastapi import FastAPI

app = FastAPI()

USERS = {1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
         2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
         3: {"id": 3, "name": "Charlie", "email": "charlie@example.com"}}

@app.get("/users")
def list_users(): return list(USERS.values())

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = USERS.get(user_id,{})
    return {**user, "served_by": "v2"} if user else {}

@app.get("/health")
def health(): return {"ok": True, "service": "usuarios", "version": "v2"}

