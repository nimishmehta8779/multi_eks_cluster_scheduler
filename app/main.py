"""
FastAPI application for the EKS Multi-Account Node Group Scheduler.

Provides REST endpoints for cluster discovery, stop/start operations,
and schedule management.
"""

import logging
import time
import traceback
import uuid
from typing import Optional

from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from config import get_settings
from discovery import discover_clusters
from json_logging import setup_json_logging
from operations.operation_router import fan_out_operation
from schedules.schedule_manager import ScheduleManager
from schedules.schedule_worker import trigger_schedule_operation
from state.state_manager import StateManager

# --- Structured Logging ---
setup_json_logging()
logger = logging.getLogger(__name__)


# --- App Setup ---
app = FastAPI(
    title="EKS Operator",
    description="Multi-Account EKS Node Group Scheduler",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global Exception Handlers ---

@app.exception_handler(ClientError)
async def aws_client_error_handler(request: Request, exc: ClientError):
    """Handle AWS SDK ClientError with structured response."""
    error_code = exc.response.get("Error", {}).get("Code", "Unknown")
    error_msg = exc.response.get("Error", {}).get("Message", str(exc))
    logger.error(
        "AWS ClientError",
        extra={"path": request.url.path, "error_code": error_code, "error": error_msg},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": f"AWS service error: {error_code}", "message": error_msg},
    )


@app.exception_handler(EndpointConnectionError)
async def aws_connection_error_handler(request: Request, exc: EndpointConnectionError):
    """Handle AWS endpoint connection errors."""
    logger.error(
        "AWS connection error",
        extra={"path": request.url.path, "error": str(exc)},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "AWS service unavailable", "message": str(exc)},
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    """Handle Pydantic configuration validation errors."""
    logger.error(
        "Configuration validation error",
        extra={"path": request.url.path, "error": str(exc)},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Configuration error", "message": str(exc)},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """Catch-all handler for unhandled exceptions."""
    logger.error(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "error": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal error: {type(exc).__name__}", "message": str(exc)},
    )


# --- Request/Response Models ---

class StopRequest(BaseModel):
    label_filter: Optional[dict[str, str]] = None
    initiated_by: str = "api"


class StartRequest(BaseModel):
    source_operation_id: str
    initiated_by: str = "api"


class ScheduleCreateRequest(BaseModel):
    name: str
    desired_capacity: Optional[int] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    recurrence: str  # Cron expression
    time_zone: str = "UTC"
    start_date: Optional[str] = None
    start_time: Optional[str] = None
    end_date: Optional[str] = None
    end_time: Optional[str] = None
    target: dict  # {account_id, region, cluster_name, nodegroup_name}


class ScheduleUpdateRequest(BaseModel):
    name: Optional[str] = None
    desired_capacity: Optional[int] = None
    min_size: Optional[int] = None
    max_size: Optional[int] = None
    recurrence: Optional[str] = None
    time_zone: Optional[str] = None
    start_date: Optional[str] = None
    start_time: Optional[str] = None
    end_date: Optional[str] = None
    end_time: Optional[str] = None
    enabled: Optional[bool] = None


class PauseRequest(BaseModel):
    until: Optional[str] = None


# --- Middleware ---

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID and timing to all responses."""
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    response = await call_next(request)

    duration_ms = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Duration-Ms"] = str(duration_ms)

    logger.info(
        "Request completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )

    return response


# --- Health ---

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}


# --- Discovery ---

@app.get("/clusters")
async def list_clusters(label_filter: Optional[str] = Query(None)):
    """
    Discover EKS clusters across all target accounts.

    Query params:
        label_filter: Comma-separated key=value pairs, e.g. env=dev,team=backend
    """
    parsed_filter = None
    if label_filter:
        try:
            parsed_filter = dict(
                pair.split("=", 1) for pair in label_filter.split(",")
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid label_filter format. Use key=value,key=value",
            )

    clusters = discover_clusters(parsed_filter)
    return {
        "clusters": clusters,
        "total": len(clusters),
        "total_nodegroups": sum(len(c.get("node_groups", [])) for c in clusters),
    }


# --- Operations ---

@app.post("/operation/stop")
async def stop_operation(request: StopRequest):
    """
    Stop EKS node groups matching the label filter.

    Only clusters with auto_stop=true tag are affected.
    Production clusters are automatically excluded.
    """
    clusters = discover_clusters(request.label_filter)

    # Filter for auto_stop clusters
    stoppable = [
        c for c in clusters
        if c.get("tags", {}).get("auto_stop") == "true"
    ]

    if not stoppable:
        raise HTTPException(
            status_code=404,
            detail="No clusters with auto_stop=true matched the filter",
        )

    operation_id = str(uuid.uuid4())
    state_manager = StateManager()
    state_manager.create_operation(
        operation_id=operation_id,
        action="stop",
        initiated_by=request.initiated_by,
        clusters=stoppable,
    )

    fan_out_result = fan_out_operation(
        operation_id=operation_id,
        action="stop",
        clusters=stoppable,
        initiated_by=request.initiated_by,
    )

    return {
        "operation_id": operation_id,
        "action": "stop",
        "clusters_queued": fan_out_result["clusters_count"],
        "nodegroups_queued": fan_out_result["nodegroups_count"],
    }


@app.post("/operation/start")
async def start_operation(request: StartRequest):
    """
    Start EKS node groups, restoring sizes from a previous stop operation.
    """
    state_manager = StateManager()
    source_op = state_manager.get_full_operation_summary(
        request.source_operation_id, include_detail=True
    )

    if not source_op:
        raise HTTPException(
            status_code=404,
            detail=f"Source operation {request.source_operation_id} not found",
        )

    if source_op.get("action") != "stop":
        raise HTTPException(
            status_code=400,
            detail="Source operation must be a stop operation",
        )

    # Rebuild cluster list from source operation
    clusters = []
    for cluster_detail in source_op.get("clusters", []):
        node_groups = [
            {"name": ng["name"]}
            for ng in cluster_detail.get("nodegroups", [])
        ]
        clusters.append({
            "account_id": cluster_detail["account_id"],
            "region": cluster_detail["region"],
            "cluster_name": cluster_detail["cluster_name"],
            "tags": {},
            "node_groups": node_groups,
        })

    operation_id = str(uuid.uuid4())
    state_manager.create_operation(
        operation_id=operation_id,
        action="start",
        initiated_by=request.initiated_by,
        clusters=clusters,
    )

    fan_out_result = fan_out_operation(
        operation_id=operation_id,
        action="start",
        clusters=clusters,
        initiated_by=request.initiated_by,
    )

    return {
        "operation_id": operation_id,
        "action": "start",
        "source_operation_id": request.source_operation_id,
        "clusters_queued": fan_out_result["clusters_count"],
        "nodegroups_queued": fan_out_result["nodegroups_count"],
    }


@app.get("/operations/latest")
async def get_latest_operations(limit: int = Query(5)):
    """Get the most recent operations."""
    state_manager = StateManager()
    # Scans are expensive but this is a small table for metadata
    # In production, we'd use a GSI on SK + created_at
    response = state_manager._table.scan(
        FilterExpression="SK = :sk",
        ExpressionAttributeValues={":sk": "META"},
    )
    items = response.get("Items", [])
    # Sort by created_at descending
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"operations": items[:limit]}


@app.get("/operation/{operation_id}")
async def get_operation(operation_id: str, detail: bool = Query(False)):
    """Get operation status and summary."""
    state_manager = StateManager()
    summary = state_manager.get_full_operation_summary(
        operation_id, include_detail=detail
    )

    if not summary:
        raise HTTPException(
            status_code=404,
            detail=f"Operation {operation_id} not found",
        )

    return summary


@app.get("/operation/{operation_id}/nodegroups")
async def get_operation_nodegroups(operation_id: str):
    """Get per-nodegroup details for an operation."""
    state_manager = StateManager()
    meta = state_manager.get_operation_meta(operation_id)

    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Operation {operation_id} not found",
        )

    clusters = state_manager.get_operation_clusters(operation_id)
    all_ngs = []

    for cluster in clusters:
        cluster_id = cluster.get("cluster_id", "")
        ngs = state_manager.get_cluster_nodegroups(operation_id, cluster_id)
        all_ngs.extend(ngs)

    return {
        "operation_id": operation_id,
        "nodegroups": all_ngs,
        "total": len(all_ngs),
    }


# --- Schedules ---

@app.post("/schedules")
async def create_schedule(request: ScheduleCreateRequest):
    """Create a new schedule."""
    schedule_manager = ScheduleManager()
    try:
        schedule = schedule_manager.create_schedule(request.model_dump())
        triggers = schedule_manager.get_next_triggers(
            schedule["schedule_id"]
        )
        schedule.update(triggers)
        return schedule
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/schedules")
async def list_schedules(
    enabled_only: bool = Query(False),
    cluster_name: Optional[str] = Query(None),
    node_group_name: Optional[str] = Query(None)
):
    """List all schedules with filtering support."""
    schedule_manager = ScheduleManager()
    schedules = schedule_manager.list_schedules(
        enabled_only=enabled_only,
        cluster_name=cluster_name,
        node_group_name=node_group_name
    )
    return {"schedules": schedules, "total": len(schedules)}


@app.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Get a schedule with next trigger times."""
    schedule_manager = ScheduleManager()
    schedule = schedule_manager.get_schedule(schedule_id)

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail=f"Schedule {schedule_id} not found",
        )

    triggers = schedule_manager.get_next_triggers(schedule_id)
    schedule.update(triggers)
    return schedule


@app.put("/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, request: ScheduleUpdateRequest):
    """Update a schedule."""
    schedule_manager = ScheduleManager()
    updates = {
        k: v for k, v in request.model_dump().items() if v is not None
    }

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = schedule_manager.update_schedule(schedule_id, updates)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete (disable) a schedule."""
    schedule_manager = ScheduleManager()
    schedule_manager.delete_schedule(schedule_id)
    return {"status": "deleted", "schedule_id": schedule_id}


@app.post("/schedules/{schedule_id}/trigger")
async def manual_trigger(schedule_id: str):
    """Manually trigger a schedule."""
    schedule_manager = ScheduleManager()
    schedule = schedule_manager.get_schedule(schedule_id)

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail=f"Schedule {schedule_id} not found",
        )

    # Simplified trigger: always use the stored capacities
    result = trigger_schedule_operation(schedule, action="scale")

    if result.get("operation_id"):
        schedule_manager.record_execution(
            schedule_id, "scale",
            result["operation_id"],
            result.get("clusters_queued", 0),
        )

    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder(result)


@app.post("/schedules/{schedule_id}/pause")
async def pause_schedule(schedule_id: str, request: PauseRequest):
    """Pause a schedule."""
    from datetime import datetime

    schedule_manager = ScheduleManager()
    until_dt = None
    if request.until:
        try:
            until_dt = datetime.fromisoformat(request.until)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid 'until' datetime format",
            )

    updated = schedule_manager.pause_schedule(schedule_id, until_dt)
    return updated


@app.get("/schedules/{schedule_id}/history")
async def get_schedule_history(
    schedule_id: str, limit: int = Query(20, ge=1, le=100)
):
    """Get schedule execution history."""
    schedule_manager = ScheduleManager()
    history = schedule_manager.get_schedule_history(schedule_id, limit=limit)
    return {"schedule_id": schedule_id, "history": history, "total": len(history)}
