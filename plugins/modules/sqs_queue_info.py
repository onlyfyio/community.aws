#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: sns_queue_info
short_description: sns_queue_info module
version_added: 6.0.0
description:
- The M(community.aws.sns_queue_info) module allows to get all AWS SQS queues or properties of a specific AWS SQS queue.
author:
- "Ralph Kühnert (@redradrat)"
options:
  queue_name:
      description: The ARN or Name of the AWS SQS queue for which you wish to find information.
      required: true
      type: str
  queue_type:
      description:
      - Standard or FIFO queue.
      - I(queue_type) can only be set at queue creation and will otherwise be
          ignored.
      choices: ['standard', 'fifo']
      default: 'standard'
      type: str        
extends_documentation_fragment:
- amazon.aws.aws
- amazon.aws.ec2
- amazon.aws.boto3
'''

EXAMPLES = r'''
- name: list all the topics
  community.aws.sns_topic_info:
  register: sns_topic_list

- name: get info on specific topic
  community.aws.sns_topic_info:
    topic_arn: "{{ sns_arn }}"
  register: sns_topic_info
'''

RETURN = r'''
result:
  description:
    - The result contaning the details of one or all AWS SNS topics.
  returned: success
  type: list
  contains:
    sns_arn:
        description: The ARN of the topic.
        type: str
        returned: always
        sample: "arn:aws:sns:us-east-2:123456789012:my_topic_name"
    sns_topic:
        description: Dict of sns topic details.
        type: complex
        returned: always
        contains:
            content_based_deduplication:
              description: Whether or not content_based_deduplication was set
              returned: always
              type: bool
              sample: true
            delivery_policy:
                description: Delivery policy for the SNS topic.
                returned: when topic is owned by this AWS account
                type: str
                sample: >
                    {"http":{"defaultHealthyRetryPolicy":{"minDelayTarget":20,"maxDelayTarget":20,"numRetries":3,"numMaxDelayRetries":0,
                    "numNoDelayRetries":0,"numMinDelayRetries":0,"backoffFunction":"linear"},"disableSubscriptionOverrides":false}}
            display_name:
                description: Display name for SNS topic.
                returned: when topic is owned by this AWS account
                type: str
                sample: My topic name
            owner:
                description: AWS account that owns the topic.
                returned: when topic is owned by this AWS account
                type: str
                sample: '123456789012'
            policy:
                description: Policy for the SNS topic.
                returned: when topic is owned by this AWS account
                type: str
                sample: >
                    {"Version":"2012-10-17","Id":"SomePolicyId","Statement":[{"Sid":"ANewSid","Effect":"Allow","Principal":{"AWS":"arn:aws:iam::123456789012:root"},
                    "Action":"sns:Subscribe","Resource":"arn:aws:sns:us-east-2:123456789012:ansible-test-dummy-topic","Condition":{"StringEquals":{"sns:Protocol":"email"}}}]}
            subscriptions:
                description: List of subscribers to the topic in this AWS account.
                returned: always
                type: list
                sample: []
            subscriptions_added:
                description: List of subscribers added in this run.
                returned: always
                type: list
                sample: []
            subscriptions_confirmed:
                description: Count of confirmed subscriptions.
                returned: when topic is owned by this AWS account
                type: str
                sample: '0'
            subscriptions_deleted:
                description: Count of deleted subscriptions.
                returned: when topic is owned by this AWS account
                type: str
                sample: '0'
            subscriptions_existing:
                description: List of existing subscriptions.
                returned: always
                type: list
                sample: []
            subscriptions_new:
                description: List of new subscriptions.
                returned: always
                type: list
                sample: []
            subscriptions_pending:
                description: Count of pending subscriptions.
                returned: when topic is owned by this AWS account
                type: str
                sample: '0'
            subscriptions_purge:
                description: Whether or not purge_subscriptions was set.
                returned: always
                type: bool
                sample: true
            topic_arn:
                description: ARN of the SNS topic (equivalent to sns_arn).
                returned: when topic is owned by this AWS account
                type: str
                sample: arn:aws:sns:us-east-2:123456789012:ansible-test-dummy-topic
            topic_type:
                description: The type of topic.
                type: str
                sample: "standard"
'''


try:
    import botocore
except ImportError:
    pass  # handled by AnsibleAWSModule


from ansible_collections.amazon.aws.plugins.module_utils.core import AnsibleAWSModule
from ansible_collections.amazon.aws.plugins.module_utils.ec2 import AWSRetry
from ansible_collections.community.aws.plugins.module_utils.sqs import get_client
from ansible_collections.community.aws.plugins.module_utils.sqs import get_queue_name
from ansible_collections.community.aws.plugins.module_utils.sqs import get_queue_url
from ansible_collections.community.aws.plugins.module_utils.sqs import get_queue_arn
from ansible_collections.community.aws.plugins.module_utils.sqs import describe_queue
from ansible_collections.community.aws.plugins.module_utils.sqs import list_queues


def main():
    argument_spec = dict(
        name=dict(type='str', required=True),
        type=dict(type='str', default='standard', choices=['standard', 'fifo']),
    )

    module = AnsibleAWSModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    client = get_client(module)

    queue_arn = None
    name = module.params.get('name')
    is_fifo = module.params.get('type') in ('fifo')
    if name.startswith('arn:'):
      queue_arn = name
    else:
      queue_url = get_queue_url(client, get_queue_name(module, is_fifo))
      queue_arn = get_queue_arn(client, queue_url)
      

    if queue_arn:
        results = dict(sqs_queue_arn=queue_arn, sqs_queue_url=queue_url, sqs_queue_attributes=describe_queue(client, queue_url))
    else:
        results = list_queues(client, module)

    module.exit_json(**results)


if __name__ == '__main__':
    main()
