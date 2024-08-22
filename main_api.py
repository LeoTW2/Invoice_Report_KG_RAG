import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn
import numpy as np
import pandas as pd
from invoice_analysor import Financial_report

app = FastAPI()

analysor = None

class ReportRequest(BaseModel):
    alert_rate: Optional[float] = None
    num_of_avg: Optional[int] = None
    task: str
    user_input: Optional[str] = None
    m_uid: str

@app.on_event("startup")
async def startup_event():
    global analysor
    analysor = Financial_report()

def convert_numpy_types(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    elif isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(i) for i in obj]
    return obj

@app.post("/analyze")
async def analyze_report(request: ReportRequest):
    try:
        global analysor
        if request.task == 'month_alert':
            alert_categories = analysor.generate_report(m_uid=request.m_uid,
                                                        alert_rate=request.alert_rate,
                                                        num_of_avg=request.num_of_avg,
                                                        task=request.task)
            conclusion = {c: analysor.generate_report(m_uid=request.m_uid, alert_cate=c, task='analysis_alert') for c in alert_categories}
            return {"conclusion": convert_numpy_types(conclusion)}
        elif request.task == 'reply_user':
            res = analysor.llm_response(request.m_uid, request.user_input)
            if len(res) == 3:
                return {"reply": convert_numpy_types(res[0]), "image_or_not": res[1], "image_data": convert_numpy_types(res[2])}
            else:
                return {"reply": convert_numpy_types(res[0]), "image_or_not": res[1]}
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
async def read_root():
    return {"message": "Hello World"}

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")