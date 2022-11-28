from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re
import copy

try:
    import botocore
except ImportError:
    pass  # handled by AnsibleAWSModule


from ansible_collections.amazon.aws.plugins.module_utils.core import is_boto3_error_code
from ansible_collections.amazon.aws.plugins.module_utils.ec2 import AWSRetry
from ansible_collections.amazon.aws.plugins.module_utils.ec2 import camel_dict_to_snake_dict


@AWSRetry.jittered_backoff()
def _list_queues_with_backoff(client):
    paginator = client.get_paginator('list_queues')
    return paginator.paginate().build_full_result()['QueueUrls']


def get_client(module):
    retry_decorator = AWSRetry.jittered_backoff(catch_extra_error_codes=['AWS.SimpleQueueService.NonExistentQueue'])
    client = module.client('sqs', retry_decorator=retry_decorator)
    return client


def get_queue_name(module, is_fifo=False):
    name = module.params.get('name')
    if not is_fifo or name.endswith('.fifo'):
        return name
    return name + '.fifo'


# NonExistentQueue is explicitly expected when a queue doesn't exist
@AWSRetry.jittered_backoff()
def get_queue_url(client, name):
    try:
        return client.get_queue_url(QueueName=name)['QueueUrl']
    except is_boto3_error_code('AWS.SimpleQueueService.NonExistentQueue'):
        return None


# NonExistentQueue is explicitly expected when a queue doesn't exist
@AWSRetry.jittered_backoff()
def get_queue_arn(client, url):
    try:
        return client.client.get_queue_attributes(QueueUrl=url,AttributeNames=['QueueArn'])['Attributes']['QueueArn']
    except is_boto3_error_code('AWS.SimpleQueueService.NonExistentQueue'):
        return None


def describe_queue(client, queue_url):
    """
    Description a queue in snake format
    """
    attributes = client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=['All'], aws_retry=True)['Attributes']
    description = dict(attributes)
    description.pop('Policy', None)
    description.pop('RedrivePolicy', None)
    description = camel_dict_to_snake_dict(description)
    description['policy'] = attributes.get('Policy', None)
    description['redrive_policy'] = attributes.get('RedrivePolicy', None)

    # Boto3 returns everything as a string, convert them back to integers/dicts if
    # that's what we expected.
    for key, value in description.items():
        if value is None:
            continue

        if key in ['policy', 'redrive_policy']:
            policy = json.loads(value)
            description[key] = policy
            continue

        if key == 'content_based_deduplication':
            try:
                description[key] = bool(value)
            except (TypeError, ValueError):
                pass

        try:
            if value == str(int(value)):
                description[key] = int(value)
        except (TypeError, ValueError):
            pass

    return description


def list_queues(client, module):
    try:
        queues = _list_queues_with_backoff(client)
    except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
        module.fail_json_aws(e, msg="Couldn't get queue list")
    return [q for q in queues]
