"""
State manager for EKS operations.

Tracks operations at META, CLUSTER, and NG granularities in DynamoDB.
Includes status derivation logic and idempotency lock implementation.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import get_settings

logger = logging.getLogger(__name__)


class StateManager:
    """Manages operation state in DynamoDB."""

    def __init__(self):
        settings = get_settings()
        self._dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self._table = self._dynamodb.Table(settings.dynamodb_operations_table)

    def create_operation(
        self,
        operation_id: str,
        action: str,
        initiated_by: str,
        clusters: list[dict],
        schedule_id: Optional[str] = None,
    ) -> dict:
        """
        Create a new operation with META + CLUSTER + NG items.

        Args:
            operation_id: Unique operation identifier.
            action: 'stop' or 'start'.
            initiated_by: Who initiated the operation.
            clusters: List of cluster dicts with node_groups.
            schedule_id: Optional schedule ID if triggered by schedule.

        Returns:
            META item dict.
        """
        now = datetime.now(timezone.utc).isoformat()
        expires_at = int(time.time()) + (30 * 86400)  # 30 days TTL

        total_clusters = len(clusters)
        total_ngs = sum(len(c.get("node_groups", [])) for c in clusters)

        meta_item = {
            "PK": f"OP#{operation_id}",
            "SK": "META",
            "operation_id": operation_id,
            "action": action,
            "status": "IN_PROGRESS",
            "initiated_by": initiated_by,
            "total_clusters": total_clusters,
            "total_nodegroups": total_ngs,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
        }

        if schedule_id:
            meta_item["schedule_id"] = schedule_id

        items = [meta_item]

        for cluster in clusters:
            cluster_id = f"{cluster['account_id']}:{cluster['region']}:{cluster['cluster_name']}"
            cluster_item = {
                "PK": f"OP#{operation_id}",
                "SK": f"CLUSTER#{cluster_id}",
                "cluster_id": cluster_id,
                "account_id": cluster["account_id"],
                "region": cluster["region"],
                "cluster_name": cluster["cluster_name"],
                "status": "PENDING",
                "total_nodegroups": len(cluster.get("node_groups", [])),
                "created_at": now,
                "updated_at": now,
                "expires_at": expires_at,
            }
            items.append(cluster_item)

            for ng in cluster.get("node_groups", []):
                ng_id = f"{cluster_id}:{ng['name']}"
                ng_item = {
                    "PK": f"OP#{operation_id}",
                    "SK": f"NG#{ng_id}",
                    "nodegroup_id": ng_id,
                    "cluster_id": cluster_id,
                    "account_id": cluster["account_id"],
                    "region": cluster["region"],
                    "cluster_name": cluster["cluster_name"],
                    "nodegroup_name": ng["name"],
                    "action": action,
                    "status": "PENDING",
                    "original_desired": ng.get("desired_size", 0),
                    "original_min": ng.get("min_size", 0),
                    "original_max": ng.get("max_size", 0),
                    "current_desired": ng.get("desired_size", 0),
                    "retry_count": 0,
                    "created_at": now,
                    "updated_at": now,
                    "expires_at": expires_at,
                }
                items.append(ng_item)

        # Batch write all items
        with self._table.batch_writer() as batch:
            for item in items:
                batch.put_item(Item=item)

        logger.info(
            "Operation created",
            extra={
                "operation_id": operation_id,
                "action": action,
                "clusters": total_clusters,
                "nodegroups": total_ngs,
            },
        )

        return meta_item

    def update_nodegroup_status(
        self,
        operation_id: str,
        ng_id: str,
        status: str,
        error_message: Optional[str] = None,
        current_desired: Optional[int] = None,
    ) -> None:
        """
        Update nodegroup status and propagate to cluster/meta.

        Args:
            operation_id: Operation identifier.
            ng_id: Nodegroup identifier.
            status: New status string.
            error_message: Optional error message.
            current_desired: Optional updated desired size.
        """
        now = datetime.now(timezone.utc).isoformat()

        update_expr = "SET #status = :status, updated_at = :now"
        expr_values = {":status": status, ":now": now}
        expr_names = {"#status": "status"}

        if error_message:
            update_expr += ", error_message = :error"
            expr_values[":error"] = error_message

        if current_desired is not None:
            update_expr += ", current_desired = :desired"
            expr_values[":desired"] = current_desired

        if status == "FAILED":
            update_expr += ", retry_count = retry_count + :one"
            expr_values[":one"] = 1

        self._table.update_item(
            Key={"PK": f"OP#{operation_id}", "SK": f"NG#{ng_id}"},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

        # Derive and propagate cluster + meta statuses
        cluster_id = ":".join(ng_id.split(":")[:3])
        self._update_cluster_status(operation_id, cluster_id)
        self._update_meta_status(operation_id)

    def _update_cluster_status(self, operation_id: str, cluster_id: str) -> None:
        """Derive cluster status from its nodegroup statuses."""
        ngs = self.get_cluster_nodegroups(operation_id, cluster_id)
        derived_status = self._derive_status([ng.get("status", "") for ng in ngs])

        self._table.update_item(
            Key={"PK": f"OP#{operation_id}", "SK": f"CLUSTER#{cluster_id}"},
            UpdateExpression="SET #status = :status, updated_at = :now",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": derived_status,
                ":now": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _update_meta_status(self, operation_id: str) -> None:
        """Derive meta status from cluster statuses."""
        clusters = self.get_operation_clusters(operation_id)
        derived_status = self._derive_status([c.get("status", "") for c in clusters])

        self._table.update_item(
            Key={"PK": f"OP#{operation_id}", "SK": "META"},
            UpdateExpression="SET #status = :status, updated_at = :now",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": derived_status,
                ":now": datetime.now(timezone.utc).isoformat(),
            },
        )

    @staticmethod
    def _derive_status(statuses: list[str]) -> str:
        """
        Derive aggregate status from a list of child statuses.

        Rules:
            - All COMPLETED -> COMPLETED
            - Any IN_PROGRESS or PENDING with some done -> IN_PROGRESS
            - All FAILED -> FAILED
            - Mix of COMPLETED and FAILED -> PARTIAL_FAILURE
            - Any PENDING remaining -> IN_PROGRESS
        """
        status_set = set(statuses)

        if not status_set:
            return "UNKNOWN"

        if status_set == {"COMPLETED"}:
            return "COMPLETED"

        if status_set == {"FAILED"}:
            return "FAILED"

        if "PENDING" in status_set or "IN_PROGRESS" in status_set:
            return "IN_PROGRESS"

        if "COMPLETED" in status_set and "FAILED" in status_set:
            return "PARTIAL_FAILURE"

        return "IN_PROGRESS"

    def get_operation_meta(self, operation_id: str) -> Optional[dict]:
        """Get operation META item."""
        response = self._table.get_item(
            Key={"PK": f"OP#{operation_id}", "SK": "META"}
        )
        return response.get("Item")

    def get_operation_clusters(self, operation_id: str) -> list[dict]:
        """Get all cluster items for an operation."""
        response = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"OP#{operation_id}",
                ":prefix": "CLUSTER#",
            },
        )
        return response.get("Items", [])

    def get_cluster_nodegroups(self, operation_id: str, cluster_id: str) -> list[dict]:
        """Get all nodegroup items for a cluster in an operation."""
        response = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"OP#{operation_id}",
                ":prefix": f"NG#{cluster_id}:",
            },
        )
        return response.get("Items", [])

    def get_full_operation_summary(
        self, operation_id: str, include_detail: bool = False
    ) -> Optional[dict]:
        """
        Get complete operation summary.

        Args:
            operation_id: Operation identifier.
            include_detail: Include per-cluster and per-nodegroup details.

        Returns:
            Summary dict or None if operation not found.
        """
        meta = self.get_operation_meta(operation_id)
        if not meta:
            return None

        summary = {
            "operation_id": operation_id,
            "action": meta.get("action"),
            "status": meta.get("status"),
            "initiated_by": meta.get("initiated_by"),
            "total_clusters": int(meta.get("total_clusters", 0)),
            "total_nodegroups": int(meta.get("total_nodegroups", 0)),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "schedule_id": meta.get("schedule_id"),
        }

        if include_detail:
            clusters = self.get_operation_clusters(operation_id)
            cluster_details = []

            for cluster in clusters:
                cluster_id = cluster.get("cluster_id", "")
                ngs = self.get_cluster_nodegroups(operation_id, cluster_id)
                cluster_details.append({
                    "cluster_id": cluster_id,
                    "cluster_name": cluster.get("cluster_name", ""),
                    "account_id": cluster.get("account_id", ""),
                    "region": cluster.get("region", ""),
                    "status": cluster.get("status", ""),
                    "nodegroups": [
                        {
                            "name": ng.get("nodegroup_name", ""),
                            "status": ng.get("status", ""),
                            "error": ng.get("error_message"),
                        }
                        for ng in ngs
                    ],
                })

            summary["clusters"] = cluster_details

        return summary

    def acquire_idempotency_lock(
        self, lock_key: str, ttl_seconds: int = 120
    ) -> bool:
        """
        Acquire an idempotency lock in DynamoDB.

        Args:
            lock_key: Unique lock identifier.
            ttl_seconds: Lock TTL in seconds.

        Returns:
            True if lock acquired, False if already held.
        """
        now = int(time.time())
        expires = now + ttl_seconds

        try:
            self._table.put_item(
                Item={
                    "PK": f"LOCK#{lock_key}",
                    "SK": "LOCK",
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": expires,
                },
                ConditionExpression="attribute_not_exists(PK) OR expires_at < :now",
                ExpressionAttributeValues={":now": now},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
