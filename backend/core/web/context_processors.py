def ui(request):
    name = request.user.name if request.user.is_authenticated else ''
    initials = ''.join(word[0] for word in name.split() if word)[:2].upper()
    return {'display_initials': initials, 'cart_count': sum(request.session.get('cart', {}).values())}
