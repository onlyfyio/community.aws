#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: sqs_queue_info
short_description: sqs_queue_info module
version_added: 6.0.0
description:
- The M(community.aws.sqs_queue_info) module allows to get properties of a specific AWS SQS queue.
author:
- "Ralph Kühnert (@redradrat)"
options:
  name:
    description: The ARN or Name of the AWS SQS queue for which you wish to find information.
    required: true
    type: str
  type:
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
- name: list all the queues
  community.aws.sqs_queue_info:
  register: sqs_queue_list

- name: get info on specific queue
  community.aws.sqs_queue_info:
    name: "{{ queue_arn }}"
    type: fifo
  register: sqs_queue_info
'''

RETURN = r'''
arn:
    description: The ARN of the queue.
    type: str
    returned: always
    sample: "arn:aws:sqs:us-east-2:123456789012:name"
url:
    description: The queue url.
    type: str
    returned: always
    sample: "https://us-east-2.queue.amazonaws.com/123456789012/name"
attributes:
    description: Dict of sns queue details.
    type: complex
    returned: always
    contains:
        approximate_number_of_messages:
            description: Returns the approximate number of messages available for retrieval from the queue.
            type: int
            returned: always
            sample: 0
        approximate_number_of_messages_delayed:
            description: Returns the approximate number of messages in the queue that are delayed and not available for reading immediately. This can happen when the queue is configured as a delay queue or when a message has been sent with a delay parameter.
            type: int
            returned: always
            sample: 0
        approximate_number_of_messages_not_visible:
            description: Returns the approximate number of messages that are in flight. Messages are considered to be in flight if they have been sent to a client but have not yet been deleted or have not yet reached the end of their visibility window.
            type: str
            returned: always
            sample: 0
        delay_seconds:
            description: The delivery delay in seconds.
            type: int
            returned: always
            sample: 0
        maximum_message_size:
            description: The maximum message size in bytes.
            type: int
            returned: always
            sample: 262144
        message_retention_period:
            description: The message retention period in seconds.
            type: int
            returned: always
            sample: 345600
        queue_arn:
            description: The queue's Amazon resource name (ARN).
            type: str
            returned: on success
            sample: 'arn:aws:sqs:us-east-1:123456789012:queuename-987d2de0'
        redrive_policy:
            description: The string that includes the parameters for the dead-letter queue functionality of the source queue as a JSON object.
            type: str
            returned: always
            sample: '{"deadLetterTargetArn": "arn:aws:sqs:us-east-2:123456789012:test_dlq", "maxReceiveCount": 5}'
        sqs_managed_sse_enabled:
            description: Returns information about whether the queue is using SSE-SQS encryption using SQS owned encryption keys.
            type: bool
            returned: always
            sample: true
        visibility_timeout:
            description: The default visibility timeout in seconds.
            type: int
            returned: always
            sample: 30
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
        results = dict(arn=queue_arn, url=queue_url, attributes=describe_queue(client, queue_url))
    else:
        results = list_queues(client, module)

    module.exit_json(**results)


if __name__ == '__main__':
    main()
