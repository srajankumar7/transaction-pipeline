from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from app.database import Base

class JobSummary(Base):
    __tablename__ = "job_summaries"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), unique=True, nullable=False)
    total_spend_inr = Column(Float, default=0.0)
    total_spend_usd = Column(Float, default=0.0)
    top_merchants = Column(Text, nullable=True)   # JSON string
    anomaly_count = Column(Integer, default=0)
    narrative = Column(Text, nullable=True)
    risk_level = Column(String, nullable=True)    # low | medium | high
