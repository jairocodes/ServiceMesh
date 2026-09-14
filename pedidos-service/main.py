from fastapi import FastAPI
import httpx, os

app = FastAPI()
#Las URL internas del cluster - Istio intercepta estas llamadas
USUARIOS_URL = os.getenv("USUARIOS_URL", "http://usuarios-service")
PRODUCTOS_URL = os.getenv("PRODUCTOS_URL", "http://productos-service")

@app.post("/orders")
async def create_order(user_id: int, product_id: int):
    async with httpx.AsyncClient() as client:
        #Aqui las llamadas HTTP que son interceptadas por Envoy a mTLS automático
        user = (await client.get(f"{USUARIOS_URL}/users/{user_id}")).json()
        product = (await client.get(f"{PRODUCTOS_URL}/products/{product_id}")).json()
    return {"order_id": "ord-001", "user": user, "product": product, "status": "created"}

@app.get("/health")
def health(): return {"ok": True, "service": "pedidos"}

