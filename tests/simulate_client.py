import threading
import time

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn
from rich.progress import Progress
from rich.progress import SpinnerColumn
from rich.progress import TextColumn
from rich.progress import TimeElapsedColumn
from rich.table import Table

console = Console()

OPERATIONS = [
    ("add", 2, 3),
    ("subtract", 10, 4),
    ("multiply", 6, 7),
    ("divide", 8, 2),
    ("increment", 5, None),
]


def enqueue_and_poll(
    operation, a, b=None, output_list=None, idx=None, progress=None, task_id=None
):
    url = "http://localhost:8000/tasks/enqueue"
    payload = {"a": a, "operation": operation}
    if b is not None:
        payload["b"] = b

    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=10)
    except requests.exceptions.RequestException as e:
        if output_list is not None and idx is not None:
            output_list[idx] = {
                "rule": f"[bold blue]{operation.upper()}[/] [a={a}, b={b}]",
                "table": None,
                "panel": Panel.fit(f"[red][{operation}] Request failed: {e}[/red]"),
                "summary": (operation, "failed", "-", 0, f"{e}"),
            }
        if progress and task_id is not None:
            progress.advance(task_id)
        return

    try:
        resp_json = response.json()
    except Exception:
        if output_list is not None and idx is not None:
            output_list[idx] = {
                "rule": f"[bold blue]{operation.upper()}[/] [a={a}, b={b}]",
                "table": None,
                "panel": Panel.fit(
                    f"[red][{operation}] Invalid response: {response.text}[/red]"
                ),
                "summary": (operation, "failed", "-", 0, "Invalid response"),
            }
        if progress and task_id is not None:
            progress.advance(task_id)
        return

    job_id = resp_json.get("job_id")
    if not job_id:
        if output_list is not None and idx is not None:
            output_list[idx] = {
                "rule": f"[bold blue]{operation.upper()}[/] [a={a}, b={b}]",
                "table": None,
                "panel": Panel.fit(f"[red][{operation}] No job_id returned![/red]"),
                "summary": (operation, "failed", "-", 0, "No job_id returned"),
            }
        if progress and task_id is not None:
            progress.advance(task_id)
        return

    location = response.headers.get("Location")
    if location and not location.startswith("http"):
        api_url = f"http://localhost:8000{location}"
    else:
        api_url = location or f"http://localhost:8000/tasks/job/{job_id}"

    poll_interval = resp_json.get("poll_interval_seconds", 2)
    table = Table(title=f"Job {job_id} ({operation})", show_lines=True)
    table.add_column("Poll", style="cyan", justify="right")
    table.add_column("Status", style="magenta")
    table.add_column("Result", style="green")
    table.add_column("Exception", style="red")
    table.add_column("Finished At", style="yellow")
    table.add_column("Expires In (s)", style="blue")

    status = None
    result = exc = finished_at = expires_in = "-"
    duration = 0
    for i in range(1, 21):
        try:
            job_resp = requests.get(api_url, timeout=5)
            job_resp.raise_for_status()
            job_data = job_resp.json()
        except Exception as e:
            table.add_row(str(i), "[red]error[/red]", "-", str(e), "-", "-")
            time.sleep(poll_interval)
            continue
        status = job_data.get("status")
        result = str(job_data.get("result"))
        exc = str(job_data.get("exception")) if job_data.get("exception") else "-"
        finished_at = job_data.get("finished_at") or "-"
        expires_in = (
            str(job_data.get("result_expires_in_seconds"))
            if job_data.get("result_expires_in_seconds") is not None
            else "-"
        )
        table.add_row(str(i), status, result, exc, finished_at, expires_in)
        if status == "finished":
            duration = time.time() - start_time
            break
        elif status in ("failed", "stopped"):
            duration = time.time() - start_time
            break
        time.sleep(poll_interval)
    else:
        duration = time.time() - start_time

    if status == "finished":
        result_panel = Panel.fit(
            f"[bold green]{operation.upper()} result: {result}[/bold green]"
        )
        summary = (
            operation,
            "[green]finished[/green]",
            result,
            round(duration, 2),
            "-",
        )
    elif status in ("failed", "stopped"):
        result_panel = Panel.fit(
            f"[bold red]{operation.upper()} failed: {exc}[/bold red]"
        )
        summary = (operation, "[red]failed[/red]", "-", round(duration, 2), exc)
    else:
        result_panel = Panel.fit(
            f"[yellow]{operation.upper()} job did not finish in time.[/yellow]"
        )
        summary = (operation, "[yellow]timeout[/yellow]", "-", round(duration, 2), "-")
    if output_list is not None and idx is not None:
        output_list[idx] = {
            "rule": f"[bold blue]{operation.upper()}[/] [a={a}, b={b}]",
            "table": table,
            "panel": result_panel,
            "summary": summary,
        }
    if progress and task_id is not None:
        progress.advance(task_id)


def main():
    threads = []
    outputs = [None] * len(OPERATIONS)
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        # One progress bar for all tasks
        task_id = progress.add_task("Processing all jobs...", total=len(OPERATIONS))
        for idx, (op, a, b) in enumerate(OPERATIONS):
            t = threading.Thread(
                target=enqueue_and_poll,
                args=(op, a, b, outputs, idx, progress, task_id),
            )
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        # Ensure progress bar is complete
        progress.update(task_id, completed=len(OPERATIONS))
    # Print all outputs in order
    for out in outputs:
        console.rule(out["rule"])
        if out["table"]:
            console.print(out["table"])
        console.print(out["panel"])
    # Print summary table
    summary = Table(title="Summary", show_lines=True)
    summary.add_column("Operation", style="cyan")
    summary.add_column("Status")
    summary.add_column("Result", style="green")
    summary.add_column("Duration (s)", style="yellow")
    summary.add_column("Exception", style="red")
    for out in outputs:
        op, status, result, duration, exc = out["summary"]
        summary.add_row(op, status, result, str(duration), exc)
    console.rule("[bold magenta]All Jobs Summary[/bold magenta]")
    console.print(summary)


if __name__ == "__main__":
    main()
