from django.contrib.auth import views as auth_views


def password_reset_view(request):
    return auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/password_reset_email.txt',
        subject_template_name='accounts/password_reset_subject.txt',
    )(request)


def password_reset_done_view(request):
    return auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    )(request)


def password_reset_confirm_view(request, uidb64, token):
    return auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
    )(request, uidb64=uidb64, token=token)


def password_reset_complete_view(request):
    return auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    )(request)
