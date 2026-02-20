"""
Task worker for EKS operations.

Handles fan-out tasks from SQS, processing individual cluster/nodegroup operations.
Currently supports 'stop' and 'start' actions by setting ASG desired capacity.
"""

import json
import logging
from typing import Any

from discovery import discover_clusters
from operations.eks_controller import EKSController
from state.cluster_baseline import ClusterBaseline
from state.state_manager import StateManager

# Setup structured logging
from json_logging import setup_json_logging
setup_json_logging()
logger = logging.getLogger(__name__)


def _process_message(
    message: dict[str, Any],
    controller: EKSController,
    baseline: ClusterBaseline,
    state_manager: StateManager,
) -> None:
    """
    Process a single operation message.
    """
    operation_id = message.get("operation_id")
    action = message.get("action")
    cluster_name = message.get("cluster_name")
    account_id = message.get("account_id")
    region = message.get("region")
    
    if not all([operation_id, action, cluster_name, account_id, region]):
        logger.error("Missing required fields in message", extra={"message": message})
        return

    cluster_id = f"{account_id}:{region}:{cluster_name}"

    logger.info(
        f"Processing operation",
        extra={
            "operation_id": operation_id,
            "action": action,
            "cluster_id": cluster_id,
        }
    )

    try:
        # Resolve target ASGs
        target_cluster = None
        discovered = discover_clusters()
        for c in discovered:
            if c["cluster_name"] == cluster_name and c["region"] == region and str(c["account_id"]) == str(account_id):
                target_cluster = c
                break
        
        if not target_cluster:
            logger.error(f"Cluster {cluster_name} not found during processing in account {account_id}")
            return

        # Filter node groups if specified in the message
        target_ng_names = []
        if "nodegroup_name" in message:
            target_ng_names = [message["nodegroup_name"]]
        elif "node_groups" in message:
            target_ng_names = [ng["name"] for ng in message.get("node_groups", [])]
        
        for ng in target_cluster.get("node_groups", []):
            if target_ng_names and ng["name"] not in target_ng_names:
                continue

            ng_id = f"{cluster_id}:{ng['name']}"
            
            try:
                if action == "stop":
                    # capture baseline before stopping
                    baseline.save_baseline(
                        cluster_id=cluster_id,
                        nodegroup_name=ng["name"],
                        desired_size=ng["desired_size"],
                        min_size=ng["min_size"],
                        max_size=ng["max_size"]
                    )
                    
                    # scale to 0
                    controller.stop_nodegroup(
                        account_id=account_id,
                        region=region,
                        cluster_name=cluster_name,
                        nodegroup_name=ng["name"],
                        asg_name=ng.get("asg_name")
                    )
                    
                    state_manager.update_nodegroup_status(
                        operation_id=operation_id,
                        ng_id=ng_id,
                        status="COMPLETED",
                        current_desired=0
                    )

                elif action == "start":
                    # retrieve baseline
                    saved = baseline.get_baseline(
                        cluster_id=cluster_id,
                        nodegroup_name=ng["name"]
                    )
                    
                    if not saved:
                        logger.warning(f"No baseline found for {ng_id}, using current min_size")
                        target_size = ng["min_size"]
                        min_size = ng["min_size"]
                        max_size = ng["max_size"]
                    else:
                        target_size = int(saved["desired_size"])
                        min_size = int(saved["min_size"])
                        max_size = int(saved["max_size"])
                    
                    controller.start_nodegroup(
                        account_id=account_id,
                        region=region,
                        cluster_name=cluster_name,
                        nodegroup_name=ng["name"],
                        desired_size=target_size,
                        min_size=min_size,
                        max_size=max_size,
                        asg_name=ng.get("asg_name")
                    )
                    
                    state_manager.update_nodegroup_status(
                        operation_id=operation_id,
                        ng_id=ng_id,
                        status="COMPLETED",
                        current_desired=target_size
                    )
                    
                    # Cleanup baseline after successful start
                    baseline.delete_baseline(cluster_id, ng["name"])

                elif action == "scale":
                    # Directly apply specified capacities
                    target_desired = message.get("target_desired")
                    target_min = message.get("target_min")
                    target_max = message.get("target_max")

                    controller.scale_nodegroup(
                        account_id=account_id,
                        region=region,
                        cluster_name=cluster_name,
                        nodegroup_name=ng["name"],
                        desired_size=target_desired,
                        min_size=target_min,
                        max_size=target_max,
                        asg_name=ng.get("asg_name")
                    )

                    state_manager.update_nodegroup_status(
                        operation_id=operation_id,
                        ng_id=ng_id,
                        status="COMPLETED",
                        current_desired=target_desired
                    )

            except Exception as e:
                logger.error(
                    "Failed to execute action on nodegroup",
                    extra={
                        "nodegroup": ng["name"],
                        "error": str(e)
                    },
                    exc_info=True
                )
                state_manager.update_nodegroup_status(
                    operation_id=operation_id,
                    ng_id=ng_id,
                    status="FAILED",
                    error_message=str(e)
                )

    except Exception as e:
        logger.error("Fatal error in worker", exc_info=True)
        raise e


def handler(event, context):
    """
    SQS Lambda Handler.
    """
    # Check for warm-up event
    if event.get("warm"):
        logger.info("Worker warmed up")
        return {"status": "warmed"}

    controller = EKSController()
    baseline = ClusterBaseline()
    state_manager = StateManager()

    logger.info(f"Received event with {len(event.get('Records', []))} records")
    
    batch_item_failures = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            if "Message" in body:
                message = json.loads(body["Message"])
            else:
                message = body

            _process_message(message, controller, baseline, state_manager)

        except Exception as e:
            logger.error(
                "Failed to process record",
                extra={
                    "record_id": record.get("messageId", "unknown"),
                    "error": str(e),
                },
                exc_info=True
            )
            batch_item_failures.append(
                {"itemIdentifier": record["messageId"]}
            )

    return {"batchItemFailures": batch_item_failures}
