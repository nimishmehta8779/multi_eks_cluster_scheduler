# Multi-Cluster EKS Scheduler: End-to-End Code Workflow

This document maps the Python code logic to the AWS platform, detailing what each core function does, where it resides, and why.

---

## 🧠 Code Logic Mind-Map (Paper Banana Format)

![Code Logic Mind-map](code_logic_mindmap.png)

---

## 🏗️ Deployment Distribution

The codebase is shared across three primary execution environments, each chosen for its specific operational profile.

### 1. The Hub API (`app/main.py`)
- **Enviroment**: AWS ECS Fargate
- **Responsibilities**: REST API management, manual scaling triggers, schedule configuration.
- **Why?**: Long-running HTTP context, stateful discovery results, and high availability.

### 2. The Timekeeper (`app/schedules/schedule_poller.py`)
- **Environment**: AWS Lambda (Scheduler)
- **Responsibilities**: Evaluating cron expressions once per minute.
- **Why?**: Purely event-driven; triggers once per minute, executes in milliseconds.

### 3. The Scaler (`app/operations/task_worker.py`)
- **Environment**: AWS Lambda (Worker)
- **Responsibilities**: Massively parallel execution of scaling tasks.
- **Why?**: High horizontal scale; can process 500+ ASGs in parallel without a bottleneck.

---

## 🔄 End-to-End Function Workflow

### Phase 1: Initiation
| Function | File | Environment | Summary |
| :--- | :--- | :--- | :--- |
| `handler` | `schedule_poller.py` | Lambda (S) | **Entry Point**: Scans DynamoDB for active schedules every minute. |
| `manual_trigger` | `main.py` | ECS | **Entry Point**: REST call to force a schedule execution now. |
| `stop_operation` | `main.py` | ECS | **Entry Point**: REST call to stop all clusters matching a label. |

### Phase 2: Orchestration (The Brain)
| Function | File | Summary |
| :--- | :--- | :--- |
| `is_triggered` | `cron_utils.py` | Logic to check if a schedule’s cron matches the current minute. |
| `trigger_schedule_operation` | `schedule_worker.py` | Fetches target clusters/ASGs and creates an Operation ID. |
| `discover_all_resources` | `discovery.py` | Uses `ThreadPoolExecutor` to scan multi-account ASGs in parallel. |

### Phase 3: Fan-Out (The Dispatcher)
| Function | File | Summary |
| :--- | :--- | :--- |
| `fan_out_operation` | `operation_router.py` | Splts a single "Stop Clusters" request into individual SQS messages for every target ASG. |

### Phase 4: Execution (The Muscle)
| Function | File | Environment | Summary |
| :--- | :--- | :--- | :--- |
| `handler` | `task_worker.py` | Lambda (W) | Consumes a single SQS message (1 ASG). |
| `stop_nodegroup` | `eks_controller.py` | Lambda (W) | Performs **STS AssumeRole** into the Spoke Account. |
| `scale_nodegroup` | `eks_controller.py` | Lambda (W) | Updates the AWS ASG API with the target capacity (e.g., 0). |
| `create_baseline` | `cluster_baseline.py`| Saves pre-stop ASG sizes to DynamoDB for later restoration. |

---

## 🔒 Shared Utility Layer
All environments utilize these core modules:
- **`config.py`**: Resolves environment variables and manages cross-account sessions.
- **`state_manager.py`**: Centralized logic for reading/writing to the 3 DynamoDB tables.
- **`json_logging.py`**: Ensures CloudWatch logs are structured for easy indexing.
