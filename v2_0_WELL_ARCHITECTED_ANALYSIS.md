# Multi-Cluster EKS Scheduler v2.0: Scale Analysis & Architecture Roadmap

This document evaluates the current v1.0 architecture, explicitly identifying the mathematical limits and bottlenecks required to safely scale the solution to manage **1,000+ EKS Clusters** across hundreds of AWS accounts.

---

## 1. The Math of Scaling: 1000+ Clusters
If you have 1000 EKS clusters, each with say 3–5 nodegroups, that's **3,000–5,000 ASG scaling operations** potentially triggered in a single scheduling window. This sheer volume stress-tests every component of the architecture simultaneously.

---

## 2. Critical Bottlenecks (Well-Architected Analysis)

### A. Reliability & Throttling Limits

**1. Lambda Worker — STS AssumeRole at Scale**
*   **The Problem**: Every Lambda Worker invocation performs `sts:AssumeRole` into a spoke account. STS has a soft limit of 2,000 calls/sec globally per account. At 1000 clusters with burst scaling, we hit this instantly. STS throttling causes the Lambda to fail, throwing the message back to SQS, creating a retry storm and DLQ flood.
*   **v2.0 Fix**: Implement STS session caching with credential reuse (min 15-min sessions) across Lambda invocations, or utilize a pre-assumed role credential store via Secrets Manager or ElastiCache.

**2. Cross-Account API Rate Limits (The Silent Killer)**
*   **The Problem**: AWS enforces strict rate limits per account (e.g., `eks:UpdateNodegroupConfig` is 100 req/sec, `autoscaling:SetDesiredCapacity` is 100 req/sec). Triggering 10 clusters in the same spoke account concurrently will hit EKS/ASG API throttling. The current Lambda Worker lacks exponential backoff, worsening the throttling via aggressive retries.
*   **v2.0 Fix**: Implement advanced jittered exponential backoff (e.g., Python's `tenacity` library) for all downstream AWS API interactions. Be explicitly aware of per-account rate limits.

### B. Performance Efficiency & The "Thundering Herd"

**1. Single SNS Topic → Single SQS Queue Bottleneck**
*   **The Problem**: The current flow (Scheduler → 1 SNS → 1 SQS → Worker) breaks at scale. If 1,000 clusters fire at 9:00 AM, 5000 SQS messages arrive instantly. If the Worker Lambda's `lambda_max_concurrency` is capped (e.g., at 100), you have 4,900+ messages sitting in queue, delaying the actual scaling operations.
*   **v2.0 Fix**: Implement per-account or per-region SQS queues with dedicated Lambda concurrency pools to segment the blast radius and ensure swift execution.

**2. EventBridge 1-Minute Cron (Precision Problem)**
*   **The Problem**: A 1-minute global cron evaluates 1000+ schedules and dumps thousands of SNS messages simultaneously. This creates a massive "Thundering Herd" at the `:00` second mark of every minute.
*   **v2.0 Fix**: Jitter and stagger message publishing. Introduce a random delay (0–50 seconds) per cluster message so scaling operations spread evenly across the 60-second window.

### C. Scalability & Data Management

**1. Lambda Scheduler — Reading 1000 Schedules**
*   **The Problem**: One Lambda traversing a DynamoDB table for 1000+ schedules risks hitting the 15-minute Lambda timeout constraint, especially if evaluation logic expands. If the Lambda times out at minute 14, the next EventBridge triggers at minute 15, causing overlaps and duplicate scale events.
*   **v2.0 Fix**: Partition schedules by account/region. Use DynamoDB `Query` (not `Scan`) with a GSI on the schedule time. Fan out schedule evaluation to child Lambdas or Step Functions.

**2. DynamoDB — Hot Partition Risk**
*   **The Problem**: 1,000 concurrent Lambda Workers writing to `eks-operations` or `eks-cluster-state`. If partition keys are poorly distributed (e.g., heavily grouping by `account_id`), we hit hot partitions. Hot partitions are throttled even in On-Demand mode due to per-partition burst limits.
*   **v2.0 Fix**: Add a shard suffix to partition keys to ensure write sharding. Enable DynamoDB DAX for read-heavy schedule lookups.

### D. Cost & Compute Optimization

**1. ECS Fargate (API Control Plane)**
*   **The Problem**: While the ECS API is not the main bottleneck, static `service_desired_count` limits its ability to handle concurrent API bursts from thousands of clients or automated checks.
*   **v2.0 Fix**: Implement Target Tracking Auto Scaling on CPU or request count. Add Application Load Balancer connection draining and circuit breaker patterns.

---

## 3. Consolidated Recommendation Plan for v2.0

To achieve a production-grade operator supporting 1000+ clusters, the architecture must transition from a simple fan-out to a heavily sharded, dynamically scaled, and observable system.

### Phase 1: The Decoupling Layer
*   **Current State**: 1 SNS → 1 SQS → 1 Lambda Worker function.
*   **v2.0 Goal**: 
    *   Route SNS to **SQS queues sharded per region/account**.
    *   Deploy **Lambda Worker pools per shard** to isolate concurrency bottlenecks.
    *   Introduce **AWS Step Functions** for complex multi-step operations replacing single monolithic Lambda runs.

### Phase 2: The Scaling Layer
*   **Current State**: Static `lambda_max_concurrency`, static ECS desired count, DynamoDB scanning.
*   **v2.0 Goal**:
    *   Implement **Reserved Concurrency** per Lambda function shard.
    *   Implement **SQS-based Auto Scaling** for Lambda (using queue depth metrics).
    *   Configure **ECS Target Tracking Auto Scaling** for the API layer.
    *   Upgrade databases to **DynamoDB On-Demand + DAX** with sharded partition keys.

### Phase 3: The Reliability Layer
*   **Current State**: Basic SQS Dead Letter Queue (DLQ), immediate failures on API limits.
*   **v2.0 Goal**:
    *   Implement **Exponential backoff + jitter** in the Lambda Worker using `tenacity`.
    *   Introduce aggressive **STS credential caching**.
    *   Build **Per-account rate limit awareness** into the routing logic.
    *   Use Step Functions for built-in retry/catch and circuit breaker patterns.

### Phase 4: The Observability Layer
*   **Current State**: Base CloudWatch Logs.
*   **v2.0 Goal**:
    *   Generate a specific **CloudWatch metric per cluster/account**.
    *   Create dynamic **Alarms on SQS queue depth** > threshold.
    *   Create **Alarms on Lambda error rate** > 1%.
    *   Implement **AWS X-Ray tracing end-to-end** across the API, SNS, SQS, and Lambda limits.
    *   Provide a custom operational dashboard per spoke account.
