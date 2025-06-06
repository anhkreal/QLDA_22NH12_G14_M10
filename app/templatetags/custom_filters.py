# app/templatetags/custom_filters.py
import base64
from django import template

register = template.Library()

@register.filter
def b64encode(value):
    if value:
        try:
            return base64.b64encode(value).decode('utf-8')
        except Exception:
            return ''
    return ''
