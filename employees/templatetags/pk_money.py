from django import template

register = template.Library()


@register.filter
def pk_money(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    abs_num = abs(num)
    sign = '-' if num < 0 else ''
    if abs_num >= 1000000000:
        return f'{sign}{abs_num / 1000000000:.2f} Arab'
    elif abs_num >= 10000000:
        return f'{sign}{abs_num / 10000000:.2f} Cr'
    elif abs_num >= 100000:
        return f'{sign}{abs_num / 100000:.2f} Lakh'
    elif abs_num >= 1000:
        return f'{sign}{abs_num / 1000:.1f}K'
    else:
        return f'{sign}{abs_num:.0f}'