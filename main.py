from fastapi import FastAPI
from config import settings

app = FastAPI(title=settings.APP_NAME)

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI Project"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
