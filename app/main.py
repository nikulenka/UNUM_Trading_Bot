import uvicorn
from fastapi import FastAPI
from fastapi import HTTPException

app = FastAPI(title="AI Trade Bot")

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

# A mock function simulating a database
def is_database_connected():
    return True 

@app.get("/health/ready")
def readiness_check():
    """
    Checks if the application is ready to receive traffic.
    """
    db_status = is_database_connected()
    
    if db_status:
        return {"status": "ready"}
    else:
        # If dependencies aren't ready, return a 503 error
        raise HTTPException(status_code=503, detail="Database not ready")