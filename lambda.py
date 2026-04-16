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
