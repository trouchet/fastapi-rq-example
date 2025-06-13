# FastAPI + RQ + Docker Example

A minimal project demonstrating how to use FastAPI, RQ (Redis Queue), and Docker for background job processing.

## Project Structure

- `src/app.py` - FastAPI application with an endpoint to enqueue jobs.
- `src/tasks.py` - Background task(s) for RQ.
- `src/worker.py` - RQ worker process.
- `src/main.py` - Main FastAPI application (with all endpoints).
- `src/utils.py` - Utility functions for queue/job management.
- `tests/simulate_client.py` - Rich-powered script to test the API and poll job status.
- `docker-compose.yml` - Orchestrates FastAPI, Redis, RQ worker, and rq-dashboard.
- `.env` - Environment variables for configuration.

## Usage

### 1. Build and Start Services

```sh
docker-compose up --build
```

- FastAPI app: [http://localhost:8000](http://localhost:8000)
- RQ Dashboard: [http://localhost:9181](http://localhost:9181)

### 2. Enqueue a Job

You can use the provided test script (with rich UI):

```sh
python tests/simulate_client.py
```

Or manually with `curl` (example for addition):

```sh
curl -X POST "http://localhost:8000/tasks/enqueue" \
  -H "Content-Type: application/json" \
  -d '{"a": 2, "b": 3, "operation": "add"}'
```

### 3. Check Job Status

You can poll the job status using the API:

```sh
curl http://localhost:8000/tasks/job/<job_id>
```

Or visit [http://localhost:9181](http://localhost:9181) to view jobs and results in the dashboard.

## Customization

- Add more tasks to `src/tasks.py`.
- Add more endpoints to `src/main.py`.

## Cleanup

To stop and remove containers:

```sh
docker-compose down -v
```
