# aws-ec2-scheduling-auto-start/stop
AWS EC2 Auto Start/Stop.
## 1. Architecture Overview:
EventBridge  ->  Lambda  ->  EC2  (Tag-Based Scheduling)

Amazon EventBridge Scheduler (cron): ```Fires at 8 AM (start) and 8 PM (stop) daily```
AWS Lambda Function: ```Receives action payload, queries EC2 by tag, executes start/stop```
Amazon EC2: ```Only instances tagged AutoSchedule=true are affected```

## 2. AWS Services Used: 
|Service	| Purpose	| Key Setting |
|----------|----------|-------------|
|Amazon EventBridge|Triggers Lambda on cron schedule|Timezone: Asia/Kolkata|
