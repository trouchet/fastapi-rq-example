from fastapi import FastAPI, HTTPException, APIRouter, Response
from enum import Enum
from redis import Redis
from rq import Queue
from rq.job import Job
from pydantic import BaseModel
from datetime import datetime

from src.tasks import add, subtract, multiply, divide, increment

app = FastAPI(
    title="Task Queue API",
    description="API for managing task queues using Redis and RQ",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "tasks",
            "description": "Operations related to task management"
        },
        {
            "name": "queue",
            "description": "Operations related to queue management"
        }
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

redis_conn = Redis(host="redis", port=6379)
q = Queue(connection=redis_conn)

class Operation(str, Enum):
    add = "add"
    subtract = "subtract"
    multiply = "multiply"
    divide = "divide"
    increment = "increment"

operation_map = {
    Operation.add: add,
    Operation.subtract: subtract,
    Operation.multiply: multiply,
    Operation.divide: divide,
    Operation.increment: increment,
}

tasks_router = APIRouter(prefix="/tasks")

class OperationRequest(BaseModel):
    a: int
    b: int = 0
    operation: Operation = Operation.add

# ---------------------------------------------------------------
# Task management endpoints
# ----------------------------------------------------------------
@tasks_router.post("/enqueue")
def enqueue_task(request: OperationRequest, response: Response):
    task_func = operation_map.get(request.operation)
    if not task_func:
        raise HTTPException(status_code=400, detail="Invalid operation")
    # increment only needs one argument
    if request.operation == Operation.increment:
        job = q.enqueue(task_func, request.a)
    else:
        job = q.enqueue(task_func, request.a, request.b)
    job_id = job.get_id()
    location = f"/tasks/job/{job_id}"
    response.headers["Location"] = location
    return {
        "job_id": job_id,
        "status": "queued",
        "location": location,
        "poll_interval_seconds": 2
    }

@tasks_router.get("/job/{job_id}")
def get_job_status(job_id: str):
    """
    Get the status and result of a job by its ID.
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")
    status = job.get_status(refresh=True)
    result = None
    exc_string = None
    result_ttl = None
    finished_at = None

    # Try to get the latest result if available (RQ >= 1.12)
    try:
        latest_result = job.latest_result()
        if latest_result:
            if latest_result.type.name == "SUCCESSFUL":
                result = latest_result.return_value
            elif latest_result.type.name == "FAILED":
                exc_string = latest_result.exc_string
    except Exception:
        # Fallback for older RQ or if latest_result is not available
        result = job.return_value

    # Add result expiry info if available
    if hasattr(job, "result_ttl"):
        result_ttl = job.result_ttl
    if hasattr(job, "ended_at") and job.ended_at:
        finished_at = job.ended_at.isoformat() if isinstance(job.ended_at, datetime) else str(job.ended_at)

    return {
        "job_id": job.id,
        "status": status,
        "result": result,
        "exception": exc_string,
        "result_expires_in_seconds": result_ttl,
        "finished_at": finished_at,
        "poll_interval_seconds": 2
    }

@tasks_router.get("/job/{job_id}/history")
def get_job_history(job_id: str):
    """
    Get the execution history of a job (last 10 runs).
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")
    history = []
    try:
        for exec_result in job.results():
            history.append({
                "created_at": exec_result.created_at,
                "type": exec_result.type.name,
                "result": exec_result.return_value,
                "exception": exec_result.exc_string,
            })
    except Exception:
        # results() may not be available in older RQ
        pass
    return {"job_id": job.id, "history": history}


# ---------------------------------------------------------------
# Queue management endpoints
# ----------------------------------------------------------------
queue_router = APIRouter(prefix="/queue")

@queue_router.get("/count")
def queue_count():
    return {"count": q.count}

app.include_router(tasks_router, tags=["tasks"])
app.include_router(queue_router, tags=["queue"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Task Queue API. Use /tasks/enqueue to add tasks."}