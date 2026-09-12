from fastapi import FastAPI

app = FastAPI()

PRODUCTS = {1: {"id": 1, "name": "Laptop", "price": 999.99},
            2: {"id": 2, "name": "Mouse", "price": 19.99}}

@app.get("/products")
def list_products(): return list (PRODUCTS.values())

@app.get("/products/{product_id}")
def get_product(product_id: int): return PRODUCTS.get(product_id, {})

@app.get("/health")
def health(): return {"ok": True, "service": "productos"}

