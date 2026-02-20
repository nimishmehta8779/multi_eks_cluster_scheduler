"""
Multi-account EKS cluster and Auto Scaling Group discovery.

Discovers EKS clusters across target accounts using parallel execution.
Discovers ASGs tagged with 'eks:cluster-name' for self-managed node groups.
Includes safety filters (blocking prod) and label-based filtering.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from config import get_settings, get_assumed_role_session

logger = logging.getLogger(__name__)


def discover_all_resources(label_filter: Optional[dict[str, str]] = None) -> dict:
    """
    Discover all resources across target accounts and regions.
    
    Includes EKS clusters and associated ASGs.
    """
    settings = get_settings()
    account_ids = _resolve_account_ids(settings)
    regions = settings.parsed_target_regions

    logger.info(
        "Starting multi-region EKS discovery",
        extra={
            "account_count": len(account_ids),
            "regions": regions,
            "label_filter": label_filter,
        },
    )

    results = {
        "clusters": [],
    }

    with ThreadPoolExecutor(max_workers=settings.max_discovery_workers) as executor:
        futures = []
        for account_id in account_ids:
            for region in regions:
                futures.append(executor.submit(
                    _discover_account_clusters, account_id, region, label_filter
                ))

        for future in as_completed(futures):
            try:
                clusters = future.result()
                results["clusters"].extend(clusters)
            except Exception as e:
                logger.error("Discovery task failed", extra={"error": str(e)})

    return results


def discover_clusters(label_filter: Optional[dict[str, str]] = None) -> list[dict]:
    """Backward compatibility wrapper."""
    return discover_all_resources(label_filter)["clusters"]


def _resolve_account_ids(settings) -> list[str]:
    """
    Resolve target account IDs from settings or Organizations.

    If target_account_ids is set, use those.
    Otherwise, list all accounts in the Organization.

    Args:
        settings: Application settings.

    Returns:
        List of AWS account IDs.
    """
    if settings.parsed_target_account_ids:
        logger.info(
            "Using explicit target accounts",
            extra={"count": len(settings.parsed_target_account_ids)},
        )
        return settings.parsed_target_account_ids

    try:
        org_client = boto3.client("organizations", region_name=settings.aws_region)
        paginator = org_client.get_paginator("list_accounts")
        account_ids = []

        for page in paginator.paginate():
            for account in page["Accounts"]:
                if account["Status"] == "ACTIVE" and account["Id"] != settings.management_account_id:
                    account_ids.append(account["Id"])

        logger.info(
            "Discovered accounts from Organizations",
            extra={"count": len(account_ids)},
        )
        return account_ids

    except ClientError as e:
        logger.error(
            "Failed to list accounts from Organizations",
            extra={"error": str(e)},
        )
        return []


def _discover_account_clusters(
    account_id: str,
    region: str,
    label_filter: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    Discover EKS clusters in a single account.

    For each cluster, discovers Auto Scaling Groups tagged with
    'eks:cluster-name' = <cluster_name>.

    Args:
        account_id: AWS account ID.
        region: AWS region to scan.
        label_filter: Optional tag filter.

    Returns:
        List of cluster dicts passing all filters.
    """
    try:
        session = get_assumed_role_session(account_id, region_name=region)
        eks_client = session.client("eks", region_name=region)

        cluster_names = []
        paginator = eks_client.get_paginator("list_clusters")
        for page in paginator.paginate():
            cluster_names.extend(page.get("clusters", []))

        clusters = []
        for cluster_name in cluster_names:
            cluster = _describe_cluster(eks_client, account_id, region, cluster_name)
            if cluster is None:
                continue

            # Safety filter: skip production clusters
            tags = cluster.get("tags", {})
            
            # Case-insensitive environment tag check
            env_key = next((k for k in tags if k.lower() in ("env", "environment")), None)
            env_tag = tags.get(env_key, "").lower() if env_key else ""
            
            if env_tag in ("prod", "production"):
                logger.warning(
                    "Skipping production cluster",
                    extra={
                        "account_id": account_id,
                        "cluster_name": cluster_name,
                        "env_tag": env_tag,
                    },
                )
                continue

            # Label filter
            if label_filter and not _matches_labels(tags, label_filter):
                continue

            # Discover Auto Scaling Groups for this cluster
            asgs = _discover_auto_scaling_groups(session, account_id, region, cluster_name)
            cluster["auto_scaling_groups"] = asgs

            # Keep backward compatibility — expose ASGs under node_groups key too
            cluster["node_groups"] = [
                {
                    "name": asg["name"],
                    "asg_name": asg["asg_name"],
                    "status": asg["status"],
                    "desired_size": asg["desired_capacity"],
                    "min_size": asg["min_size"],
                    "max_size": asg["max_size"],
                    "instance_types": asg.get("instance_types", []),
                    "capacity_type": asg.get("capacity_type", "ON_DEMAND"),
                    "tags": asg.get("tags", {}),
                    "type": "asg",
                }
                for asg in asgs
            ]

            clusters.append(cluster)

        return clusters

    except Exception as e:
        logger.error(
            "Failed to discover clusters in account",
            extra={
                "account_id": account_id,
                "region": region,
                "error": str(e),
            },
        )
        raise


def _describe_cluster(
    eks_client,
    account_id: str,
    region: str,
    cluster_name: str,
) -> Optional[dict]:
    """
    Describe a single EKS cluster.

    Args:
        eks_client: boto3 EKS client.
        account_id: AWS account ID.
        region: AWS region.
        cluster_name: EKS cluster name.

    Returns:
        Cluster dict or None if describe fails.
    """
    try:
        response = eks_client.describe_cluster(name=cluster_name)
        cluster = response["cluster"]
        return {
            "account_id": account_id,
            "region": region,
            "cluster_name": cluster["name"],
            "cluster_arn": cluster["arn"],
            "cluster_status": cluster["status"],
            "kubernetes_version": cluster.get("version", "unknown"),
            "tags": cluster.get("tags", {}),
        }
    except ClientError as e:
        logger.error(
            "Failed to describe cluster",
            extra={
                "account_id": account_id,
                "cluster_name": cluster_name,
                "error": str(e),
            },
        )
        return None


def _discover_auto_scaling_groups(
    session,
    account_id: str,
    region: str,
    cluster_name: str,
) -> list[dict]:
    """
    Discover Auto Scaling Groups associated with a given EKS cluster.

    Finds ASGs by looking for the tag 'eks:cluster-name' or
    'kubernetes.io/cluster/<cluster_name>' on the ASGs.

    Args:
        session: boto3 session with assumed role.
        account_id: AWS account ID.
        region: AWS region.
        cluster_name: EKS cluster name.

    Returns:
        List of ASG dicts with scaling details.
    """
    try:
        asg_client = session.client("autoscaling", region_name=region)

        # Paginate through all ASGs
        all_asgs = []
        paginator = asg_client.get_paginator("describe_auto_scaling_groups")
        for page in paginator.paginate():
            all_asgs.extend(page.get("AutoScalingGroups", []))

        matching_asgs = []
        for asg in all_asgs:
            asg_tags = {tag["Key"]: tag["Value"] for tag in asg.get("Tags", [])}

            # Match by 'eks:cluster-name' tag
            tag_cluster_name = asg_tags.get("eks:cluster-name", "")
            k8s_cluster_tag = f"kubernetes.io/cluster/{cluster_name}"
            k8s_match = k8s_cluster_tag in asg_tags

            if tag_cluster_name == cluster_name or k8s_match:
                # Skip if explicitly marked to be ignored
                if asg_tags.get("eks-operator/skip") == "true":
                    logger.info(
                        "Skipping node group due to skip tag",
                        extra={
                            "asg_name": asg["AutoScalingGroupName"],
                            "cluster_name": cluster_name,
                        },
                    )
                    continue
                # Determine instance types from the mixed instances policy or launch template
                instance_types = _extract_instance_types(asg)
                
                # Determine capacity type (spot vs on-demand)
                capacity_type = _extract_capacity_type(asg)
                
                # Derive a friendly nodegroup name from tags
                nodegroup_name = asg_tags.get(
                    "eks:nodegroup-name",
                    asg_tags.get("Name", asg["AutoScalingGroupName"]),
                )

                # Derive status
                status = "ACTIVE"
                if asg["DesiredCapacity"] == 0 and asg["MinSize"] == 0:
                    status = "STOPPED"

                matching_asgs.append({
                    "name": nodegroup_name,
                    "asg_name": asg["AutoScalingGroupName"],
                    "asg_arn": asg["AutoScalingGroupARN"],
                    "status": status,
                    "desired_capacity": asg["DesiredCapacity"],
                    "min_size": asg["MinSize"],
                    "max_size": asg["MaxSize"],
                    "instance_types": instance_types,
                    "capacity_type": capacity_type,
                    "tags": asg_tags,
                    "instances_count": len(asg.get("Instances", [])),
                })

                logger.info(
                    "Found ASG for cluster",
                    extra={
                        "account_id": account_id,
                        "cluster_name": cluster_name,
                        "asg_name": asg["AutoScalingGroupName"],
                        "desired_capacity": asg["DesiredCapacity"],
                    },
                )

        return matching_asgs

    except ClientError as e:
        logger.error(
            "Failed to discover ASGs",
            extra={
                "account_id": account_id,
                "cluster_name": cluster_name,
                "error": str(e),
            },
        )
        return []


def _extract_instance_types(asg: dict) -> list[str]:
    """
    Extract instance types from an ASG definition.

    Checks mixed instances policy first, then falls back to
    launch template/configuration.

    Args:
        asg: ASG description dict from AWS API.

    Returns:
        List of instance type strings.
    """
    instance_types = []

    # Check mixed instances policy
    mip = asg.get("MixedInstancesPolicy")
    if mip:
        launch_template = mip.get("LaunchTemplate", {})
        overrides = launch_template.get("Overrides", [])
        for override in overrides:
            it = override.get("InstanceType")
            if it:
                instance_types.append(it)

    # Fallback: check launch template or config
    if not instance_types:
        lt_spec = asg.get("LaunchTemplate")
        if lt_spec:
            # Instance type is in the launch template itself
            instance_types.append("(from-launch-template)")
        elif asg.get("LaunchConfigurationName"):
            instance_types.append("(from-launch-config)")

    return instance_types


def _extract_capacity_type(asg: dict) -> str:
    """
    Determine if the ASG uses Spot or On-Demand instances.

    Args:
        asg: ASG description dict.

    Returns:
        'SPOT' or 'ON_DEMAND'.
    """
    mip = asg.get("MixedInstancesPolicy")
    if mip:
        dist = mip.get("InstancesDistribution", {})
        on_demand_pct = dist.get("OnDemandPercentageAboveBaseCapacity", 100)
        if on_demand_pct == 0:
            return "SPOT"
        elif on_demand_pct < 100:
            return "MIXED"

    return "ON_DEMAND"


def _matches_labels(tags: dict, label_filter: dict[str, str]) -> bool:
    """
    Check if tags match all label filter criteria.

    Args:
        tags: Resource tags.
        label_filter: Required tag key=value pairs.

    Returns:
        True if all filter criteria match.
    """
    for key, value in label_filter.items():
        if tags.get(key) != value:
            return False
    return True
