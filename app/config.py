"""
Configuration module for the EKS Operator service.

Uses pydantic-settings for environment-based configuration.
Provides STS session factory with TTL-cached assumed-role sessions.
"""

import logging
import threading
from functools import lru_cache
from typing import Union

import boto3
from botocore.exceptions import ClientError
from cachetools import TTLCache
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    management_account_id: str
    target_account_ids: str = ""
    operator_role_name: str = "eks-operator-spoke"
    external_id: str
    sns_topic_arn: str
    sqs_queue_url: str
    dynamodb_operations_table: str = "eks-operations"
    dynamodb_cluster_state_table: str = "eks-cluster-state"
    dynamodb_schedules_table: str = "eks-schedules"
    aws_region: str = "us-east-1"
    target_regions: str = ""
    max_discovery_workers: int = 10
    task_visibility_timeout: int = 900
    lambda_max_concurrency: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def parsed_target_regions(self) -> list[str]:
        """Parse target regions from comma-separated string."""
        if self.target_regions:
            return [r.strip() for r in self.target_regions.split(",") if r.strip()]
        return [self.aws_region]

    @property
    def parsed_target_account_ids(self) -> list[str]:
        """Parse target account IDs from comma-separated string or list."""
        if isinstance(self.target_account_ids, str):
            return [a.strip() for a in self.target_account_ids.split(",") if a.strip()]
        return self.target_account_ids


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()


# --- STS Session Factory with TTL Cache ---

_session_cache: TTLCache = TTLCache(maxsize=100, ttl=2700)
_session_lock: threading.Lock = threading.Lock()


def get_assumed_role_session(account_id: str, region_name: str = None) -> boto3.Session:
    """
    Assume the spoke role in the target account and return a boto3 Session.

    Sessions are cached for 45 minutes (STS tokens last 1 hour).
    Thread-safe via threading.Lock.

    Args:
        account_id: The AWS account ID to assume the role in.
        region_name: The region to use for the session (optional).

    Returns:
        boto3.Session configured with assumed-role credentials.

    Raises:
        RuntimeError: If AssumeRole fails for the given account.
    """
    cache_key = f"{account_id}-{region_name}"
    with _session_lock:
        if cache_key in _session_cache:
            logger.debug(
                "Using cached session",
                extra={"account_id": account_id, "region_name": region_name},
            )
            return _session_cache[cache_key]

    settings = get_settings()
    effective_region = region_name or settings.aws_region
    role_arn = f"arn:aws:iam::{account_id}:role/{settings.operator_role_name}"

    try:
        sts_client = boto3.client("sts", region_name=settings.aws_region)
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"eks-operator-{account_id}",
            ExternalId=settings.external_id,
            DurationSeconds=3600,
        )
        credentials = response["Credentials"]
        session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=effective_region,
        )

        with _session_lock:
            _session_cache[cache_key] = session

        logger.info(
            "Assumed role successfully",
            extra={"account_id": account_id, "role_arn": role_arn},
        )
        return session

    except ClientError as e:
        logger.error(
            "Failed to assume role",
            extra={
                "account_id": account_id,
                "role_arn": role_arn,
                "error": str(e),
            },
        )
        raise RuntimeError(
            f"Failed to assume role {role_arn} in account {account_id}: {e}"
        ) from e
