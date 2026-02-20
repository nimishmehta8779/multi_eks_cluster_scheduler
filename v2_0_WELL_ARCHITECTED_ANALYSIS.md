# Multi-Cluster EKS Scheduler v2.0: AWS Well-Architected Scale Analysis

This document evaluates the current v1.0 architecture against the **6 Pillars of the AWS Well-Architected Framework**, explicitly identifying the gaps and necessary upgrades required to safely scale the solution to manage **1,000+ Auto Scaling Groups (ASGs) and EKS Clusters** across hundreds of AWS accounts.

---

## 1. Reliability (The Biggest Gap for 1000+)

**Current State**: The system uses `boto3` inside a `ThreadPoolExecutor` (API/Scheduler) for API discovery and leverages SQS for fan-out task queuing, providing baseline reliability.

**Missing for 1,000+ Scale:**
*   **Throttling & Exponential Backoff**: At 1,000+ ASGs, simultaneous `sts:AssumeRole`, `eks:DescribeCluster`, and `autoscaling:SetDesiredCapacity` calls will incur massive `ThrottlingException` errors from AWS APIs, both in the Hub and Spoke accounts.
    *   *v2.0 Fix*: Implement advanced jittered exponential backoff (e.g., Python's `tenacity` library) for all downstream AWS API interactions.
*   **DynamoDB GSIs (Global Secondary Indexes)**: The `/operations/latest` API endpoint currently uses a DynamoDB `Scan`. At 1,000+ updates minute-by-minute, a full table scan will consume excessive Read Capacity Units (RCUs) and latency will spike.
    *   *v2.0 Fix*: Implement GSIs tuned for access patterns (e.g., Query by `created_at` or `status`).
*   **Partial Failure Resilience within Discovery**: If the Hub cannot assume the role in 1 out of 100 Spoke accounts during discovery, the entire API request shouldn't fail or block the other 99 accounts.
    *   *v2.0 Fix*: Isolate account failures in the `discovery.py` module, returning partial results and flagging the offline account in a DLQ.

## 2. Performance Efficiency

**Current State**: The `discover_all_resources` function fetches target states in real-time. Lambda concurrency handles the scaling bursts.

**Missing for 1,000+ Scale:**
*   **Synchronous Polling Bottleneck**: Actively querying AWS APIs across 1,000+ clusters via `ThreadPoolExecutor` takes several minutes, timing out REST API calls and the Scheduler Lambda (15-min limit).
    *   *v2.0 Fix*: **Shift to Event-Driven State Caching**. Stop querying AWS dynamically. Instead, Spoke accounts should use AWS EventBridge to push EKS/ASG state changes back to the Hub's DynamoDB table. The Hub API simply reads this centralized, microsecond-latency cache.
*   **Lambda Concurrency Exhaustion**: If the Scheduler dumps 1,000 messages into SQS at `10:00 UTC`, AWS Lambda will instantly scale to 1,000 concurrent executions. This could exhaust the entire Hub account's default Regional Concurrency Quota (1,000), starving other workloads in the account.
    *   *v2.0 Fix*: Implement **SQS Maximum Concurrency** on the Lambda Event Source Mapping (e.g., limit to 50 concurrent workers) to process the 1,000 tasks smoothly over 30-45 seconds without choking the AWS Account.

## 3. Operational Excellence

**Current State**: Basic structured JSON logging using CloudWatch.

**Missing for 1,000+ Scale:**
*   **Distributed Tracing**: When 1,000 tasks are fired into SQS, and 5 of them fail, identifying *why* those specific 5 failed across accounts is a nightmare.
    *   *v2.0 Fix*: Integrate **AWS X-Ray** or AWS Distro for OpenTelemetry (ADOT). Pass trace spans from the API -> SQS -> Lambda -> Spoke API call.
*   **Automated Quota Monitoring**: As the operator scales, the Spoke accounts might hit their own limits for simultaneous ASG capacity updates.
    *   *v2.0 Fix*: Integrate with AWS Service Quotas API to pre-flight check if scaling 50 ASGs in a single account will breach limits.

## 4. Security

**Current State**: Strong Hub-and-Spoke model with explicit `sts:AssumeRole` trusts and restrictive IAM policies.

**Missing for 1,000+ Scale:**
*   **STS Token Caching per Lambda Environment**: When 100 Lambda execution environments spin up simultaneously, they all attempt `sts:AssumeRole` concurrently. This spikes STS API limits.
    *   *v2.0 Fix*: Although the ECS API caches STS tokens (`cachetools.TTLCache`), Lambdas have individual lifespans. We need an advanced external caching layer (like Redis/ElastiCache) for STS tokens, or implement AWS IAM Roles Anywhere if operating across boundaries.

## 5. Cost Optimization

**Current State**: SQS, DynamoDB On-Demand, and Serverless Lambda scaling.

**Missing for 1,000+ Scale:**
*   **DynamoDB Write Capacity Surges**: When 1,000 Lambdas all report `COMPLETED` at exactly `10:01 UTC`, it will spike DynamoDB WCU capacity and potentially cost thousands of dollars per month on On-Demand billing.
    *   *v2.0 Fix*: If operations become highly predictable (e.g., everyday at 5 PM), switch to **Provisioned Capacity + Auto Scaling** a few minutes *before* the scheduled wave hits, drastically lowering DynamoDB costs.
*   **ECS Fargate Idle Management**: The API is running 24/7.
    *   *v2.0 Fix*: For a purely configuration-based API, migrating FastAPI to AWS API Gateway + Lambda using `Mangum` would eliminate the base cost of Fargate compute entirely.

## 6. Sustainability

**Current State**: Turning off 1,000 idle EKS clusters saves massive amounts of carbon footprint (computing power and cooling).

**Missing for 1,000+ Scale:**
*   **Network Payload Optimization**: The discovery API currently fetches entire pages of AWS API responses just to parse labels.
    *   *v2.0 Fix*: Event-Driven Caching (as recommended in Performance Efficiency) ensures the system isn't continuously dumping Megabytes of redundant JSON over the AWS backbone every minute during discovery loops.

---

### v2.0 Immediate Roadmap Priorities:
1. **Move Discovery to Event-Driven DynamoDB Cache (Stop dynamic polling).**
2. **Implement `tenacity` exponential backoff for Boto3 Spoke calls.**
3. **Set `maximum_concurrency` on the SQS-Lambda trigger (e.g., Max 50).**
4. **Implement DynamoDB GSIs for API Read operations.**
