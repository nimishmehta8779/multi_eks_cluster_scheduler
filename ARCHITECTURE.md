# EKS Multi-Account Scheduler: AWS Architecture

This document provides the definitive architectural diagram and component breakdown for the Multi-Cluster EKS Scaling solution.

## Architecture Overview

![AWS Architecture](aws_architecture.png)

### Key Components

#### 1. Management Hub Account (Control Plane)
- **ALB & ECS Fargate**: Hosts the FastAPI provider for the REST interface and cluster discovery.
- **EventBridge & Scheduler Lambda**: Periodic poller (1-min) that evaluates cron schedules.
- **SNS & SQS**: Messaging backbone for fanning out scaling operations to 1000+ clusters.
- **DynamoDB**: Persistent store for schedules, operations, and cluster state baselines.
- **Worker Lambda**: Centralized execution engine that consumes tasks from SQS and performs cross-account scaling.

#### 2. Spoke Target Accounts (Data Plane)
- **EKS Cluster**: The target Kubernetes environment.
- **Auto Scaling Groups (ASG)**: Managed node groups subjected to automated scaling.

### Security
- **STS AssumeRole**: The Hub account's Worker Lambda assumes a regional role in each Spoke account to manage infrastructure securely.
- **Network Isolation**: ECS and Lambda components are hosted in private subnets with VPC endpoints for AWS services.

### Request Flow
1. **Trigger**: User (API) or EventBridge (Schedule) initiates an action.
2. **Orchestration**: Hub components evaluate the target and populate the SNS/SQS messaging pipeline.
3. **Execution**: The Worker Lambda triggers the scaling API call in the Spoke account.
4. **State Management**: Results and pre-stop baselines are stored in DynamoDB for recovery and auditing.

### Full Technical Deep-Dive
For a detailed mapping of Python functions, code modularity, and deployment environments (ECS vs Lambda), refer to our **[Code Workflow & Logic Guide](CODE_WORKFLOW.md)**.
