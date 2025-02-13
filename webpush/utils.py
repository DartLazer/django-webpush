from django.conf import settings
from django.forms.models import model_to_dict
from django.urls import reverse

from pywebpush import WebPushException, webpush


def send_notification_to_user(user, payload, ttl=0):
    # Get all the push_info of the user

    push_infos = user.webpush_info.select_related("subscription")
    for push_info in push_infos:
        _send_notification(push_info.subscription, payload, ttl)


def send_notification_to_group(group_name, payload, ttl=0, exclude_user_id=None):
    from .models import Group

    push_infos = Group.objects.get(name=group_name).webpush_info.select_related("subscription")

    # Exclude the current user from receiving notifications if they are part of the target group.
    # This prevents users from receiving redundant notifications when they trigger an event themselves.
    if exclude_user_id is not None:
        push_infos = push_infos.exclude(user__id=exclude_user_id)

    for push_info in push_infos:
        _send_notification(push_info.subscription, payload, ttl)


def send_to_subscription(subscription, payload, ttl=0):
    return _send_notification(subscription, payload, ttl)


def _send_notification(subscription, payload, ttl):
    subscription_data = _process_subscription_info(subscription)
    vapid_data = {}

    webpush_settings = getattr(settings, 'WEBPUSH_SETTINGS', {})
    vapid_private_key = webpush_settings.get('VAPID_PRIVATE_KEY')
    vapid_admin_email = webpush_settings.get('VAPID_ADMIN_EMAIL')

    # Vapid keys are optional, and mandatory only for Chrome.
    # If Vapid key is provided, include vapid key and claims
    if vapid_private_key:
        vapid_data = {
            'vapid_private_key': vapid_private_key,
            'vapid_claims': {"sub": "mailto:{}".format(vapid_admin_email)}
        }

    try:
        req = webpush(subscription_info=subscription_data, data=payload, ttl=ttl, **vapid_data)
        return req
    except WebPushException as e:
        # If the subscription is expired, delete it.
        if e.response.status_code == 410:
            subscription.delete()
        else:
            # Its other type of exception!
            raise e


def _process_subscription_info(subscription):
    subscription_data = model_to_dict(subscription, exclude=["browser", "id"])
    endpoint = subscription_data.pop("endpoint")
    p256dh = subscription_data.pop("p256dh")
    auth = subscription_data.pop("auth")

    return {
        "endpoint": endpoint,
        "keys": {"p256dh": p256dh, "auth": auth}
    }


def get_templatetag_context(context):
    request = context['request']
    vapid_public_key = getattr(settings, 'WEBPUSH_SETTINGS', {}).get('VAPID_PUBLIC_KEY', '')

    data = {'group': context.get('webpush', {}).get('group'),
            'user': getattr(request, 'user', None),
            'vapid_public_key': vapid_public_key,
            'webpush_save_url': reverse('save_webpush_info')
            }

    return data
