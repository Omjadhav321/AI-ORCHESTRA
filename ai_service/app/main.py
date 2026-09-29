from fastapi import FastAPI
from pydantic import BaseModel
import numpy as np
import random

app = FastAPI()

class PredictionInput(BaseModel):
    age: int
    severity: int
    visit_type: str
    dept: str

@app.post("/predict")
async def predict_wait(data: PredictionInput):
    # Mock logic simulating a Scikit-learn model
    base_wait = 15
    priority_score = (data.severity * 5) + (data.age < 12 or data.age > 65) * 20
    wait_time = base_wait + (10 - data.severity) * 2
    
    return {
        "predicted_wait": int(wait_time),
        "priority_score": int(priority_score),
        "triage": "Critical" if priority_score > 70 else "Urgent" if priority_score > 40 else "Routine",
        "confidence": random.randint(85, 98)
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
