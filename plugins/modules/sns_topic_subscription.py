#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright: Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


DOCUMENTATION = r'''
module: sns_topic_subscription
short_description: Manages AWS SNS subscriptions
version_added: 6.0.0
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
        description: Endpoint for the subscription. SQS ARN for example.
        required: true
      protocol:
        description: Protocol for the subscription.
        required: true
      attributes:
        description: Attributes for the subscription. See [Boto doc](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sns.html#SNS.Client.set_subscription_attributes)
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
arn:
  description: The ARN of the topic subscription
  type: str
  returned: always
  sample: arn:aws:sns:us-west-4:123456789012:test:a89170dc-fef0-4cf8-bc7e-e02948903af9
attributes:
  description: Dict of sns topic subscription attributes
  type: complex
  returned: always
  contains:
    confirmation_was_authenticated:
      description: Whether communication to AWS was atuhenticated.
      returned: always
      type: bool
      sample: true
    endpoint:
      description: The target endpoint for the subscription.
      returned: always
      type: str
      sample: arn:aws:sqs:us-west-4:123456789012:test
    owner:
      description: The owning account for the subscription.
      returned: always
      type: str
      sample: 123456789012
    pending_confirmation:
      description: Whether the subscription still needs to be confirmed.
      returned: always
      type: bool
      sample: false
    protocol:
      description: The protocol for the subscription.
      returned: always
      type: str
      sample: sqs
    subscription_arn:
      description: The ARN for the subscription.
      returned: always
      type: str
      sample: arn:aws:sns:us-west-4:123456789012:test:a89170dc-fef0-4cf8-bc7e-e02948903af9
    subscription_principal:
      description: The ARN for the subscription.
      returned: always
      type: str
      sample: arn:aws:iam::123456789012:role/test
    topic_arn:
      description: The ARN for the topic which the subscription targets.
      returned: always
      type: str
      sample: arn:aws:sns:us-west-4:123456789012:test
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


from ansible.module_utils.common.dict_transformations import camel_dict_to_snake_dict

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
        self.attributes_set = {}

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
        boto_supported_attributes = [
            'DeliveryPolicy',
            'FilterPolicy',
            'RawMessageDelivery',
            'RedrivePolicy',
            'SubscriptionRoleArn',
        ]
        tmp_sub_attr = dict()
        for key in self.attributes_set:
            if key in boto_supported_attributes:
                tmp_sub_attr[key] = self.attributes_set[key]
        diff = set(self.desired_subscription_attributes.items()) ^ set(tmp_sub_attr.items())
        if len(diff) != 0:
            changed = True
            if not self.check_mode:
                for key in self.desired_subscription_attributes:
                    try:
                        self.connection.set_subscription_attributes(SubscriptionArn=sub_arn,
                                                                    AttributeName=key,
                                                                    AttributeValue=self.desired_subscription_attributes[key])
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
            self.topic_arn = self.topic_name
        else:
            name = self.topic_name
            if self.topic_type == 'fifo' and not name.endswith('.fifo'):
                name += ".fifo"
            self.topic_arn = topic_arn_lookup(self.connection, self.module, name)

        subscriptions_existing_list = {}
        desired_sub_key = (canonicalize_endpoint(self.subscription_protocol, self.subscription_endpoint))
        sublist = list_topic_subscriptions(self.connection, self.module, self.topic_arn)
        if len(sublist) != 0:
            for sub in sublist:
                sub_key = (canonicalize_endpoint(sub['Protocol'], sub['Endpoint']))
                subscriptions_existing_list[sub_key] = sub['SubscriptionArn']
            if desired_sub_key in subscriptions_existing_list:
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

    topic_type = module.params.get('topic').get('type')
    topic_name = module.params.get('topic').get('name')
    state = module.params.get('state')
    subscription_protocol = module.params.get('subscription').get('protocol')
    subscription_endpoint = module.params.get('subscription').get('endpoint')
    subscription_attributes = module.params.get('subscription').get('attributes')
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

    result = dict(
        arn=sns_topic_sub.sub_arn,
        attributes=camel_dict_to_snake_dict(sns_topic_sub.attributes_set)
    )

    module.exit_json(changed=changed,**result)


if __name__ == '__main__':
    main()
