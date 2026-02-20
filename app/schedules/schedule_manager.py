"""
Schedule CRUD manager.

Provides create, read, update, delete operations for schedules
stored in DynamoDB. Includes timezone awareness and override windows.
"""

import logging
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import get_settings
from schedules.cron_utils import validate_cron, get_next_trigger

logger = logging.getLogger(__name__)


class ScheduleManager:
    """Manages schedule CRUD operations in DynamoDB."""

    def __init__(self):
        settings = get_settings()
        self._dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self._table = self._dynamodb.Table(settings.dynamodb_schedules_table)

    def _convert_decimals(self, obj):
        """Recursively convert Decimals to int or float."""
        if isinstance(obj, list):
            return [self._convert_decimals(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: self._convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return obj

    def create_schedule(self, schedule_data: dict, created_by: str = "api") -> dict:
        """
        Create a new schedule.
        """
        schedule_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # Validate cron expression (recurrence)
        recurrence = schedule_data.get("recurrence")
        if not recurrence or not validate_cron(recurrence):
            raise ValueError(f"Invalid recurrence (cron): {recurrence}")

        # Enforce strict 1-to-1 Schedule-to-ASG mapping
        target = schedule_data.get("target", {})
        account_id = target.get("account_id")
        region = target.get("region")
        cluster_name = target.get("cluster_name")
        nodegroup_name = target.get("nodegroup_name")

        if not all([account_id, region, cluster_name, nodegroup_name]):
            raise ValueError("Target must include account_id, region, cluster_name, and nodegroup_name")

        nodegroup_id = f"{account_id}:{region}:{cluster_name}:{nodegroup_name}"

        # Check for existing mapping
        mapping_key = {"PK": f"ASG_MAP#{nodegroup_id}", "SK": "MAPPING"}
        response = self._table.get_item(Key=mapping_key)
        if response.get("Item"):
            existing_id = response["Item"]["schedule_id"]
            # Check if the schedule actually exists and is enabled
            existing_schedule = self.get_schedule(existing_id)
            if existing_schedule and existing_schedule.get("enabled") == "true":
                raise ValueError(f"ASG {nodegroup_id} already has an active schedule: {existing_id}")

        # Create schedule item
        item = {
            "PK": f"SCHEDULE#{schedule_id}",
            "SK": "CONFIG",
            "schedule_id": schedule_id,
            "nodegroup_id": nodegroup_id,
            "name": schedule_data["name"],
            "recurrence": recurrence,
            "desired_capacity": schedule_data.get("desired_capacity"),
            "min_size": schedule_data.get("min_size"),
            "max_size": schedule_data.get("max_size"),
            "time_zone": schedule_data.get("time_zone", "UTC"),
            "start_date": schedule_data.get("start_date"),
            "start_time": schedule_data.get("start_time"),
            "end_date": schedule_data.get("end_date"),
            "end_time": schedule_data.get("end_time"),
            "target": target,
            "enabled": "true",
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }

        # Save schedule and mapping
        self._table.put_item(Item=item)
        self._table.put_item(Item={
            "PK": f"ASG_MAP#{nodegroup_id}",
            "SK": "MAPPING",
            "schedule_id": schedule_id,
            "updated_at": now
        })

        logger.info(
            "Schedule created",
            extra={
                "schedule_id": schedule_id,
                "nodegroup_id": nodegroup_id,
                "schedule_name": schedule_data["name"],
            },
        )

        return item

    def get_schedule(self, schedule_id: str) -> Optional[dict]:
        """Get a schedule by ID."""
        response = self._table.get_item(
            Key={"PK": f"SCHEDULE#{schedule_id}", "SK": "CONFIG"}
        )
        return self._convert_decimals(response.get("Item"))

    def list_schedules(
        self, 
        enabled_only: bool = False,
        cluster_name: Optional[str] = None,
        node_group_name: Optional[str] = None
    ) -> list[dict]:
        """
        List all schedules with optional filtering.
        """
        if enabled_only:
            response = self._table.query(
                IndexName="enabled-schedules-index",
                KeyConditionExpression="#enabled = :enabled",
                ExpressionAttributeValues={":enabled": "true"},
                ExpressionAttributeNames={"#enabled": "enabled"}
            )
            items = response.get("Items", [])
        else:
            response = self._table.scan(
                FilterExpression="begins_with(PK, :prefix) AND SK = :sk",
                ExpressionAttributeValues={
                    ":prefix": "SCHEDULE#",
                    ":sk": "CONFIG",
                },
            )
            items = response.get("Items", [])

        if cluster_name or node_group_name:
            filtered = []
            for item in items:
                target = item.get("target", {})
                cn_match = not cluster_name or target.get("cluster_name") == cluster_name
                ng_match = not node_group_name or target.get("nodegroup_name") == node_group_name
                if cn_match and ng_match:
                    filtered.append(item)
            return filtered

        return self._convert_decimals(items)

    def update_schedule(self, schedule_id: str, updates: dict) -> dict:
        """
        Update a schedule.
        """
        if "recurrence" in updates and updates["recurrence"] and not validate_cron(updates["recurrence"]):
            raise ValueError(f"Invalid recurrence (cron): {updates['recurrence']}")

        now = datetime.now(timezone.utc).isoformat()
        update_parts = ["#updated_at = :now"]
        expr_values = {":now": now}
        expr_names = {"#updated_at": "updated_at"}

        # Map field names if they differ from model names
        field_map = {
            "name": "name",
            "desired_capacity": "desired_capacity",
            "min_size": "min_size",
            "max_size": "max_size",
            "recurrence": "recurrence",
            "time_zone": "time_zone",
            "start_date": "start_date",
            "start_time": "start_time",
            "end_date": "end_date",
            "end_time": "end_time"
        }

        for key, value in updates.items():
            attr_name = field_map.get(key, key)
            if key == "enabled":
                val = "true" if value else "false"
            else:
                val = value
            
            placeholder_name = f"#attr_{attr_name}"
            placeholder_value = f":val_{attr_name}"
            
            update_parts.append(f"{placeholder_name} = {placeholder_value}")
            expr_names[placeholder_name] = attr_name
            expr_values[placeholder_value] = val

        update_expr = "SET " + ", ".join(update_parts)

        response = self._table.update_item(
            Key={"PK": f"SCHEDULE#{schedule_id}", "SK": "CONFIG"},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names,
            ReturnValues="ALL_NEW",
        )
        return self._convert_decimals(response.get("Attributes", {}))

    def delete_schedule(self, schedule_id: str) -> None:
        """Soft-delete a schedule by disabling it."""
        self.update_schedule(schedule_id, {"enabled": False})

    def pause_schedule(
        self, schedule_id: str, until: Optional[datetime] = None
    ) -> dict:
        """
        Pause a schedule.
        """
        updates = {"enabled": False}
        if until:
            updates["paused_until"] = until.isoformat()

        return self.update_schedule(schedule_id, updates)

    def get_next_triggers(self, schedule_id: str) -> dict:
        """
        Get next trigger times for a schedule.
        """
        schedule = self.get_schedule(schedule_id)
        if not schedule or not schedule.get("recurrence"):
            return {}

        tz_name = schedule.get("time_zone", "UTC")
        next_trigger = get_next_trigger(schedule["recurrence"], tz_name)
        
        if next_trigger:
            return {"next_trigger": next_trigger.isoformat()}
        return {}

    def get_schedule_history(
        self, schedule_id: str, limit: int = 20
    ) -> list[dict]:
        """
        Get execution history for a schedule.
        """
        response = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": f"SCHEDULE#{schedule_id}",
                ":prefix": "EXEC#",
            },
            ScanIndexForward=False,
            Limit=limit,
        )
        return self._convert_decimals(response.get("Items", []))

    def record_execution(
        self,
        schedule_id: str,
        action: str,
        operation_id: str,
        clusters_count: int,
    ) -> None:
        """
        Record a schedule execution in history.
        """
        now = datetime.now(timezone.utc).isoformat()
        ttl = int(datetime.now(timezone.utc).timestamp()) + (90 * 86400)  # 90 days

        self._table.put_item(
            Item={
                "PK": f"SCHEDULE#{schedule_id}",
                "SK": f"EXEC#{now}",
                "schedule_id": schedule_id,
                "action": action,
                "operation_id": operation_id,
                "clusters_count": clusters_count,
                "executed_at": now,
                "ttl": ttl,
            }
        )
