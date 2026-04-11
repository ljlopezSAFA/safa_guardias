# context_processors.py
from .models import CentroEscolar
from .utils import obtener_centro_usuario


def selector_centros_global(request):
    es_admin = request.user.is_authenticated and (
            request.user.is_superuser or
            (hasattr(request.user, 'perfil_profesor') and request.user.perfil_profesor.rol == 'ADMIN')
    )

    if es_admin:
        return {
            'lista_centros_admin': CentroEscolar.objects.all().order_by('nombre'),
            'centro_activo_admin': obtener_centro_usuario(request)
        }
    return {}