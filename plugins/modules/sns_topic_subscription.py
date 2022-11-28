#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: sns_topic_subscription
short_description: Manages AWS SNS subscriptions
version_added: 1.0.0
description:
    - The M(community.aws.sns_topic_subscription) module allows you to create, delete, and manage subscriptions for AWS SNS topics.
author:
  - "Ralph Kühnert (@redradrat)"
options:
  topic:
    description:
      - Topic for which subscriptions shall be managed.
    type: dict
    required: true
    suboptions:
      name:
        description:
          - The name or ARN of the SNS topic to manage.
        required: true
        type: str
      type:
        description:
          - The type of topic. Either Standard for FIFO (first-in, first-out).
        choices: ["standard", "fifo"]
        default: 'standard'
        type: str
  state:
    description:
      - Whether to create or destroy an SNS topic.
    default: present
    choices: ["absent", "present"]
    type: str
  subscription:
    description:
      - Subscription to the topic. Note that AWS requires
        subscriptions to be confirmed, so you will need to confirm any new
        subscriptions.
    type: dict
    required: true
    suboptions:
      endpoint:
        description: Endpoint of subscription.
        required: true
      protocol:
        description: Protocol of subscription.
        required: true
      attributes:
        description: Attributes of subscription. Only supports RawMessageDelievery for SQS endpoints.
        default: {}
extends_documentation_fragment:
- amazon.aws.aws
- amazon.aws.ec2
- amazon.aws.boto3
'''

EXAMPLES = r"""

- name: Create alarm SNS topic subscription
  community.aws.sns_topic_subscription:
    state: present
    topic:
      name: "alarms"
      type: "standard"
    subscription:
      endpoint: "my_email_address@example.com"
      protocol: "email"

- name: Create alarm SNS topic subscription
  community.aws.sns_topic_subscription:
    state: present
    topic:
      name: "alarms"
      type: "standard"
    subscription:
      endpoint: "arn:aws:sqs:us-west-4:123456789012:queue"
      protocol: "sqs"
      attributes:
        RawMessageDelievery: true

- name: Delete alarm SNS topic subscription
  community.aws.sns_topic_subscription:
    state: absent
    topic:
      name: "alarms"
      type: "standard"
    subscription:
      endpoint: "arn:aws:sqs:us-west-4:123456789012:queue"
      protocol: "sqs"
"""

RETURN = r'''
subscription_id:
    description: The id of the topic subscription
    type: str
    returned: always
    sample: "c9a5b229-303d-4619-acc4-82b9f990210f"
sns_topic_subscription:
  description: Dict of sns topic subscription details
  type: complex
  returned: always
  contains:
    check_mode:
      description: whether check mode was on
      returned: always
      type: bool
      sample: false
'''

import json

try:
    import botocore
except ImportError:
    pass  # handled by AnsibleAWSModule

from ansible_collections.amazon.aws.plugins.module_utils.core import AnsibleAWSModule
from ansible_collections.community.aws.plugins.module_utils.sns import topic_arn_lookup
from ansible_collections.community.aws.plugins.module_utils.sns import list_topic_subscriptions
from ansible_collections.community.aws.plugins.module_utils.sns import canonicalize_endpoint


class SnsTopicSubscriptionManager(object):
    """ Handles SNS Topic Subscription creation and destruction """

    def __init__(self,
                 module,
                 topic_type,
                 topic_name,
                 state,
                 subscription_protocol,
                 subscription_endpoint,
                 subscription_attributes,
                 check_mode):

        self.connection = module.client('sns')
        self.module = module
        self.topic_type = topic_type
        self.topic_name = topic_name
        self.state = state
        self.subscription_protocol = subscription_protocol
        self.subscription_endpoint = subscription_endpoint
        self.subscription_attributes = subscription_attributes
        self.check_mode = check_mode
        self.topic_arn = None
        self.sub_arn = None
        self.desired_subscription_attributes = dict()
        self.attributes_set = []

    def _create_sub(self):
        if not self.check_mode:
            try:
                response = self.connection.subscribe(
                    TopicArn=self.topic_arn,
                    Protocol=self.subscription_protocol,
                    Endpoint=self.subscription_endpoint,
                    ReturnSubscriptionArn=True
                )
            except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
                self.module.fail_json_aws(e, msg="Couldn't subscribe to topic %s" % self.name)
            self.sub_arn = response['SubscriptionArn']
        return True

    def _init_desired_subscription_attributes(self):
        tmp_dict = self.subscription_attributes
        # aws sdk expects values to be strings
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#SNS.Client.set_subscription_attributes
        for k, v in tmp_dict.items():
            tmp_dict[k] = str(v)

        self.desired_subscription_attributes = tmp_dict

    def _set_topic_subs_attributes(self):
        changed = False
        sub_arn = self.sub_arn

        try:
            self.attributes_set = self.connection.get_subscription_attributes(SubscriptionArn=sub_arn)['Attributes']
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
            self.module.fail_json_aws(e, "Couldn't get subscription attributes for subscription %s" % sub_arn)

        # TODO(redradrat): find a proper comparison strategy... probably if not full equal, then change
        diff = set(self.desired_subscription_attributes.items()) ^ set(self.attributes_set.items())
        if len(diff) != 0:
            changed = True
            if not self.check_mode:
                for key, val in self.desired_subscription_attributes:
                    try:
                        self.connection.set_subscription_attributes(SubscriptionArn=sub_arn,
                                                                    AttributeName=key,
                                                                    AttributeValue=val)
                    except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
                        self.module.fail_json_aws(e, "Couldn't set subscription attribute '%s'" % key)
            self.attributes_set = self.desired_subscription_attributes
        
        return changed

    def _delete_sub(self):
        changed = True
        if not self.check_mode:
            try:
                self.connection.unsubscribe(SubscriptionArn=self.sub_arn)
            except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as e:
                self.module.fail_json_aws(e, msg="Couldn't delete subscription %s" % self.sub_arn)
        return changed

    def ensure_ok(self):
        changed = False
        if not self.topic_arn:
            self.module.fail_json(msg="Cannot subscribe to topic. Topic '%s' does not exist." % self.topic_arn)
            return changed
        if not self.sub_arn:
            changed |= self._create_sub()

        self._init_desired_subscription_attributes()
        changed |= self._set_topic_subs_attributes()

        return changed

    def ensure_gone(self):

        changed = False
        if not self.topic_arn:
            return changed
        if self.sub_arn:
            changed |= self._delete_sub()

        return changed

    def populate_arns(self):
        name = self.topic_name
        if name.startswith('arn:'):
            self.topic_arn = self.name
        else:
            name = self.name
            if self.topic_type == 'fifo' and not name.endswith('.fifo'):
                name += ".fifo"
            self.topic_arn = topic_arn_lookup(self.connection, self.module, name)
        
        subscriptions_existing_list = {}
        desired_sub_key = (canonicalize_endpoint(self.subscription_protocol, self.subscription_endpoint))
        for sub in list_topic_subscriptions(self.connection, self.module, self.topic_arn):
            sub_key = (sub['Protocol'], sub['Endpoint'])
            subscriptions_existing_list[sub_key] = sub['SubscriptionArn']
        if (desired_sub_key in subscriptions_existing_list):
            self.sub_arn = subscriptions_existing_list[sub_key]


def main():
    argument_spec = dict(
        state=dict(default='present', choices=['present', 'absent']),
        topic=dict(type='dict', required=True, options=dict(
            type=dict(type='str', required=True),
            name=dict(type='str', required=True)
        )),
        subscription=dict(type='dict', required=True, options=dict(
            protocol=dict(type='str', required=True),
            endpoint=dict(type='str', required=True),
            attributes=dict(type='dict', default={})
        )),
    )

    module = AnsibleAWSModule(argument_spec=argument_spec,
                              supports_check_mode=True)

    topic_type = module.params.get('topic_type')
    topic_name = module.params.get('topic_name')
    state = module.params.get('state')
    subscription_protocol = module.params.get('subscription_protocol')
    subscription_endpoint = module.params.get('subscription_endpoint')
    subscription_attributes = module.params.get('subscription_attributes')
    check_mode = module.check_mode

    sns_topic_sub = SnsTopicSubscriptionManager(module,
                                state=state,
                                topic_type=topic_type,
                                topic_name=topic_name,
                                subscription_protocol=subscription_protocol,
                                subscription_endpoint=subscription_endpoint,
                                subscription_attributes=subscription_attributes,
                                check_mode=check_mode)

    sns_topic_sub.populate_arns()

    if state == 'present':
        changed = sns_topic_sub.ensure_ok()
    elif state == 'absent':
        changed = sns_topic_sub.ensure_gone()

    sns_topic_sub_facts = dict(changed=changed,
                     sns_topic_subscription_arn=sns_topic_sub.sub_arn,
                     sns_topic_subscription=sns_topic_sub.attributes_set(sns_topic_sub.connection, module, sns_topic_sub.topic_arn))

    module.exit_json(**sns_topic_sub_facts)


if __name__ == '__main__':
    main()
