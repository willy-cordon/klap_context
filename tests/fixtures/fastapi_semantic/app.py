from fastapi import FastAPI

app = FastAPI()

class OrderService:
    def create(self):
        return {"created": True}

service = OrderService()

@app.post("/orders")
def create_order():
    return service.create()
