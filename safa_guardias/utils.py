# utils.py
from .models import CentroEscolar


def obtener_centro_usuario(request):
    es_admin = request.user.is_superuser or (
            hasattr(request.user, 'perfil_profesor') and request.user.perfil_profesor.rol == 'ADMIN'
    )

    # 1. Si es admin y ha seleccionado un centro en su sesión, priorizamos ese.
    if es_admin:
        centro_id_sesion = request.session.get('centro_activo_id')
        if centro_id_sesion:
            return CentroEscolar.objects.filter(id=centro_id_sesion).first()

    # 2. Si no es admin o no ha seleccionado nada, devolvemos su centro real
    try:
        return request.user.perfil_profesor.centro
    except AttributeError:
        # Si es un superuser de Django puro y no tiene perfil de profesor
        return None


