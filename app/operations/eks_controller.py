"""
EKS Auto Scaling Group controller.

Handles stop and start operations on Auto Scaling Groups associated
with EKS clusters. Uses ASG UpdateAutoScalingGroup API with retry
logic for AWS API throttling.
"""

import logging
from typing import Optional

from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_assumed_role_session

logger = logging.getLogger(__name__)


class EKSController:
    """Controls EKS worker capacity via Auto Scaling Group operations."""

    @retry(
        retry=retry_if_exception_type(ClientError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        before_sleep=lambda retry_state: logger.warning(
            "Retrying ASG API call",
            extra={
                "attempt": retry_state.attempt_number,
                "wait": retry_state.next_action.sleep,
            },
        ),
    )
    def stop_nodegroup(
        self,
        account_id: str,
        region: str,
        cluster_name: str,
        nodegroup_name: str,
        asg_name: Optional[str] = None,
    ) -> dict:
        """
        Stop an Auto Scaling Group by scaling to zero.

        Sets MinSize=0, DesiredCapacity=0, keeping MaxSize unchanged.

        Args:
            account_id: AWS account ID.
            region: AWS region.
            cluster_name: EKS cluster name.
            nodegroup_name: Logical node group name.
            asg_name: AWS Auto Scaling Group name. If not provided,
                      discovers ASG by cluster tags.

        Returns:
            Dict with action result and sizing info.
        """
        session = get_assumed_role_session(account_id)
        asg_client = session.client("autoscaling", region_name=region)

        # Resolve ASG name if not provided
        if not asg_name:
            asg_name = self._find_asg_name(
                asg_client, cluster_name, nodegroup_name
            )
            if not asg_name:
                raise RuntimeError(
                    f"Cannot find ASG for cluster={cluster_name}, "
                    f"nodegroup={nodegroup_name}"
                )

        # Get current ASG state
        response = asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[asg_name]
        )
        if not response["AutoScalingGroups"]:
            raise RuntimeError(f"ASG {asg_name} not found")

        asg = response["AutoScalingGroups"][0]
        original_desired = asg["DesiredCapacity"]
        original_min = asg["MinSize"]
        original_max = asg["MaxSize"]

        if original_desired == 0 and original_min == 0:
            logger.info(
                "ASG already at zero, skipping",
                extra={
                    "account_id": account_id,
                    "cluster_name": cluster_name,
                    "asg_name": asg_name,
                },
            )
            return {
                "action": "SKIPPED",
                "reason": "already_at_zero",
                "original_desired": original_desired,
                "original_min": original_min,
                "original_max": original_max,
            }

        # Scale to zero
        asg_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=0,
            DesiredCapacity=0,
            MaxSize=original_max,
        )

        logger.info(
            "ASG stopped (scaled to zero)",
            extra={
                "account_id": account_id,
                "cluster_name": cluster_name,
                "asg_name": asg_name,
                "nodegroup_name": nodegroup_name,
                "original_desired": original_desired,
                "original_min": original_min,
            },
        )

        return {
            "action": "STOPPED",
            "original_desired": original_desired,
            "original_min": original_min,
            "original_max": original_max,
            "current_desired": 0,
        }

    @retry(
        retry=retry_if_exception_type(ClientError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        before_sleep=lambda retry_state: logger.warning(
            "Retrying ASG API call",
            extra={
                "attempt": retry_state.attempt_number,
                "wait": retry_state.next_action.sleep,
            },
        ),
    )
    def start_nodegroup(
        self,
        account_id: str,
        region: str,
        cluster_name: str,
        nodegroup_name: str,
        desired_size: int,
        min_size: int,
        max_size: int,
        asg_name: Optional[str] = None,
    ) -> dict:
        """
        Start an Auto Scaling Group by restoring to baseline sizes.

        Args:
            account_id: AWS account ID.
            region: AWS region.
            cluster_name: EKS cluster name.
            nodegroup_name: Logical node group name.
            desired_size: Target desired capacity.
            min_size: Target min size.
            max_size: Target max size.
            asg_name: AWS Auto Scaling Group name. If not provided,
                      discovers ASG by cluster tags.

        Returns:
            Dict with action result and sizing info.
        """
        session = get_assumed_role_session(account_id)
        asg_client = session.client("autoscaling", region_name=region)

        # Resolve ASG name if not provided
        if not asg_name:
            asg_name = self._find_asg_name(
                asg_client, cluster_name, nodegroup_name
            )
            if not asg_name:
                raise RuntimeError(
                    f"Cannot find ASG for cluster={cluster_name}, "
                    f"nodegroup={nodegroup_name}"
                )

        # Restore scaling configuration
        asg_client.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=min_size,
            DesiredCapacity=desired_size,
            MaxSize=max_size,
        )

        logger.info(
            "ASG started (restored to baseline)",
            extra={
                "account_id": account_id,
                "cluster_name": cluster_name,
                "asg_name": asg_name,
                "nodegroup_name": nodegroup_name,
                "desired_size": desired_size,
                "min_size": min_size,
                "max_size": max_size,
            },
        )

        return {
            "action": "STARTED",
            "desired_size": desired_size,
            "min_size": min_size,
            "max_size": max_size,
            "current_desired": desired_size,
        }
    @retry(
        retry=retry_if_exception_type(ClientError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60),
    )
    def scale_nodegroup(
        self,
        account_id: str,
        region: str,
        cluster_name: str,
        nodegroup_name: str,
        desired_size: Optional[int] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        asg_name: Optional[str] = None,
    ) -> dict:
        """
        Scale an Auto Scaling Group to specific sizes.
        """
        session = get_assumed_role_session(account_id)
        asg_client = session.client("autoscaling", region_name=region)

        if not asg_name:
            asg_name = self._find_asg_name(asg_client, cluster_name, nodegroup_name)
            if not asg_name:
                raise RuntimeError(f"ASG not found for {cluster_name}/{nodegroup_name}")

        # Build update params - only include what's provided
        kwargs = {"AutoScalingGroupName": asg_name}
        if min_size is not None:
            kwargs["MinSize"] = min_size
        if max_size is not None:
            kwargs["MaxSize"] = max_size
        if desired_size is not None:
            kwargs["DesiredCapacity"] = desired_size

        asg_client.update_auto_scaling_group(**kwargs)

        logger.info(
            "ASG scaled",
            extra={
                "asg_name": asg_name,
                "desired": desired_size,
                "min": min_size,
                "max": max_size,
            },
        )

        return {
            "action": "SCALED",
            "asg_name": asg_name,
            "desired_size": desired_size,
            "min_size": min_size,
            "max_size": max_size,
        }

    @staticmethod
    def _find_asg_name(
        asg_client,
        cluster_name: str,
        nodegroup_name: str,
    ) -> Optional[str]:
        """
        Find ASG name by matching cluster and nodegroup tags.

        Searches ASGs with tag 'eks:cluster-name' == cluster_name
        and optionally 'eks:nodegroup-name' == nodegroup_name.

        Falls back to matching 'kubernetes.io/cluster/<name>' tag.

        Args:
            asg_client: boto3 autoscaling client.
            cluster_name: EKS cluster name.
            nodegroup_name: Logical node group name.

        Returns:
            ASG name string or None if not found.
        """
        paginator = asg_client.get_paginator("describe_auto_scaling_groups")
        for page in paginator.paginate():
            for asg in page.get("AutoScalingGroups", []):
                asg_tags = {
                    tag["Key"]: tag["Value"]
                    for tag in asg.get("Tags", [])
                }

                # Primary match: eks:cluster-name tag
                tag_cluster = asg_tags.get("eks:cluster-name", "")
                if tag_cluster != cluster_name:
                    # Fallback: kubernetes.io/cluster/<name> tag
                    k8s_tag = f"kubernetes.io/cluster/{cluster_name}"
                    if k8s_tag not in asg_tags:
                        continue

                # Match nodegroup name if available
                tag_nodegroup = asg_tags.get("eks:nodegroup-name", "")
                if tag_nodegroup and tag_nodegroup == nodegroup_name:
                    return asg["AutoScalingGroupName"]

                # If no nodegroup tag, match by ASG name containing
                # the nodegroup name, or just return the first match
                if nodegroup_name in asg["AutoScalingGroupName"]:
                    return asg["AutoScalingGroupName"]

                # No specific nodegroup match, return first cluster match
                return asg["AutoScalingGroupName"]

        return None
