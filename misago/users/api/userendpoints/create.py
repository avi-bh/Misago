from django.contrib.auth import authenticate, get_user_model, login
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_protect

from rest_framework import status
from rest_framework.response import Response

from misago.conf import settings
from misago.core.mail import mail_user

from ... import captcha
from ...forms.register import RegisterForm
from ...serializers import AuthenticatedUserSerializer
from ...tokens import make_activation_token


UserModel = get_user_model()


@csrf_protect
def create_endpoint(request):
    if settings.account_activation == 'closed':
        raise PermissionDenied(_("New users registrations are currently closed."))

    form = RegisterForm(request.data, request=request)

    try:
        captcha.test_request(request)
    except ValidationError as e:
        form.add_error('captcha', e)

    if not form.is_valid():
        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)

    activation_kwargs = {}
    if settings.account_activation == 'user':
        activation_kwargs = {
            'requires_activation': UserModel.ACTIVATION_REQUIRED_USER
        }
    elif settings.account_activation == 'admin':
        activation_kwargs = {
            'requires_activation': UserModel.ACTIVATION_REQUIRED_ADMIN
        }

    new_user = UserModel.objects.create_user(
        form.cleaned_data['username'],
        form.cleaned_data['email'],
        form.cleaned_data['password'],
        joined_from_ip=request.user_ip,
        set_default_avatar=True,
        **activation_kwargs
    )

    mail_subject = _("Welcome on %(forum_name)s forums!")
    mail_subject = mail_subject % {'forum_name': settings.forum_name}

    if settings.account_activation == 'none':
        authenticated_user = authenticate(
            username=new_user.email,
            password=form.cleaned_data['password'])
        login(request, authenticated_user)

        mail_user(request, new_user, mail_subject,
                  'misago/emails/register/complete')

        return Response({
            'activation': 'active',
            'username': new_user.username,
            'email': new_user.email
        })
    else:
        activation_token = make_activation_token(new_user)

        activation_by_admin = new_user.requires_activation_by_admin
        activation_by_user = new_user.requires_activation_by_user

        mail_user(
            request, new_user, mail_subject,
            'misago/emails/register/inactive',
            {
                'activation_token': activation_token,
                'activation_by_admin': activation_by_admin,
                'activation_by_user': activation_by_user,
            })

        if activation_by_admin:
            activation_method = 'admin'
        else:
            activation_method = 'user'

        return Response({
            'activation': activation_method,
            'username': new_user.username,
            'email': new_user.email
        })
