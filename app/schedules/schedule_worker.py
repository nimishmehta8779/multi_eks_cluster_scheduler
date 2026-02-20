"""
Schedule worker.

Contains the logic for triggering scheduled operations, including
cluster discovery, filtering, state creation, and fan-out.
Uses Auto Scaling Groups instead of EKS managed node groups.
"""

import logging
import uuid
from typing import Optional

from config import get_assumed_role_session, get_settings
from discovery import discover_clusters
from operations.operation_router import fan_out_operation
from state.state_manager import StateManager

logger = logging.getLogger(__name__)


def trigger_schedule_operation(schedule: dict, action: str) -> dict:
    """
    Trigger an operation from a schedule.

    Args:
        schedule: Schedule configuration dict.
        action: 'stop' or 'start'.

    Returns:
        Dict with operation_id and clusters_queued.
    """
    schedule_id = schedule.get("schedule_id", "")
    target = schedule.get("target", {})
    target_type = target.get("type", "label_filter")

    logger.info(
        "Triggering scheduled operation",
        extra={
            "schedule_id": schedule_id,
            "action": action,
            "target_type": target_type,
        },
    )

    # Discover clusters based on target type
    if target_type == "label_filter":
        label_filter = target.get("label_filter", {})
        clusters = discover_clusters(label_filter)
    elif target_type == "explicit":
        explicit_clusters = target.get("clusters", [])
        clusters = _resolve_explicit_clusters(explicit_clusters)
    else:
        raise ValueError(f"Unknown target type: {target_type}")

    if not clusters:
        logger.warning(
            "No clusters matched schedule target",
            extra={"schedule_id": schedule_id, "action": action},
        )
        return {
            "operation_id": None,
            "clusters_queued": 0,
        }

    # Apply auto_stop filter for stop operations
    if action == "stop":
        clusters = [
            c for c in clusters
            if c.get("tags", {}).get("auto_stop") == "true"
        ]

        if not clusters:
            logger.warning(
                "No clusters with auto_stop=true after filtering",
                extra={"schedule_id": schedule_id},
            )
            return {
                "operation_id": None,
                "clusters_queued": 0,
            }

    # Populate target capacities for scale action
    if action == "scale":
        for cluster in clusters:
            for ng in cluster.get("node_groups", []):
                ng["target_desired"] = schedule.get("desired_capacity")
                ng["target_min"] = schedule.get("min_size")
                ng["target_max"] = schedule.get("max_size")

    # Create operation
    operation_id = str(uuid.uuid4())
    state_manager = StateManager()
    state_manager.create_operation(
        operation_id=operation_id,
        action=action,
        initiated_by=f"schedule:{schedule_id}",
        clusters=clusters,
        schedule_id=schedule_id,
    )

    # Fan out
    fan_out_result = fan_out_operation(
        operation_id=operation_id,
        action=action,
        clusters=clusters,
        initiated_by=f"schedule:{schedule_id}",
    )

    logger.info(
        "Scheduled operation triggered",
        extra={
            "schedule_id": schedule_id,
            "operation_id": operation_id,
            "action": action,
            "clusters_queued": fan_out_result["clusters_count"],
            "nodegroups_queued": fan_out_result["nodegroups_count"],
        },
    )

    return {
        "operation_id": str(operation_id),
        "clusters_queued": int(fan_out_result["clusters_count"]),
    }


def _resolve_explicit_clusters(cluster_refs: list[dict]) -> list[dict]:
    """
    Resolve explicit cluster references by describing them.

    For each cluster, discovers ASGs tagged with 'eks:cluster-name'
    instead of EKS managed node groups.

    Args:
        cluster_refs: List of dicts with account_id, region, cluster_name.

    Returns:
        List of fully described cluster dicts with ASG-backed node_groups.
    """
    from botocore.exceptions import ClientError

    clusters = []

    for ref in cluster_refs:
        account_id = ref.get("account_id", "")
        region = ref.get("region", "")
        cluster_name = ref.get("cluster_name", "")

        try:
            session = get_assumed_role_session(account_id)
            eks_client = session.client("eks", region_name=region)
            asg_client = session.client("autoscaling", region_name=region)

            # Describe the EKS cluster
            response = eks_client.describe_cluster(name=cluster_name)
            cluster = response["cluster"]

            # Discover Auto Scaling Groups for this cluster
            node_groups = []
            paginator = asg_client.get_paginator("describe_auto_scaling_groups")
            for page in paginator.paginate():
                for asg in page.get("AutoScalingGroups", []):
                    asg_tags = {
                        tag["Key"]: tag["Value"]
                        for tag in asg.get("Tags", [])
                    }

                    # Match by eks:cluster-name tag
                    tag_cluster = asg_tags.get("eks:cluster-name", "")
                    k8s_tag = f"kubernetes.io/cluster/{cluster_name}"
                    k8s_match = k8s_tag in asg_tags

                    if tag_cluster == cluster_name or k8s_match:
                        nodegroup_name = asg_tags.get(
                            "eks:nodegroup-name",
                            asg_tags.get("Name", asg["AutoScalingGroupName"]),
                        )

                        node_groups.append({
                            "name": nodegroup_name,
                            "asg_name": asg["AutoScalingGroupName"],
                            "status": "ACTIVE" if asg["DesiredCapacity"] > 0 else "STOPPED",
                            "desired_size": asg["DesiredCapacity"],
                            "min_size": asg["MinSize"],
                            "max_size": asg["MaxSize"],
                            "type": "asg",
                        })

            # Filter node groups if explicitly requested in the reference
            requested_names = [ng["name"] for ng in ref.get("node_groups", [])]
            if requested_names:
                node_groups = [
                    ng for ng in node_groups 
                    if ng["name"] in requested_names
                ]

            if not node_groups and requested_names:
                logger.warning(
                    "No matching node groups found for explicit filter",
                    extra={
                        "cluster_name": cluster_name,
                        "requested": requested_names
                    }
                )
                continue

            clusters.append({
                "account_id": account_id,
                "region": region,
                "cluster_name": cluster["name"],
                "cluster_arn": cluster["arn"],
                "cluster_status": cluster["status"],
                "kubernetes_version": cluster.get("version", "unknown"),
                "tags": cluster.get("tags", {}),
                "node_groups": node_groups,
            })

        except ClientError as e:
            logger.error(
                "Failed to resolve cluster",
                extra={
                    "account_id": account_id,
                    "cluster_name": cluster_name,
                    "error": str(e),
                },
            )

    return clusters
