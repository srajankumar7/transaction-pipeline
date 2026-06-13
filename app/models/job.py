from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="pending")   # pending | processing | completed | failed
    row_count_raw = Column(Integer, default=0)
    row_count_clean = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
