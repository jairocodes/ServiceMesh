from fastapi import FastAPI

app = FastAPI()

USERS = {1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
         2: {"id": 2, "name": "Bob", "email": "bob@example.com"}}

@app.get("/users")
def list_users(): return list(USERS.values())

@app.get("/users/{user_id}")
def get_user(user_id: int): return USERS.get(user_id, {})

@app.get("/health")
def health(): return {"ok": True, "service": "usuarios"}
