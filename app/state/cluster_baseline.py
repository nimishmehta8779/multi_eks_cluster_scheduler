"""
Cluster baseline persistence.

Persists nodegroup baseline sizes before stop operations.
Protects original values with optimistic locking.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import get_settings

logger = logging.getLogger(__name__)


class ClusterBaseline:
    """Manages nodegroup baseline sizes in DynamoDB."""

    def __init__(self):
        settings = get_settings()
        self._dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self._table = self._dynamodb.Table(settings.dynamodb_cluster_state_table)

    def save_baseline(
        self,
        cluster_id: str,
        nodegroup_name: str,
        desired_size: int,
        min_size: int,
        max_size: int,
    ) -> bool:
        """
        Save nodegroup baseline sizes if not already saved.

        Uses conditional write to prevent overwriting existing baselines.
        This protects against a stop operation overwriting the original
        sizes if the nodegroup is already stopped.

        Args:
            cluster_id: Cluster identifier (account:region:name).
            nodegroup_name: Node group name.
            desired_size: Original desired size.
            min_size: Original min size.
            max_size: Original max size.

        Returns:
            True if saved, False if baseline already exists.
        """
        now = datetime.now(timezone.utc).isoformat()

        try:
            self._table.put_item(
                Item={
                    "cluster_id": cluster_id,
                    "nodegroup_name": nodegroup_name,
                    "desired_size": desired_size,
                    "min_size": min_size,
                    "max_size": max_size,
                    "saved_at": now,
                    "version": 1,
                },
                ConditionExpression="attribute_not_exists(cluster_id)",
            )

            logger.info(
                "Baseline saved",
                extra={
                    "cluster_id": cluster_id,
                    "nodegroup_name": nodegroup_name,
                    "desired_size": desired_size,
                    "min_size": min_size,
                    "max_size": max_size,
                },
            )
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(
                    "Baseline already exists, skipping overwrite",
                    extra={
                        "cluster_id": cluster_id,
                        "nodegroup_name": nodegroup_name,
                    },
                )
                return False
            raise

    def get_baseline(
        self, cluster_id: str, nodegroup_name: str
    ) -> Optional[dict]:
        """
        Get saved baseline for a nodegroup.

        Args:
            cluster_id: Cluster identifier.
            nodegroup_name: Node group name.

        Returns:
            Baseline dict or None if not found.
        """
        response = self._table.get_item(
            Key={
                "cluster_id": cluster_id,
                "nodegroup_name": nodegroup_name,
            }
        )
        return response.get("Item")

    def delete_baseline(
        self, cluster_id: str, nodegroup_name: str
    ) -> None:
        """
        Delete a baseline after successful start operation.

        Args:
            cluster_id: Cluster identifier.
            nodegroup_name: Node group name.
        """
        try:
            self._table.delete_item(
                Key={
                    "cluster_id": cluster_id,
                    "nodegroup_name": nodegroup_name,
                }
            )
            logger.info(
                "Baseline deleted",
                extra={
                    "cluster_id": cluster_id,
                    "nodegroup_name": nodegroup_name,
                },
            )
        except ClientError as e:
            logger.error(
                "Failed to delete baseline",
                extra={
                    "cluster_id": cluster_id,
                    "nodegroup_name": nodegroup_name,
                    "error": str(e),
                },
            )

    def get_cluster_baselines(self, cluster_id: str) -> list[dict]:
        """
        Get all baselines for a cluster.

        Args:
            cluster_id: Cluster identifier.

        Returns:
            List of baseline dicts.
        """
        response = self._table.query(
            KeyConditionExpression="cluster_id = :cid",
            ExpressionAttributeValues={":cid": cluster_id},
        )
        return response.get("Items", [])
