# AWS EC2 Auto Start/Stop.
## 1. Architecture Overview:
EventBridge  ->  Lambda  ->  EC2  (Tag-Based Scheduling)

Amazon EventBridge Scheduler (cron): ```Fires at 8 AM (start) and 8 PM (stop) daily``` \
AWS Lambda Function: ```Receives action payload, queries EC2 by tag, executes start/stop``` \
Amazon EC2: ```Only instances tagged AutoSchedule=true are affected```

## 2. AWS Services Used: 
|Service	| Purpose	| Key Setting |
|----------|----------|-------------|
|Amazon EventBridge|Triggers Lambda on cron schedule|Timezone: Asia/Kolkata|
|AWS Lambda|Runs start/stop logic on EC2|Runtime: Python 3.12, Timeout: 30s|
|Amazon EC2|Target instances controlled by tags|Tag: AutoSchedule=true|
|AWS IAM|Least privilege permissions|Tag-conditioned start/stop policy|
|Amazon CloudWatch|Logs, alarms, error monitoring|30-day retention + error alarm|
|Amazon SNS|Email alerts on Lambda failure|Email subscription confirmed|
|Amazon SQS|Dead Letter Queue (failed events)|Catches events Lambda fails to handle|

## Step-1: Tag your Instances
Tag EC2 instances so Lambda can find them dynamically. Only tagged instances are started or stopped — everything else is untouched.

How to Add the Tag
1.	Go to AWS Console -> EC2 -> Instances \
2.	Select the instance you want on the schedule \
3.	Click Actions -> Instance Settings -> Manage Tags \
4.	Click Add Tag and enter exactly:

|Tag Key|Tag Value|
|-------|---------|
|AutoSchedule|true|

5.	Click Save — repeat for every instance you want scheduled

## Step-2: Create IAM Role (Least Privilege): 
The Lambda function needs an IAM Role with exactly the permissions it requires — nothing more. The stop/start permission is additionally restricted to only work on instances with the AutoSchedule=true tag.

Create the Role
6.	Go to IAM -> Roles -> Create Role
7.	Trusted entity type: AWS Service -> Lambda -> Next
8.	Skip attaching managed policies for now -> Next
9.	Role name: ec2-scheduler-lambda-role -> Create Role
10.	Open the new role -> Add Permissions -> Create Inline Policy
11.	Switch to JSON tab and paste the policy below -> Next
12.	Policy name: ec2-scheduler-policy -> Create Policy
13.	Also attach AWSLambdaBasicExecutionRole (for CloudWatch logs):
•	Add Permissions -> Attach Policies -> search AWSLambdaBasicExecutionRole -> Attach
```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/AutoSchedule": "true"
        }
      }
    }
  ]
}
```
```
Why this policy is secure
DescribeInstances needs Resource: * because it is a list operation. StartInstances and StopInstances are restricted by a tag condition — IAM independently enforces that only AutoSchedule=true instances can be touched, even if Lambda code had a bug.
```

## Step 3 — Create the Lambda Function
Create Function in AWS Console \
14.	Go to Lambda -> Functions -> Create Function \
15.	Select: Author from scratch \
16.	Function name: ec2-start-stop \
17.	Runtime: Python 3.12 \
18.	Execution role: Use an existing role -> ec2-scheduler-lambda-role \
19.	Click Create Function

Update Basic Settings \
20.	Go to Configuration -> General Configuration -> Edit \
21.	Set Timeout to 0 min 30 sec \
22.	Memory: 128 MB \
23.	Click Save

Final Production Lambda Code \
Replace default code in the Code tab with the code below. Click Deploy after pasting.
```
import boto3
import logging

# Structured logging -- appears cleanly in CloudWatch
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client("ec2")

def lambda_handler(event, context):
    action = event.get("action")

    # Validate action before doing anything
    if action not in ["start", "stop"]:
        logger.error(f"Invalid action received: {action}")
        return {"error": "Invalid action. Use start or stop"}

    target_state = "running" if action == "stop" else "stopped"

    # Find eligible instances -- wrapped in try/except
    try:
        response = ec2.describe_instances(
            Filters=[
                {"Name": "tag:AutoSchedule", "Values": ["true"]},
                {"Name": "instance-state-name", "Values": [target_state]}
            ]
        )
    except Exception as e:
        logger.error(f"Failed to describe instances: {str(e)}")
        raise  # Re-raise so Lambda marks execution as FAILED

    instance_ids = []
    instance_details = []

    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]

            # Extract Name tag from the tags list
            name = "Unnamed"
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break

            instance_ids.append(instance_id)
            instance_details.append({"id": instance_id, "name": name})

    if not instance_ids:
        logger.info(f"No eligible instances found for action: {action}")
        return {"message": f"No instances to {action}"}

    # Execute start or stop with error handling
    try:
        if action == "start":
            ec2.start_instances(InstanceIds=instance_ids)
            logger.info(f"Started instances: {instance_details}")
            return {
                "message": f"Started {len(instance_ids)} instance(s)",
                "instances": instance_details
            }
        elif action == "stop":
            ec2.stop_instances(InstanceIds=instance_ids)
            logger.info(f"Stopped instances: {instance_details}")
            return {
                "message": f"Stopped {len(instance_ids)} instance(s)",
                "instances": instance_details
            }
    except Exception as e:
        logger.error(f"Failed to {action} instances {instance_ids}: {str(e)}")
        raise  # Re-raise so Lambda marks execution as FAILED
```

## Step 4 — Test the Lambda
Test manually before connecting EventBridge. Always test stop first (safer).

Test Event: Stop \
24.	Lambda console -> Code tab -> Test -> Create new test event \
25.	Event name: stop-ec2 \
26.	Event JSON: ```{ "action": "stop" }``` \
27.	Click Save -> Test \
28.	Expected response:
```
{
  "message": "Stopped 1 instance(s)",
  "instances": [
    { "id": "i-0ed579eafdd73266f", "name": "schedule_instance-bsltest" }
  ]
}
```

Test Event: Start \
29.	Create another test event named: start-ec2 \
30.	Event JSON: { "action": "start" } \
31.	Run it and confirm instance moves to Running state in EC2 console

## Step 5 — EventBridge Scheduler
Create two EventBridge Scheduler rules. Set the timezone explicitly to avoid UTC confusion.

Rule 1 — Start at 8 AM \
32.	Amazon EventBridge -> Scheduler -> Schedules -> Create Schedule \
33.	Schedule name: my-ec2-start \
34.	Schedule type: Recurring -> Cron-based schedule \
35.	Timezone: Asia/Kolkata (select your local timezone) \
36.	Cron expression: 0 8 * * ? * \
37.	Click Next \
38.	Target: AWS Lambda -> select ec2-start-stop \
39.	Input: Constant (JSON text) -> ```{ "action": "start" }``` \
40.	Action after completion: NONE \
41.	Click Next -> Next -> Create Schedule

Rule 2 — Stop at 8 PM \
42.	Create another schedule named: my-ec2-stop \
43.	Same settings but: \
•	Cron expression: 0 20 * * ? * \
•	Input payload: { "action": "stop" }

| Schedule Name	| Cron Expression	|Action Payload	|Fires At (IST)|
|---------------|-----------------|---------------|--------------|
|my-ec2-start |	0 8 * * ? *	| { "action": "start" }	| 8:00 AM daily |
|my-ec2-stop	| 0 20 * * ? *	| { "action": "stop" }	| 8:00 PM daily |

## Step 6 — Production Hardening
These four additions make your setup genuinely production-ready: email alerting on failure, dead letter queue, log retention, and alarm monitoring.

##### 6.1  SNS Alert Topic (Email Notification on Failure) \
44.	Go to SNS -> Topics -> Create Topic \
45.	Type: Standard  |  Name: ec2-scheduler-alerts -> Create Topic \
46.	Click the topic -> Create Subscription \
47.	Protocol: Email  |  Endpoint: your-email@example.com -> Create \
48.	Open your inbox and click the AWS confirmation link


#####  6.2  CloudWatch Alarm on Lambda Errors \
49.	Go to CloudWatch -> Alarms -> Create Alarm \
50.	Click Select Metric -> Lambda -> By Function Name \
51.	Find ec2-start-stop -> select Errors metric -> Select Metric \
52.	Condition: Greater than 0 for 1 datapoint in 1 minute \
53.	Next -> In Alarm -> choose SNS topic: ec2-scheduler-alerts \
54.	Alarm name: ec2-scheduler-lambda-errors -> Create Alarm
```
What this gives you
If Lambda fails at 8 AM (permissions error, timeout, API throttle), you receive an email within 1-2 minutes. Without this, instances stay in the wrong state all day with zero visibility.
```

#####  6.3  Dead Letter Queue (DLQ)
55.	Go to SQS -> Create Queue -> Type: Standard \
56.	Name: ec2-scheduler-dlq -> Create Queue \
57.	Lambda -> Configuration -> Asynchronous Invocation -> Edit \
58.	Dead-letter queue service: SQS -> select ec2-scheduler-dlq \
59.	Maximum age of event: 1 hour  |  Retry attempts: 2 -> Save
```
Why a DLQ matters
EventBridge invokes Lambda asynchronously. If Lambda fails with no DLQ, the failed event is permanently lost with no record. A DLQ captures failed invocations in SQS where you can inspect or replay them.
```

##### 6.4  CloudWatch Log Retention \
60.	Go to CloudWatch -> Log Groups
61.	Find: /aws/lambda/ec2-start-stop
62.	Click Actions -> Edit Retention Setting -> 30 days -> Save



