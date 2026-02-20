# EKS Operator - Multi-Account Node Group Scheduler

Stateless FastAPI service running on ECS Fargate that stops and starts
EKS node groups across multiple AWS accounts in an Organization.

## Architecture

```
+---------------------------------------------+
|              Hub AWS Account                 |
|                                              |
User ----> ALB ----> ECS Fargate (FastAPI)     |
|              |                               |
|              v SNS publish                   |
|          SNS Topic                           |
|              | subscription                  |
|              v                               |
|          SQS Queue ------> DLQ               |
|              | event source mapping          |
|              v                               |
|       Lambda Worker (per nodegroup)          |
|              | AssumeRole                    |
|              v                               |
|    +--- Target AWS Account ---+              |
|    |        EKS Cluster       |              |
|    +--------------------------+              |
|                                              |
|  EventBridge (1 min)                         |
|       |                                      |
|       v                                      |
|  Lambda Scheduler --> SNS (same path)        |
|                                              |
|  All components --> DynamoDB (3 tables)      |
|    - eks-operations                          |
|    - eks-cluster-state                       |
|    - eks-schedules                           |
+----------------------------------------------+
```

## Prerequisites

- Terraform >= 1.5.0
- AWS CLI configured with management account credentials
- Docker installed and running
- VPC with public and private subnets

## Deploy

```bash
cd terraform

# 1. Initialize
terraform init

# 2. Create your variables file
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# 3. Plan
terraform plan -var-file=terraform.tfvars

# 4. Apply (writes Python files, builds Docker, pushes to ECR, provisions all infra)
terraform apply -var-file=terraform.tfvars

# 5. Deploy spoke role to target accounts via CloudFormation StackSets
#    using the output JSON policies
terraform output spoke_role_trust_policy_json
terraform output spoke_role_permissions_json
```

## Add a New AWS Account

**Option A**: Add account ID to `target_account_ids` in tfvars
**Option B**: Ensure account is in AWS Organization (auto-discovered)
**Always**: Deploy spoke role to new account via StackSets

## API Usage

```bash
# Set your ALB endpoint
API=$(terraform output -raw api_base_url)

# Health check
curl $API/health

# Discover clusters with label filter
curl "$API/clusters?label_filter=env=dev,team=backend"

# Stop all dev clusters with auto_stop tag
curl -X POST $API/operation/stop \
  -H "Content-Type: application/json" \
  -d '{"label_filter": {"env": "dev"}, "initiated_by": "admin"}'

# Start clusters from a previous stop operation
curl -X POST $API/operation/start \
  -H "Content-Type: application/json" \
  -d '{"source_operation_id": "OP_ID_HERE", "initiated_by": "admin"}'

# Check operation status with full detail
curl "$API/operation/{operation_id}?detail=true"

# Get nodegroup-level detail
curl "$API/operation/{operation_id}/nodegroups"

# Create a schedule (stop at 8pm EST, start at 6am EST)
curl -X POST $API/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dev cluster nightly stop/start",
    "timezone": "America/New_York",
    "target": {
      "type": "label_filter",
      "label_filter": {"env": "dev", "team": "platform"}
    },
    "stop_cron": "0 20 * * 1-5",
    "start_cron": "0 6 * * 1-5",
    "enabled": true,
    "override_windows": [
      {"date": "2024-12-25", "reason": "Christmas"}
    ]
  }'

# Get schedule with next trigger times
curl $API/schedules/{schedule_id}

# List all schedules
curl "$API/schedules?enabled_only=true"

# Manually trigger a schedule
curl -X POST "$API/schedules/{schedule_id}/trigger?action=stop"

# Pause a schedule
curl -X POST $API/schedules/{schedule_id}/pause \
  -H "Content-Type: application/json" \
  -d '{"until": "2024-01-20T00:00:00Z"}'

# Get schedule execution history
curl "$API/schedules/{schedule_id}/history?limit=10"
```

## Spoke Role StackSets Deployment

1. Get the trust policy and permissions policy JSONs:

```bash
terraform output spoke_role_trust_policy_json
terraform output spoke_role_permissions_json
```

2. Create a CloudFormation template with these policies
3. Deploy via StackSets to all target OUs/accounts
4. The spoke role name must match `spoke_role_name` variable (default: `eks-operator-spoke`)

## Safety Features

- **Production HARD BLOCK**: Clusters tagged `env=prod` are never exposed or operated on
- **auto_stop tag required**: Stop operations only affect clusters with `auto_stop=true`
- **Baseline preservation**: Original node group sizes are saved before stops and never overwritten
- **Idempotency locks**: Schedule triggers use DynamoDB locks to prevent duplicate operations
- **Override windows**: Skip scheduled operations on specific dates (holidays, etc.)
- **Optimistic locking**: Cluster state uses version-based concurrency control
