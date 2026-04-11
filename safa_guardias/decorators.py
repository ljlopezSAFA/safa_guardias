from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages


def rol_requerido(roles_permitidos):
    """
    Decorador genérico para restringir vistas según el rol del Profesor.
    Si el usuario no tiene el rol, lanza un mensaje de error y redirige.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # 1. Verificamos si está logueado (por si olvidaste el @login_required)
            if not request.user.is_authenticated:
                messages.warning(request, "Debes iniciar sesión para acceder.")
                return redirect('login')

            # 2. El superusuario de Django SIEMPRE tiene acceso total
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # 3. Comprobamos si tiene perfil y su rol está en la lista de permitidos
            if hasattr(request.user, 'perfil_profesor'):
                if request.user.perfil_profesor.rol in roles_permitidos:
                    return view_func(request, *args, **kwargs)

            # 4. Si llega aquí, es que no tiene permiso
            messages.error(request, "Acceso denegado. No tienes los permisos necesarios para ver esta sección.")
            return redirect('index')  # Cambia 'index' por tu URL base o dashboard

        return _wrapped_view

    return decorator



def es_directivo_o_admin(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if hasattr(user, 'perfil_profesor'):
        return user.perfil_profesor.rol in ['ADMIN', 'DIRE', 'JEFE']
    return False

def solo_directivos(view_func):
    """Decorador para proteger las vistas de la central de datos"""
    def _wrapped_view(request, *args, **kwargs):
        if es_directivo_o_admin(request.user):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied("No tienes permisos para acceder a esta sección.")
    return _wrapped_view