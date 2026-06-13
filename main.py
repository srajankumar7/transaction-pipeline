from fastapi import FastAPI
from app.database import Base, engine
from app.models import Job, Transaction, JobSummary   # ensure tables are registered
from app.api.jobs import router as jobs_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Transaction Processing Pipeline")
app.include_router(jobs_router)

@app.get("/")
def home():
    return {"message": "AI Transaction Pipeline Running", "docs": "/docs"}
