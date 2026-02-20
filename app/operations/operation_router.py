"""
Operation router for SNS fan-out.

Publishes one SNS message per ASG (node group) for parallel processing
by the Lambda worker.
"""

import json
import logging

import boto3

from config import get_settings

logger = logging.getLogger(__name__)


def fan_out_operation(
    operation_id: str,
    action: str,
    clusters: list[dict],
    initiated_by: str,
) -> dict:
    """
    Publish SNS messages for each ASG/nodegroup in the operation.

    Args:
        operation_id: Operation identifier.
        action: 'stop' or 'start'.
        clusters: List of cluster dicts with node_groups (ASG-backed).
        initiated_by: Who initiated the operation.

    Returns:
        Dict with counts of clusters and nodegroups published.
    """
    settings = get_settings()
    sns_client = boto3.client("sns", region_name=settings.aws_region)

    clusters_count = 0
    nodegroups_count = 0

    for cluster in clusters:
        cluster_id = f"{cluster['account_id']}:{cluster['region']}:{cluster['cluster_name']}"
        clusters_count += 1

        for ng in cluster.get("node_groups", []):
            message = {
                "operation_id": operation_id,
                "action": action,
                "account_id": cluster["account_id"],
                "region": cluster["region"],
                "cluster_name": cluster["cluster_name"],
                "cluster_id": cluster_id,
                "nodegroup_name": ng["name"],
                "nodegroup_id": f"{cluster_id}:{ng['name']}",
                "asg_name": ng.get("asg_name", ""),
                "original_desired": int(ng.get("desired_size", 0)),
                "original_min": int(ng.get("min_size", 0)),
                "original_max": int(ng.get("max_size", 0)),
                "initiated_by": initiated_by,
                "node_type": ng.get("type", "asg"),
                "target_desired": int(ng.get("target_desired")) if ng.get("target_desired") is not None else None,
                "target_min": int(ng.get("target_min")) if ng.get("target_min") is not None else None,
                "target_max": int(ng.get("target_max")) if ng.get("target_max") is not None else None,
            }

            # 2. Publish to SNS (Workers subscribe to this topic via SQS)
            sns_client.publish(
                TopicArn=settings.sns_topic_arn,
                Message=json.dumps(message, default=str),
                MessageAttributes={
                    "action": {
                        "DataType": "String",
                        "StringValue": str(action),
                    },
                    "account_id": {
                        "DataType": "String",
                        "StringValue": str(cluster["account_id"]),
                    },
                },
            )

            nodegroups_count += 1

    logger.info(
        "Fan-out complete",
        extra={
            "operation_id": operation_id,
            "action": action,
            "clusters_count": clusters_count,
            "nodegroups_count": nodegroups_count,
        },
    )

    return {
        "clusters_count": clusters_count,
        "nodegroups_count": nodegroups_count,
    }
