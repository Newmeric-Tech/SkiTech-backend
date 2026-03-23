from fastapi import FastAPI
from config import settings
from middleware.exception_handler import ExceptionHandlerMiddleware

from fastapi.middleware.cors import CORSMiddleware
from api.v1.router import api_router

app = FastAPI(title=settings.APP_NAME)

# Add CORS middleware to allow the browser (Swagger UI) to talk to the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for local testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ExceptionHandlerMiddleware)

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME}

@app.get("/demo-error")
async def demo_error():
    """
    Demo endpoint to show how the Global Exception Handler 
    catches a crash and returns a professional JSON response.
    """
    raise ValueError("This is a simulated system error for the demo!")

@app.get("/")
async def root():
    return {"message": "Welcome to FastAPI Project"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
