import csv
import io
from datetime import datetime, timedelta, date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Case, When, Value, IntegerField
from .decorators import rol_requerido, solo_directivos
from .forms import *
from .utils import obtener_centro_usuario
from django.core.paginator import Paginator


# Create your views here.
@login_required
def pagina_inicio(request):
    centro = obtener_centro_usuario(request)

    if not centro and not request.user.is_superuser:
        messages.error(request, "Tu usuario no tiene un centro escolar asignado.")
        return redirect('logout')

    ahora = timezone.localtime(timezone.now())
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()

    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_hoy.weekday()]

    # AÑADIDO: .prefetch_related('etapas') para optimizar la carga del ManyToMany
    tramos_actuales = TramoHorario.objects.filter(
        centro=centro,
        dia_semana=dia_sem,
        hora_inicio__lte=hora_actual,
        hora_fin__gte=hora_actual
    ).prefetch_related('etapas')

    if tramos_actuales.exists():
        generar_guardias_del_dia(fecha_hoy, centro)

    guardias_pendientes = []
    if tramos_actuales.exists():
        guardias_pendientes = RegistroGuardia.objects.filter(
            centro=centro,
            fecha=fecha_hoy,
            tramo_horario__in=tramos_actuales
        ).select_related('profesor_ausente', 'grupo', 'aula', 'tramo_horario').prefetch_related('tramo_horario__etapas')

    disponibles = []
    if tramos_actuales.exists():
        vistos = set()
        for tramo in tramos_actuales:
            profes_tramo = obtener_profesores_disponibles(tramo, fecha_hoy, centro)
            for p in profes_tramo:
                if p.id not in vistos:
                    p.tramo_asociado = tramo
                    disponibles.append(p)
                    vistos.add(p.id)

    docentes_ausentes_hoy = RegistroGuardia.objects.filter(
        centro=centro,
        fecha=fecha_hoy
    ).values('profesor_ausente').distinct().count()

    context = {
        'tramos_actuales': tramos_actuales,
        'guardias_pendientes': guardias_pendientes,
        'profesores_disponibles': disponibles,
        'hora_servidor_iso': ahora.isoformat(),
        'conteo_pendientes': len([g for g in guardias_pendientes if g.estado == 'PENT']) if tramos_actuales.exists() else 0,
        'ausencias_hoy': docentes_ausentes_hoy,
    }

    return render(request, 'inicio.html', context)


@login_required
def ver_profesores(request):
    centro = obtener_centro_usuario(request)
    # CORREGIDO: Solo profesores de su centro
    profesores = Profesor.objects.filter(centro=centro)
    return render(request, "profesores.html", {"lista_profesores": profesores})


@login_required
def ver_aulas(request):
    centro = obtener_centro_usuario(request)
    # CORREGIDO: Añadido el query que te faltaba
    aulas = Aula.objects.filter(centro=centro)
    return render(request, "aulas.html", {"aulas": aulas})


@login_required
@solo_directivos
def central_importar(request):
    # Cogemos el centro directamente del selector global o del perfil del directivo
    centro_actual = obtener_centro_usuario(request)

    es_admin = request.user.is_superuser or (
            hasattr(request.user, 'perfil_profesor') and request.user.perfil_profesor.rol == 'ADMIN'
    )

    if request.method == 'POST':
        form = CentralImportForm(request.POST, request.FILES)
        if form.is_valid():
            tipo = form.cleaned_data['tipo_dato']
            archivo = request.FILES['archivo']

            # --- VERIFICACIÓN DE CENTRO ---
            if tipo != 'centro' and not centro_actual:
                messages.error(request,
                               "Debes seleccionar un Centro Escolar en la barra superior para importar estos datos.")
                return redirect('central_importar')

            try:
                decoded_file = archivo.read().decode('UTF-8')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string, delimiter=',', quotechar='"')

                try:
                    next(reader)  # Saltar cabecera
                except StopIteration:
                    messages.error(request, "El archivo CSV está vacío.")
                    return redirect('central_importar')

                creados, actualizados, errores = 0, 0, 0

                with transaction.atomic():
                    for row in reader:
                        if not row: continue

                        created = False
                        try:
                            if tipo == 'centro':
                                # admin importa centros: nombre, codigo, localidad, provincia, ccaa
                                obj, created = CentroEscolar.objects.update_or_create(
                                    codigo=row[1].strip(),
                                    defaults={
                                        'nombre': row[0].strip(),
                                        'localidad': row[2].strip() if len(row) > 2 else '',
                                        'provincia': row[3].strip() if len(row) > 3 else '',
                                        'comunidad_autonoma': row[4].strip() if len(row) > 4 else ''
                                    }
                                )

                            elif tipo == 'profesor':
                                obj, created = Profesor.objects.update_or_create(
                                    email=row[2].strip().lower(),
                                    defaults={
                                        'centro': centro_actual,
                                        'nombre': row[0].strip(),
                                        'apellidos': row[1].strip(),
                                        'abreviatura': row[3].strip().upper()
                                    }
                                )
                            elif tipo == 'aula':
                                # CUIDADO: La clave única es centro + abrev
                                obj, created = Aula.objects.update_or_create(
                                    centro=centro_actual,
                                    abrev=row[2].strip(),
                                    defaults={
                                        'nombre': row[0].strip(),
                                        'pabellon': row[1].strip(),
                                    }
                                )
                            elif tipo == 'materia':
                                obj, created = Materia.objects.update_or_create(
                                    centro=centro_actual,
                                    abrev=row[1].strip().upper(),
                                    defaults={'nombre': row[0].strip()}
                                )
                            elif tipo == 'grupo':
                                obj, created = Grupo.objects.update_or_create(
                                    centro=centro_actual,
                                    nombre=row[0].strip().upper(),
                                    curso=row[1].strip(),
                                    defaults={'etapa': row[2].strip()}
                                )
                            elif tipo == 'tramo':
                                obj, created = TramoHorario.objects.get_or_create(
                                    centro=centro_actual,
                                    hora_inicio=row[0].strip(),
                                    hora_fin=row[1].strip(),
                                    dia_semana=row[2].strip().upper()
                                )
                            elif tipo == 'horario':
                                try:
                                    tramo = TramoHorario.objects.get(
                                        centro=centro_actual, dia_semana=row[0].strip().upper(),
                                        hora_inicio=row[1].strip(), hora_fin=row[2].strip()
                                    )
                                    materia = Materia.objects.get(centro=centro_actual, abrev=row[3].strip().upper())
                                    profesor = Profesor.objects.get(centro=centro_actual,
                                                                    abreviatura=row[4].strip().upper())
                                    aula = Aula.objects.get(centro=centro_actual, abrev=row[5].strip())
                                    grupo = Grupo.objects.get(centro=centro_actual, nombre=row[6].strip().upper())

                                    obj, created = Horario.objects.update_or_create(
                                        tramo_horario=tramo, grupo=grupo, profesor=profesor,
                                        defaults={'materia': materia, 'aula': aula}
                                    )
                                except Exception as e:
                                    print(f"Error en fila {row}: {e}")
                                    errores += 1
                                    continue

                            elif tipo == 'guardia':
                                try:
                                    tramo = TramoHorario.objects.get(
                                        centro=centro_actual, dia_semana=row[0].strip().upper(),
                                        hora_inicio=row[1].strip(), hora_fin=row[2].strip()
                                    )
                                    profesor = Profesor.objects.get(centro=centro_actual,
                                                                    abreviatura=row[4].strip().upper())
                                    prioridad_val = int(row[5].strip()) if len(row) > 5 else 0

                                    obj, created = HorarioGuardia.objects.update_or_create(
                                        tramo_horario=tramo, profesor=profesor,
                                        defaults={'tipo_guardia': row[3].strip().upper(), 'prioridad': prioridad_val}
                                    )
                                except Exception as e:
                                    print(f"Error en fila guardia {row}: {e}")
                                    errores += 1
                                    continue

                            if created:
                                creados += 1
                            else:
                                actualizados += 1

                        except IntegrityError as e:
                            print(f"Conflicto de integridad {row}: {e}")
                            errores += 1
                        except Exception as e:
                            print(f"Error inesperado {row}: {e}")
                            errores += 1

                if errores > 0:
                    messages.warning(request,
                                     f'Terminado: {creados} creados, {actualizados} actualizados, {errores} omitidos por errores (Revisa consola).')
                else:
                    messages.success(request, f'¡Éxito! {creados} creados y {actualizados} actualizados.')
                return redirect('central_importar')

            except Exception as e:
                messages.error(request, f'Error crítico: {e}')
                return redirect('central_importar')
    else:
        form = CentralImportForm()

    return render(request, 'importar_csv.html', {'form': form, 'es_admin': es_admin, 'centro': centro_actual})

def descargar_plantilla_csv(request, tipo):
    """Genera y descarga un CSV de plantilla basado en el tipo solicitado"""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="plantilla_{tipo}.csv"'

    # Escribimos el BOM de UTF-8 para que Excel lo abra bien sin romper las tildes
    response.write('\ufeff'.encode('utf8'))
    writer = csv.writer(response, delimiter=',', quotechar='"')

    # Diccionario de cabeceras según el tipo
    cabeceras = {
        'centro': ['nombre_centro', 'codigo_oficial', 'localidad', 'provincia', 'comunidad_autonoma'],
        'profesor': ['nombre', 'apellidos', 'email', 'abreviatura'],
        'aula': ['nombre_aula', 'pabellon', 'abreviatura_aula'],
        'materia': ['nombre_materia', 'abreviatura'],
        'grupo': ['nombre_grupo', 'curso', 'etapa_abreviada'],
        'tramo': ['hora_inicio_hh:mm', 'hora_fin_hh:mm', 'dia_semana_letra'],
        'horario': ['dia_semana_letra', 'hora_inicio_hh:mm', 'hora_fin_hh:mm', 'materia_abr', 'profesor_abr',
                    'aula_abr', 'grupo_nombre'],
        'guardia': ['dia_semana_letra', 'hora_inicio_hh:mm', 'hora_fin_hh:mm', 'tipo_guardia', 'profesor_abr',
                    'prioridad_0_a_9']
    }

    ejemplos = {
        'centro': ['SAFA Úbeda', '23004351', 'Úbeda', 'Jaén', 'Andalucía'],
        'profesor': ['Juan', 'Pérez García', 'juanperez@safa.edu', 'JPG'],
        'aula': ['Aula 101', 'Edificio Principal', 'A101'],
        'materia': ['Matemáticas', 'MAT'],
        'grupo': ['A', '2º', 'ESO'],
        'tramo': ['08:00', '09:00', 'L'],
        'horario': ['L', '08:00', '09:00', 'MAT', 'JPG', 'A101', 'A'],
        'guardia': ['L', '08:00', '09:00', 'GU-REC', 'JPG', '5']
    }

    if tipo in cabeceras:
        writer.writerow(cabeceras[tipo])
        writer.writerow(ejemplos[tipo])  # Fila de ejemplo

    return response


@login_required
def visor_horarios(request):
    centro = obtener_centro_usuario(request)

    etapas_objs = Etapa.objects.filter(centro=centro).order_by('nombre')
    grupos = Grupo.objects.filter(centro=centro).select_related('etapa').order_by('etapa__nombre', 'curso', 'nombre')
    profesores = Profesor.objects.filter(centro=centro).order_by('apellidos')
    materias_todas = Materia.objects.filter(centro=centro)

    grupo_id = request.GET.get('grupo')
    profesor_id = request.GET.get('profesor')
    etapa_id = request.GET.get('etapa')

    dias_semana = ['L', 'M', 'X', 'J', 'V']
    horario_tabla = []
    entidad_nombre = ""
    num_clases = 0
    num_guardias = 0
    total_horas = 0

    tramos_base = TramoHorario.objects.filter(centro=centro).prefetch_related('etapas')
    tramos_qs = []
    clases = []
    guardias = []

    if profesor_id:
        p = get_object_or_404(Profesor, id=profesor_id, centro=centro)
        entidad_nombre = f"Horario de: {p.apellidos}, {p.nombre}"

        clases = Horario.objects.filter(profesor=p).select_related('materia', 'aula', 'grupo__etapa', 'tramo_horario')
        guardias = HorarioGuardia.objects.filter(profesor=p).select_related('tramo_horario')

        # Etapas en las que da clase el profesor
        etapas_profe = clases.values_list('grupo__etapa_id', flat=True).distinct()

        # Tramos comunes o de sus etapas
        tramos_qs = tramos_base.filter(
            Q(etapas__isnull=True) | Q(etapas__id__in=list(etapas_profe))
        ).distinct().order_by('hora_inicio')

        num_clases = clases.values('tramo_horario').distinct().count()
        num_guardias = guardias.values('tramo_horario').distinct().count()
        total_horas = num_clases + num_guardias

    elif grupo_id:
        g = get_object_or_404(Grupo, id=grupo_id, centro=centro)
        entidad_nombre = f"Horario de: {g.curso} {g.nombre}"

        clases = Horario.objects.filter(grupo=g).select_related('materia', 'profesor', 'aula', 'tramo_horario')

        # Tramos comunes o de la etapa del grupo
        tramos_qs = tramos_base.filter(
            Q(etapas__isnull=True) | Q(etapas__id=g.etapa_id)
        ).distinct().order_by('hora_inicio')

    # 1. Recuperamos la lógica de agrupar para NO duplicar filas
    horas_filas = []
    seen_horas = set()
    for t in tramos_qs:
        if (t.hora_inicio, t.hora_fin) not in seen_horas:
            horas_filas.append(t)
            seen_horas.add((t.hora_inicio, t.hora_fin))

    # 2. Construimos la tabla cruzando por HORA y DÍA (no por ID de tramo)
    for tramo in horas_filas:
        fila = {'tramo': tramo, 'celdas': []}
        for dia in dias_semana:
            # Aquí volvemos a comparar por hora_inicio y dia_semana para que encaje en la cuadrícula
            c_celda = [c for c in clases if
                       c.tramo_horario.hora_inicio == tramo.hora_inicio and c.tramo_horario.dia_semana == dia]

            if profesor_id:
                g_celda = [g for g in guardias if
                           g.tramo_horario.hora_inicio == tramo.hora_inicio and g.tramo_horario.dia_semana == dia]
            else:
                g_celda = []

            fila['celdas'].append({'clases': c_celda, 'guardias': g_celda})

        horario_tabla.append(fila)

    return render(request, 'visor_horarios.html', {
        'etapas': etapas_objs,
        'grupos': grupos,
        'profesores': profesores,
        'materias_todas': materias_todas,
        'horario_tabla': horario_tabla,
        'dias_semana': dias_semana,
        'grupo_seleccionado': int(grupo_id) if grupo_id and grupo_id.isdigit() else None,
        'profesor_seleccionado': int(profesor_id) if profesor_id and profesor_id.isdigit() else None,
        'etapa_seleccionada_id': int(etapa_id) if etapa_id and etapa_id.isdigit() else None,
        'entidad_nombre': entidad_nombre,
        'num_clases': num_clases,
        'num_guardias': num_guardias,
        'total_horas': total_horas,
    })


@login_required
def visor_guardias(request):
    centro = obtener_centro_usuario(request)

    # 1. Sacamos las horas únicas y su estado de recreo
    tramos_referencia = TramoHorario.objects.filter(centro=centro).values(
        'hora_inicio', 'hora_fin', 'es_recreo'
    ).distinct().order_by('hora_inicio')

    dias = ['L', 'M', 'X', 'J', 'V']

    # 2. Traemos TODAS las guardias del centro de una vez
    guardias_qs = HorarioGuardia.objects.filter(
        profesor__centro=centro
    ).select_related('profesor', 'tramo_horario')

    cuadrante = []

    for tramo in tramos_referencia:
        fila = {
            'inicio': tramo['hora_inicio'],
            'fin': tramo['hora_fin'],
            'es_recreo': tramo['es_recreo'],
            'columnas': []
        }

        for dia in dias:
            # 3. Filtramos la lista en memoria (súper rápido)
            guardias_celda = [
                g for g in guardias_qs
                if g.tramo_horario.hora_inicio == tramo['hora_inicio']
                   and g.tramo_horario.dia_semana == dia
            ]

            fila['columnas'].append(guardias_celda)

        cuadrante.append(fila)

    return render(request, 'visor_guardias.html', {
        'cuadrante': cuadrante,
        'dias': dias
    })


# --- CRUD PARA BAJAS ---
@login_required
def gestionar_baja(request, pk=None):
    centro = obtener_centro_usuario(request)
    baja = get_object_or_404(BajaProfesor, pk=pk, centro=centro) if pk else None
    titulo = "Editar Baja de Profesor" if pk else "Registrar Nueva Baja"

    if request.method == 'POST':
        form = BajaProfesorForm(request.POST, instance=baja, centro=centro)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.centro = centro
            obj.save()

            # LIMPIEZA: Si acortamos las fechas de la baja, borramos guardias huérfanas
            if pk:
                if obj.fecha_fin:
                    RegistroGuardia.objects.filter(baja_origen=obj).filter(
                        Q(fecha__lt=obj.fecha_inicio) | Q(fecha__gt=obj.fecha_fin)
                    ).delete()
                else:
                    RegistroGuardia.objects.filter(baja_origen=obj, fecha__lt=obj.fecha_inicio).delete()

            # REGENERACIÓN: Si la baja afecta a hoy, generamos guardias
            hoy = timezone.localtime(timezone.now()).date()
            if obj.fecha_inicio <= hoy and (not obj.fecha_fin or hoy <= obj.fecha_fin):
                generar_guardias_del_dia(hoy, centro)

            messages.success(request, f"Baja {'actualizada' if pk else 'registrada'} correctamente.")
            return redirect('gestion_ausencias')
    else:
        form = BajaProfesorForm(instance=baja, centro=centro)

    return render(request, 'formulario_ausencias.html',
                  {'form': form, 'titulo': titulo, 'icono': 'bi-person-dash-fill', 'color': 'danger'})


@login_required
def eliminar_baja(request, pk):
    centro = obtener_centro_usuario(request)
    baja = get_object_or_404(BajaProfesor, pk=pk, centro=centro)

    # Eliminamos las guardias generadas por esta baja
    RegistroGuardia.objects.filter(baja_origen=baja).delete()
    baja.delete()

    messages.success(request, "Baja eliminada del sistema.")
    return redirect('gestion_ausencias')

# --- CRUD PARA EXCURSIONES ---
@login_required
def gestionar_salida(request, pk=None):
    centro = obtener_centro_usuario(request)
    salida = get_object_or_404(SalidaExcursion, pk=pk, centro=centro) if pk else None
    titulo = "Editar Salida/Excursión" if pk else "Programar Nueva Salida"

    if request.method == 'POST':
        form = SalidaExcursionForm(request.POST, instance=salida, centro=centro)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.centro = centro
            obj.save()
            form.save_m2m()  # Guardamos relaciones ManyToMany (vital para los grupos)

            # LIMPIEZA INCONGRUENCIAS (La magia del cruce de horarios)
            if obj.grupos_implicados.exists():
                # Borramos cualquier guardia previa (generada por una baja, por ejemplo)
                # que afecte a estos grupos, en estas fechas, y que se solape con las horas de la excursión.
                RegistroGuardia.objects.filter(
                    centro=centro,
                    fecha__range=[obj.fecha_inicio, obj.fecha_fin],
                    grupo__in=obj.grupos_implicados.all(),
                    # Fórmula de solapamiento: (Inicio Tramo < Fin Excursión) Y (Fin Tramo > Inicio Excursión)
                    tramo_horario__hora_inicio__lt=obj.hora_fin,
                    tramo_horario__hora_fin__gt=obj.hora_inicio
                ).delete()

            # REGENERACIÓN: Si los profesores acompañantes dejan clases vacías hoy
            hoy = timezone.localtime(timezone.now()).date()
            if obj.fecha_inicio <= hoy <= obj.fecha_fin:
                generar_guardias_del_dia(hoy, centro)

            messages.success(request, f"Excursión {'actualizada' if pk else 'programada'} correctamente.")
            return redirect('gestion_ausencias')
    else:
        form = SalidaExcursionForm(instance=salida, centro=centro)

    return render(request, 'formulario_ausencias.html',
                  {'form': form, 'titulo': titulo, 'icono': 'bi-bus-front-fill', 'color': 'success'})


@login_required
def eliminar_salida(request, pk):
    centro = obtener_centro_usuario(request)
    salida = get_object_or_404(SalidaExcursion, pk=pk, centro=centro)

    # Borramos las guardias creadas porque los profes se habían ido a esta excursión
    RegistroGuardia.objects.filter(excursion_origen=salida).delete()

    # Comprobamos si la excursión era hoy antes de borrarla
    hoy = timezone.localtime(timezone.now()).date()
    era_hoy = salida.fecha_inicio <= hoy <= salida.fecha_fin

    salida.delete()

    # REGENERACIÓN: Al cancelar la excursión, los grupos y profesores vuelven.
    # Regeneramos por si hay bajas pendientes de cubrir en esos grupos.
    if era_hoy:
        generar_guardias_del_dia(hoy, centro)

    messages.success(request, "Salida/Excursión cancelada y eliminada.")
    return redirect('gestion_ausencias')


@login_required
def gestion_ausencias(request):
    centro = obtener_centro_usuario(request)

    date_str = request.GET.get('date')
    if date_str:
        try:
            fecha_base = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_base = timezone.now().date()
    else:
        fecha_base = timezone.now().date()

    lunes = fecha_base - timedelta(days=fecha_base.weekday())
    domingo = lunes + timedelta(days=6)

    semana_anterior = (lunes - timedelta(days=7)).strftime('%Y-%m-%d')
    semana_siguiente = (lunes + timedelta(days=7)).strftime('%Y-%m-%d')

    bajas = BajaProfesor.objects.filter(
        centro=centro,
        fecha_inicio__lte=domingo
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=lunes)
    ).order_by('fecha_inicio')

    ausencias_semana = AusenciaPuntual.objects.filter(
        centro=centro,
        fecha__range=[lunes, domingo]
    ).order_by('fecha', 'hora_inicio')

    excursiones = SalidaExcursion.objects.filter(
        centro=centro,
        fecha_inicio__lte=domingo,
        fecha_fin__gte=lunes
    ).order_by('fecha_inicio')

    return render(request, 'gestion_ausencias.html', {
        'lunes': lunes,
        'domingo': domingo,
        'semana_anterior': semana_anterior,
        'semana_siguiente': semana_siguiente,
        'bajas_activas': bajas,
        'ausencias_semana': ausencias_semana,
        'excursiones': excursiones
    })


# --- CRUD PARA AUSENCIAS PUNTUALES ---
@login_required
def gestionar_ausencia_puntual(request, pk=None):
    centro = obtener_centro_usuario(request)
    ausencia = get_object_or_404(AusenciaPuntual, pk=pk, centro=centro) if pk else None

    if request.method == 'POST':
        form = AusenciaPuntualForm(request.POST, instance=ausencia, centro=centro)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.centro = centro
            obj.save()

            # LIMPIEZA: Si ha cambiado la fecha o las horas en la edición
            if pk:
                # Borramos las guardias de otra fecha
                RegistroGuardia.objects.filter(ausencia_origen=obj).exclude(fecha=obj.fecha).delete()
                # Borramos las guardias que ya no entran en el nuevo rango horario
                RegistroGuardia.objects.filter(ausencia_origen=obj).exclude(
                    tramo_horario__hora_inicio__lt=obj.hora_fin,
                    tramo_horario__hora_fin__gt=obj.hora_inicio
                ).delete()

            # REGENERACIÓN: Si la ausencia es para hoy
            hoy = timezone.localtime(timezone.now()).date()
            if obj.fecha == hoy:
                generar_guardias_del_dia(hoy, centro)

            messages.success(request, "Ausencia puntual registrada.")
            return redirect('gestion_ausencias')
    else:
        form = AusenciaPuntualForm(instance=ausencia, centro=centro)

    return render(request, 'formulario_ausencias.html', {
        'form': form,
        'titulo': "Permiso por Horas" if pk else "Nueva Ausencia Puntual",
        'color': 'warning',
        'icono': 'bi-clock-history'
    })


@login_required
def eliminar_ausencia_puntual(request, pk):
    centro = obtener_centro_usuario(request)
    ap = get_object_or_404(AusenciaPuntual, pk=pk, centro=centro)

    RegistroGuardia.objects.filter(ausencia_origen=ap).delete()
    ap.delete()

    messages.success(request, "Ausencia puntual cancelada y eliminada.")
    return redirect('gestion_ausencias')



def generar_guardias_del_dia(fecha_consulta=None, centro=None):
    if not centro:
        return 0  # Si por algún motivo se llama sin centro, abortamos silenciosamente para no mezclar datos

    if not fecha_consulta:
        fecha_consulta = timezone.now().date()

    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_consulta.weekday()]

    excursiones_hoy = SalidaExcursion.objects.filter(
        centro=centro,
        fecha_inicio__lte=fecha_consulta,
        fecha_fin__gte=fecha_consulta
    )

    ids_grupos_fuera = []
    for exc in excursiones_hoy:
        ids_grupos_fuera.extend(exc.grupos_implicados.values_list('id', flat=True))

    objetos_origen = {}

    bajas = BajaProfesor.objects.filter(
        centro=centro,
        fecha_inicio__lte=fecha_consulta
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_consulta)
    )

    for baja in bajas:
        objetos_origen[baja.profesor_id] = baja

    for exc in excursiones_hoy:
        for profe in exc.profesores_acompanantes.all():
            objetos_origen[profe.id] = exc

    # CORREGIDO: Filtramos a través de la relación 'profesor'
    clases_hoy = Horario.objects.filter(
        profesor__centro=centro,  # <--- EL TRUCO AQUÍ
        tramo_horario__dia_semana=dia_sem
    ).exclude(grupo_id__in=ids_grupos_fuera)

    registros_creados = 0
    for clase in clases_hoy:
        evento = objetos_origen.get(clase.profesor.id)
        ausencia_puntual = None

        if not evento:
            ausencia_puntual = AusenciaPuntual.objects.filter(
                centro=centro,
                profesor=clase.profesor,
                fecha=fecha_consulta,
                hora_inicio__lte=clase.tramo_horario.hora_inicio,
                hora_fin__gte=clase.tramo_horario.hora_fin
            ).first()

        if evento or ausencia_puntual:
            defaults_data = {
                'aula': clase.aula,
                'materia': clase.materia,
                'baja_origen': None,
                'excursion_origen': None,
                'ausencia_origen': None,
                'motivo_ausencia': None
            }

            if evento:
                if isinstance(evento, BajaProfesor):
                    defaults_data['baja_origen'] = evento
                    defaults_data['motivo_ausencia'] = "Baja Médica / Permiso"
                elif isinstance(evento, SalidaExcursion):
                    defaults_data['excursion_origen'] = evento
                    defaults_data['motivo_ausencia'] = f"Excursión: {evento.descripcion}"
            elif ausencia_puntual:
                defaults_data['ausencia_origen'] = ausencia_puntual
                defaults_data['motivo_ausencia'] = f"Ausencia: {ausencia_puntual.motivo or 'Asunto puntual'}"

            # ATENCIÓN: Si tu modelo 'RegistroGuardia' no tiene un campo 'centro' explícito,
            # tendrás que borrar la línea 'centro=centro' de este get_or_create.
            guardia, created = RegistroGuardia.objects.get_or_create(
                centro=centro,  # <--- Déjalo solo si el modelo tiene este campo
                fecha=fecha_consulta,
                tramo_horario=clase.tramo_horario,
                grupo=clase.grupo,
                profesor_ausente=clase.profesor,
                defaults=defaults_data
            )

            if not created:
                guardia.aula = defaults_data['aula']
                guardia.materia = defaults_data['materia']
                guardia.baja_origen = defaults_data['baja_origen']
                guardia.excursion_origen = defaults_data['excursion_origen']
                guardia.ausencia_origen = defaults_data['ausencia_origen']
                guardia.motivo_ausencia = defaults_data['motivo_ausencia']
                guardia.save()
            else:
                registros_creados += 1

    return registros_creados


def obtener_profesores_disponibles(tramo, fecha, centro):
    if not tramo or not centro:
        return []

    # 1. Profesores que tienen asignada una guardia en este tramo
    en_guardia_ids = set(HorarioGuardia.objects.filter(
        profesor__centro=centro,  # CORREGIDO
        tramo_horario=tramo
    ).values_list('profesor_id', flat=True))

    # 2. Profesores "liberados" porque su grupo está de excursión
    grupos_fuera_ids = SalidaExcursion.objects.filter(
        centro=centro,
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha
    ).values_list('grupos_implicados__id', flat=True)

    liberados_ids = set(Horario.objects.filter(
        profesor__centro=centro,  # CORREGIDO
        tramo_horario=tramo,
        grupo_id__in=grupos_fuera_ids
    ).values_list('profesor_id', flat=True))

    candidatos_ids = en_guardia_ids.union(liberados_ids)

    # 3. FILTRAR QUIÉNES NO ESTÁN REALMENTE (Bajas, excursiones, ausencias puntuales)
    bajas_ids = BajaProfesor.objects.filter(
        centro=centro,
        fecha_inicio__lte=fecha
    ).filter(
        Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
    ).values_list('profesor_id', flat=True)

    profes_fuera_ids = SalidaExcursion.objects.filter(
        centro=centro,
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha
    ).values_list('profesores_acompanantes__id', flat=True)

    ausencias_puntuales_ids = AusenciaPuntual.objects.filter(
        centro=centro,
        fecha=fecha,
        hora_inicio__lt=tramo.hora_fin,
        hora_fin__gt=tramo.hora_inicio
    ).values_list('profesor_id', flat=True)

    total_ausentes_ids = set(list(bajas_ids) + list(profes_fuera_ids) + list(ausencias_puntuales_ids))

    # 4. Obtener QuerySet base
    disponibles_qs = Profesor.objects.filter(
        centro=centro,
        id__in=candidatos_ids
    ).exclude(
        id__in=total_ausentes_ids
    ).distinct()

    # 5. Inyectar el motivo de disponibilidad
    disponibles = list(disponibles_qs)
    for profe in disponibles:
        if profe.id in liberados_ids:
            profe.motivo_disponibilidad = 'LIBERADO'
        elif profe.id in en_guardia_ids:
            profe.motivo_disponibilidad = 'GUARDIA'

    return disponibles


@login_required
def gestion_guardias_global(request):
    centro = obtener_centro_usuario(request)

    fecha_str = request.GET.get('fecha')
    tramo_id = request.GET.get('tramo')
    grupo_etapas = request.GET.get('grupo_etapas') # <-- Nuevo parámetro agrupado

    if fecha_str:
        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_consulta = timezone.localtime().date()
    else:
        fecha_consulta = timezone.localtime().date()

    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_consulta.weekday()]

    # Tramos del día para este centro base
    tramos_del_dia = TramoHorario.objects.filter(centro=centro, dia_semana=dia_sem).order_by('hora_inicio')

    # --- FILTRO AGRUPADO POR BLOQUES DE ETAPA ---
    if grupo_etapas == 'inf_pri':
        # Buscamos tramos vinculados a etapas que contengan Infantil o Primaria
        tramos_del_dia = tramos_del_dia.filter(
            Q(etapas__nombre__icontains='infantil') |
            Q(etapas__nombre__icontains='primaria')
        ).distinct()
    elif grupo_etapas == 'eso_esno':
        # Buscamos tramos vinculados a ESO, Bachillerato, FP, etc.
        tramos_del_dia = tramos_del_dia.filter(
            Q(etapas__nombre__icontains='eso') |
            Q(etapas__nombre__icontains='secundaria') |
            Q(etapas__nombre__icontains='bachillerato') |
            Q(etapas__nombre__icontains='esno') |
            Q(etapas__nombre__icontains='ciclo') |
            Q(etapas__nombre__icontains='fp')
        ).distinct()

    # Validar el tramo seleccionado (si cambiamos de bloque, el tramo viejo se resetea)
    tramo_seleccionado = None
    if tramo_id:
        tramo_seleccionado = tramos_del_dia.filter(id=tramo_id).first()

    if not tramo_seleccionado and tramos_del_dia.exists():
        tramo_seleccionado = tramos_del_dia.first()

    # Generar registros vacíos (tu función externa)
    generar_guardias_del_dia(fecha_consulta, centro)

    # Guardias de ese centro
    guardias_dia = RegistroGuardia.objects.filter(
        profesor_ausente__centro=centro,
        fecha=fecha_consulta
    ).select_related('profesor_ausente', 'grupo', 'tramo_horario', 'aula')

    guardias_tramo = guardias_dia.filter(tramo_horario=tramo_seleccionado) if tramo_seleccionado else []

    # Profesores disponibles
    disponibles = obtener_profesores_disponibles(tramo_seleccionado, fecha_consulta, centro) if tramo_seleccionado else []

    # Resumen de pendientes/totales para la interfaz
    resumen_tramos = guardias_dia.values('tramo_horario').annotate(
        pendientes=Count('id', filter=Q(estado='PENT')),
        total=Count('id')
    )
    info_tramos = {item['tramo_horario']: item for item in resumen_tramos}

    context = {
        'fecha_consulta': fecha_consulta,
        'tramos_del_dia': tramos_del_dia,
        'tramo_seleccionado': tramo_seleccionado,
        'guardias_tramo': guardias_tramo,
        'profesores_disponibles': disponibles,
        'info_tramos': info_tramos,
        'grupo_etapas': grupo_etapas, # Pasamos el valor actual para mantener seleccionado el select
    }
    return render(request, 'gestion_guardias_global.html', context)



def calcular_porcentaje_compatibilidad(profesores_disponibles, registro, fecha, centro):
    lista_evaluada = []
    tramo = registro.tramo_horario
    grupo_afectado = registro.grupo
    etapa_afectada = grupo_afectado.etapa

    profes_ids = [p.id for p in profesores_disponibles]

    # CORREGIDO: Aislamos por centro a través del profesor
    horarios_profes = Horario.objects.filter(
        profesor__centro=centro,  # <--- EL TRUCO AQUÍ
        profesor_id__in=profes_ids
    ).select_related('grupo')

    datos_docencia = {pid: {'horas_grupo': 0, 'etapas': set()} for pid in profes_ids}
    for h in horarios_profes:
        datos_docencia[h.profesor_id]['etapas'].add(h.grupo.etapa)
        if h.grupo_id == grupo_afectado.id:
            datos_docencia[h.profesor_id]['horas_grupo'] += 1

    # CORREGIDO: Aislamos por centro a través del profesor
    guardias_dict = {
        hg.profesor_id: hg.prioridad
        for hg in HorarioGuardia.objects.filter(profesor__centro=centro, tramo_horario=tramo) # <--- Y AQUÍ
    }

    # ESTO ESTÁ BIEN: SalidaExcursion tiene el campo centro
    grupos_fuera_ids = SalidaExcursion.objects.filter(
        centro=centro,
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha
    ).values_list('grupos_implicados__id', flat=True)

    # CORREGIDO: Aislamos por centro a través del profesor
    liberados_ids = set(Horario.objects.filter(
        profesor__centro=centro,  # <--- Y AQUÍ TAMBIÉN
        tramo_horario=tramo,
        grupo_id__in=grupos_fuera_ids
    ).values_list('profesor_id', flat=True))

    for prof in profesores_disponibles:
        porcentaje = 0

        if prof.id in liberados_ids:
            porcentaje += 70
        elif prof.id in guardias_dict:
            prioridad = guardias_dict[prof.id]
            puntos_base = max(20, 70 - (prioridad * 10))
            porcentaje += puntos_base

        horas_grupo = datos_docencia[prof.id]['horas_grupo']
        if horas_grupo > 0:
            porcentaje += 10
            porcentaje += (horas_grupo * 2)
            prof.conoce_grupo = True
            prof.horas_grupo = horas_grupo
        else:
            prof.conoce_grupo = False
            prof.horas_grupo = 0

        if etapa_afectada in datos_docencia[prof.id]['etapas']:
            porcentaje += 10
            prof.misma_etapa = True
        else:
            prof.misma_etapa = False

        prof.porcentaje = min(100, porcentaje)
        lista_evaluada.append(prof)

    lista_evaluada.sort(key=lambda x: x.porcentaje, reverse=True)

    return lista_evaluada

@login_required
def asignar_guardia(request, registro_id):
    centro = obtener_centro_usuario(request)
    registro = get_object_or_404(RegistroGuardia, id=registro_id, centro=centro)

    if request.method == 'POST':
        profesor_id = request.POST.get('profesor_id')

        if profesor_id:
            # CORREGIDO: Validamos que el profesor que va a cubrir la guardia pertenece a este centro
            profesor = get_object_or_404(Profesor, id=profesor_id, centro=centro)
            registro.profesor_guardia = profesor
            registro.estado = 'COB'
            registro.observaciones = request.POST.get('observaciones', '')
            registro.save()
            messages.success(request, f'Guardia asignada a {profesor.abreviatura}')

        elif 'autogestion' in request.POST:
            registro.profesor_guardia = None
            registro.estado = 'AUTO'
            registro.observaciones = request.POST.get('observaciones', '')
            registro.save()
            messages.info(request, 'Guardia marcada como autogestionada')

        return redirect(f"/gestion-guardias/?fecha={registro.fecha.isoformat()}&tramo={registro.tramo_horario.id}")

    # CORREGIDO: Pasamos el 'centro' a nuestras funciones calculadoras
    disponibles_crudos = obtener_profesores_disponibles(registro.tramo_horario, registro.fecha, centro)
    disponibles_con_porcentaje = calcular_porcentaje_compatibilidad(disponibles_crudos, registro, registro.fecha,
                                                                    centro)

    context = {
        'registro': registro,
        'profesores_disponibles': disponibles_con_porcentaje,
    }
    return render(request, 'asignar_guardia.html', context)


@login_required
@rol_requerido(['ADMIN'])
def crear_cuenta_usuario(request):
    # Obtenemos el centro del admin logueado
    centro_actual = obtener_centro_usuario(request)

    if request.method == 'POST':
        # Le pasamos el centro al formulario
        form = GestorUsuarioForm(request.POST, centro=centro_actual)
        if form.is_valid():
            try:
                with transaction.atomic():
                    nuevo_user = User.objects.create_user(
                        username=form.cleaned_data['username'],
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password']
                    )

                    tipo = form.cleaned_data['tipo']

                    if tipo == 'existente':
                        profesor = form.cleaned_data['profesor_existente']
                        profesor.usuario = nuevo_user
                        if not profesor.email:
                            profesor.email = form.cleaned_data['email']
                        profesor.save()
                        accion_msg = f"vinculado al perfil existente de {profesor.nombre}"

                    else:
                        profesor = Profesor.objects.create(
                            usuario=nuevo_user,
                            nombre=form.cleaned_data['nombre'],
                            apellidos=form.cleaned_data['apellidos'],
                            abreviatura=form.cleaned_data['abreviatura'].upper(),
                            email=form.cleaned_data['email'],
                            rol=form.cleaned_data['rol'],
                            centro=form.cleaned_data['centro']
                        )
                        accion_msg = f"con nuevo perfil creado en {profesor.centro.nombre}"

                messages.success(request, f"✅ Cuenta '{nuevo_user.username}' generada exitosamente y {accion_msg}.")
                return redirect('crear_cuenta_usuario')

            except IntegrityError:
                messages.error(request, "Hubo un error de integridad (Posiblemente el email o username ya existan).")
            except Exception as e:
                messages.error(request, f"Error crítico al guardar: {e}")
    else:
        # En GET, también le pasamos el centro para que cargue bien el desplegable
        form = GestorUsuarioForm(centro=centro_actual)

    return render(request, 'crear_cuenta.html', {'form': form})


@login_required
def cambiar_centro_sesion(request):
    es_admin = request.user.is_superuser or (
            hasattr(request.user, 'perfil_profesor') and request.user.perfil_profesor.rol == 'ADMIN'
    )

    if not es_admin:
        messages.error(request, "No tienes permiso para cambiar de centro.")
        return redirect('pagina_inicio')

    if request.method == 'POST':
        centro_id = request.POST.get('centro_id')
        if centro_id:
            request.session['centro_activo_id'] = int(centro_id)
            messages.success(request, "Vista cambiada al nuevo centro.")
        else:
            # Si eligen la opción en blanco, limpiamos la sesión
            if 'centro_activo_id' in request.session:
                del request.session['centro_activo_id']
                messages.info(request, "Has vuelto a tu centro por defecto.")

    # Redirigimos a la página desde la que el usuario hizo el post (o a inicio si falla)
    next_url = request.META.get('HTTP_REFERER', 'pagina_inicio')
    return redirect(next_url)




@login_required
@solo_directivos
def panel_central_datos(request):
    centro = obtener_centro_usuario(request)
    return render(request, 'centro_datos.html', {'centro': centro})


@login_required
def gestionar_tramos(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar horarios.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN INDIVIDUAL (GET) ---
    tramo_edit_id = request.GET.get('edit')
    tramo_instancia = None
    if tramo_edit_id:
        tramo_instancia = get_object_or_404(TramoHorario, id=tramo_edit_id, centro=centro)

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. ELIMINAR TRAMO
        if action == 'delete':
            tramo_id = request.POST.get('tramo_id')
            tramo_a_borrar = get_object_or_404(TramoHorario, id=tramo_id, centro=centro)
            tramo_a_borrar.delete()
            messages.success(request, "Tramo eliminado correctamente.")
            return redirect('gestionar_tramos')

        # 2. ACTUALIZAR UN ÚNICO TRAMO
        elif action == 'save_single':
            form_individual = TramoIndividualForm(request.POST, instance=tramo_instancia, centro=centro)
            if form_individual.is_valid():
                form_individual.save()
                messages.success(request, "Tramo individual actualizado con éxito.")
                return redirect('gestionar_tramos')

        # 3. GENERADOR MASIVO (Tu código original adaptado)
        elif action == 'generar_masivo':
            form_masivo = GeneradorTramosForm(request.POST, centro=centro)
            inicios = request.POST.getlist('inicio[]')
            fines = request.POST.getlist('fin[]')
            tipos = request.POST.getlist('tipo[]')

            if form_masivo.is_valid() and inicios and fines and tipos:
                datos = form_masivo.cleaned_data
                etapas_seleccionadas = datos['etapas']

                # Lógica de borrado previo
                if datos['borrar_anteriores']:
                    tramos_afectados = TramoHorario.objects.filter(centro=centro,
                                                                   etapas__in=etapas_seleccionadas).distinct()
                    for t in tramos_afectados:
                        t.etapas.remove(*etapas_seleccionadas)
                        if not t.etapas.exists():
                            t.delete()

                dias_semana = ['L', 'M', 'X', 'J', 'V']  # Ajusta si tu modelo usa otros values
                tramos_creados, tramos_actualizados = 0, 0

                for dia in dias_semana:
                    plantilla_diaria = zip(inicios, fines, tipos)
                    for hora_ini, hora_fin, tipo in plantilla_diaria:
                        if not hora_ini or not hora_fin: continue

                        es_recreo = (tipo == 'recreo')
                        tramo, created = TramoHorario.objects.get_or_create(
                            centro=centro, dia_semana=dia, hora_inicio=hora_ini, hora_fin=hora_fin,
                            defaults={'es_recreo': es_recreo}
                        )
                        tramo.etapas.add(*etapas_seleccionadas)

                        if created:
                            tramos_creados += 1
                        else:
                            tramos_actualizados += 1

                messages.success(request,
                                 f"¡Éxito! {tramos_creados} tramos creados y {tramos_actualizados} actualizados.")
                return redirect('gestionar_tramos')
            else:
                messages.error(request, "Debes seleccionar etapas y añadir al menos un tramo válido.")

    # --- INICIALIZACIÓN DE FORMULARIOS PARA GET ---
    form_masivo = GeneradorTramosForm(centro=centro)
    form_individual = TramoIndividualForm(instance=tramo_instancia, centro=centro) if tramo_instancia else None

    # --- LISTADO (Columna Derecha) ---
    tramos = TramoHorario.objects.filter(centro=centro).prefetch_related('etapas').annotate(
        orden_dia=Case(
            When(dia_semana='L', then=Value(1)),
            When(dia_semana='M', then=Value(2)),
            When(dia_semana='X', then=Value(3)),
            When(dia_semana='J', then=Value(4)),
            When(dia_semana='V', then=Value(5)),
            When(dia_semana='S', then=Value(6)),
            When(dia_semana='D', then=Value(7)),
            output_field=IntegerField(),
        )
    ).order_by('orden_dia', 'hora_inicio')

    contexto = {
        'tramos': tramos,
        'form_masivo': form_masivo,
        'form_individual': form_individual,
        'is_edit': bool(tramo_instancia),
        'centro': centro
    }
    return render(request, 'gestionar_tramos.html', contexto)


@login_required
def gestionar_etapas(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar las etapas.")
        return redirect('centro_datos')  # Ajusta al name de tu url principal

    # --- LÓGICA DE EDICIÓN (GET) ---
    etapa_edit_id = request.GET.get('edit')
    etapa_instancia = None
    if etapa_edit_id:
        etapa_instancia = get_object_or_404(Etapa, id=etapa_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        # ELIMINAR
        if action == 'delete':
            etapa_id = request.POST.get('etapa_id')
            etapa_a_borrar = get_object_or_404(Etapa, id=etapa_id, centro=centro)
            try:
                etapa_a_borrar.delete()
                messages.success(request, "Etapa eliminada correctamente.")
            except Exception as e:
                # Fallará si tiene grupos asociados por el on_delete=models.PROTECT
                messages.error(request, "No se puede eliminar la etapa porque ya tiene grupos o tramos asociados.")
            return redirect('gestionar_etapas')

        # CREAR / ACTUALIZAR
        elif action == 'save':
            form = EtapaForm(request.POST, instance=etapa_instancia)
            if form.is_valid():
                nueva_etapa = form.save(commit=False)
                nueva_etapa.centro = centro
                try:
                    nueva_etapa.save()
                    mensaje = "Etapa actualizada con éxito." if etapa_instancia else "Etapa creada con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_etapas')
                except IntegrityError:
                    messages.error(request,
                                   f"Ya existe una etapa con las siglas '{nueva_etapa.siglas}' en este centro.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = EtapaForm(instance=etapa_instancia)

    # --- LISTADO (GET) ---
    etapas = Etapa.objects.filter(centro=centro).order_by('nombre')

    contexto = {
        'etapas': etapas,
        'form': form,
        'is_edit': bool(etapa_instancia),
        'centro': centro
    }
    return render(request, 'gestionar_etapas.html', contexto)


@login_required
def gestionar_grupos(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar los grupos.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN (GET) ---
    grupo_edit_id = request.GET.get('edit')
    grupo_instancia = None
    if grupo_edit_id:
        grupo_instancia = get_object_or_404(Grupo, id=grupo_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        # ELIMINAR
        if action == 'delete':
            grupo_id = request.POST.get('grupo_id')
            grupo_a_borrar = get_object_or_404(Grupo, id=grupo_id, centro=centro)
            try:
                grupo_a_borrar.delete()
                messages.success(request, "Grupo eliminado correctamente.")
            except Exception:
                messages.error(request,
                               "No se puede eliminar el grupo porque tiene alumnos, horarios o guardias asociadas.")
            return redirect('gestionar_grupos')

        # CREAR / ACTUALIZAR
        elif action == 'save':
            # Pasamos el centro al formulario
            form = GrupoForm(request.POST, instance=grupo_instancia, centro=centro)
            if form.is_valid():
                nuevo_grupo = form.save(commit=False)
                nuevo_grupo.centro = centro
                try:
                    nuevo_grupo.save()
                    mensaje = "Grupo actualizado con éxito." if grupo_instancia else "Grupo creado con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_grupos')
                except IntegrityError:
                    messages.error(request,
                                   f"El grupo '{nuevo_grupo.curso} {nuevo_grupo.nombre}' ya existe en esta etapa.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = GrupoForm(instance=grupo_instancia, centro=centro)

    # --- LISTADO (GET) ---
    # Usamos select_related para traer la etapa de golpe y ordenamos jerárquicamente
    grupos = Grupo.objects.filter(centro=centro).select_related('etapa').order_by('etapa__nombre', 'curso', 'nombre')

    contexto = {
        'grupos': grupos,
        'form': form,
        'is_edit': bool(grupo_instancia),
        'centro': centro
    }
    return render(request, 'gestionar_grupos.html', contexto)


@login_required
def gestionar_materias(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar las materias.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN (GET) ---
    materia_edit_id = request.GET.get('edit')
    materia_instancia = None
    if materia_edit_id:
        materia_instancia = get_object_or_404(Materia, id=materia_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        # ELIMINAR
        if action == 'delete':
            materia_id = request.POST.get('materia_id')
            materia_a_borrar = get_object_or_404(Materia, id=materia_id, centro=centro)
            try:
                materia_a_borrar.delete()
                messages.success(request, "Materia eliminada correctamente.")
            except Exception:
                messages.error(request, "No se puede eliminar la materia porque tiene horarios o guardias asociadas.")
            return redirect('gestionar_materias')

        # CREAR / ACTUALIZAR
        elif action == 'save':
            form = MateriaForm(request.POST, instance=materia_instancia)
            if form.is_valid():
                nueva_materia = form.save(commit=False)
                nueva_materia.centro = centro
                try:
                    nueva_materia.save()
                    mensaje = "Materia actualizada con éxito." if materia_instancia else "Materia creada con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_materias')
                except IntegrityError:
                    messages.error(request,
                                   f"Ya existe una materia con la abreviatura '{nueva_materia.abrev}' en el centro.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = MateriaForm(instance=materia_instancia)

    # --- LISTADO (GET) ---
    materias = Materia.objects.filter(centro=centro).order_by('nombre')

    contexto = {
        'materias': materias,
        'form': form,
        'is_edit': bool(materia_instancia),
        'centro': centro
    }
    return render(request, 'gestionar_materias.html', contexto)


@login_required
def gestionar_aulas(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar las aulas.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN (GET) ---
    aula_edit_id = request.GET.get('edit')
    aula_instancia = None
    if aula_edit_id:
        aula_instancia = get_object_or_404(Aula, id=aula_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        # ELIMINAR
        if action == 'delete':
            aula_id = request.POST.get('aula_id')
            aula_a_borrar = get_object_or_404(Aula, id=aula_id, centro=centro)
            try:
                aula_a_borrar.delete()
                messages.success(request, "Aula eliminada correctamente.")
            except Exception:
                messages.error(request, "No se puede eliminar el aula porque tiene horarios o guardias asociadas.")
            return redirect('gestionar_aulas')

        # CREAR / ACTUALIZAR
        elif action == 'save':
            form = AulaForm(request.POST, instance=aula_instancia)
            if form.is_valid():
                nueva_aula = form.save(commit=False)
                nueva_aula.centro = centro
                try:
                    nueva_aula.save()
                    mensaje = "Aula actualizada con éxito." if aula_instancia else "Aula creada con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_aulas')
                except IntegrityError:
                    messages.error(request, f"Ya existe una aula con la abreviatura '{nueva_aula.abrev}' en el centro.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = AulaForm(instance=aula_instancia)

    # --- LISTADO (GET) ---
    # Ordenamos por pabellón primero, para que salgan agrupadas visualmente
    aulas = Aula.objects.filter(centro=centro).order_by('pabellon', 'nombre')

    contexto = {
        'aulas': aulas,
        'form': form,
        'is_edit': bool(aula_instancia),
        'centro': centro
    }
    return render(request, 'gestionar_aulas.html', contexto)


@login_required
def gestionar_horarios(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar los horarios.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN (GET) ---
    horario_edit_id = request.GET.get('edit')
    horario_instancia = None
    if horario_edit_id:
        horario_instancia = get_object_or_404(Horario, id=horario_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete':
            horario_id = request.POST.get('horario_id')
            horario_a_borrar = get_object_or_404(Horario, id=horario_id, centro=centro)
            horario_a_borrar.delete()
            messages.success(request, "Asignación de horario eliminada correctamente.")
            return redirect('gestionar_horarios')

        elif action == 'save':
            form = HorarioForm(request.POST, instance=horario_instancia, centro=centro)
            if form.is_valid():
                nuevo_horario = form.save(commit=False)
                nuevo_horario.centro = centro
                try:
                    nuevo_horario.save()
                    mensaje = "Horario actualizado con éxito." if horario_instancia else "Asignación creada con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_horarios')
                except IntegrityError:
                    messages.error(request, "Ya existe un conflicto con esta asignación horaria.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = HorarioForm(instance=horario_instancia, centro=centro)

    # --- CAPTURA DE FILTROS AVANZADOS (GET) ---
    f_dia = request.GET.get('f_dia', '')
    f_etapa = request.GET.get('f_etapa', '')
    f_grupo = request.GET.get('f_grupo', '')
    f_materia = request.GET.get('f_materia', '')
    f_profesor = request.GET.get('f_profesor', '')

    horarios_base = Horario.objects.filter(centro=centro)

    if f_dia:
        horarios_base = horarios_base.filter(tramo_horario__dia_semana=f_dia)
    if f_etapa:
        horarios_base = horarios_base.filter(grupo__etapa_id=f_etapa)
    if f_grupo:
        horarios_base = horarios_base.filter(grupo_id=f_grupo)
    if f_materia:
        horarios_base = horarios_base.filter(materia_id=f_materia)
    if f_profesor:
        horarios_base = horarios_base.filter(profesor_id=f_profesor)

    # --- LISTADO OPTIMIZADO Y ORDENADO ---
    horarios_completos = horarios_base.annotate(
        orden_dia=Case(
            When(tramo_horario__dia_semana='L', then=Value(1)),
            When(tramo_horario__dia_semana='M', then=Value(2)),
            When(tramo_horario__dia_semana='X', then=Value(3)),
            When(tramo_horario__dia_semana='J', then=Value(4)),
            When(tramo_horario__dia_semana='V', then=Value(5)),
            When(tramo_horario__dia_semana='S', then=Value(6)),
            When(tramo_horario__dia_semana='D', then=Value(7)),
            output_field=IntegerField(),
        )
    ).order_by('orden_dia', 'tramo_horario__hora_inicio', 'grupo__nombre')

    # --- PAGINACIÓN ---
    paginator = Paginator(horarios_completos, 50)  # Muestra 50 registros por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Preparamos la URL base de los filtros para no perderlos al cambiar de página
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_params = query_params.urlencode()  # Ej: "f_dia=L&f_grupo=3"

    contexto = {
        'page_obj': page_obj,  # Cambiamos 'horarios' por 'page_obj'
        'url_params': url_params,  # Lo mandamos a la plantilla
        'form': form,
        'is_edit': bool(horario_instancia),
        'centro': centro,
        'dias_choices': TramoHorario.DIAS_CHOICES,
        'etapas_list': Etapa.objects.filter(centro=centro),
        'grupos_list': Grupo.objects.filter(centro=centro).order_by('curso', 'nombre'),
        'materias_list': Materia.objects.filter(centro=centro).order_by('nombre'),
        'profesores_list': Profesor.objects.filter(centro=centro),
        'current_filters': request.GET,
    }
    return render(request, 'gestionar_horarios.html', contexto)


@login_required
def gestionar_guardias(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar las guardias.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN (GET) ---
    guardia_edit_id = request.GET.get('edit')
    guardia_instancia = None
    if guardia_edit_id:
        guardia_instancia = get_object_or_404(HorarioGuardia, id=guardia_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete':
            guardia_id = request.POST.get('guardia_id')
            guardia_a_borrar = get_object_or_404(HorarioGuardia, id=guardia_id, centro=centro)
            guardia_a_borrar.delete()
            messages.success(request, "Guardia eliminada correctamente.")
            return redirect('gestionar_guardias')

        elif action == 'save':
            form = HorarioGuardiaForm(request.POST, instance=guardia_instancia, centro=centro)
            if form.is_valid():
                nueva_guardia = form.save(commit=False)
                nueva_guardia.centro = centro
                try:
                    nueva_guardia.save()
                    mensaje = "Guardia actualizada con éxito." if guardia_instancia else "Guardia creada con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_guardias')
                except IntegrityError:
                    messages.error(request, "Error al guardar la guardia.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = HorarioGuardiaForm(instance=guardia_instancia, centro=centro)

    # --- CAPTURA DE FILTROS AVANZADOS (GET) ---
    f_dia = request.GET.get('f_dia', '')
    f_etapa = request.GET.get('f_etapa', '')
    f_profesor = request.GET.get('f_profesor', '')
    f_tipo = request.GET.get('f_tipo', '')  # Búsqueda de texto para el tipo de guardia

    guardias_base = HorarioGuardia.objects.filter(centro=centro)

    if f_dia:
        guardias_base = guardias_base.filter(tramo_horario__dia_semana=f_dia)
    if f_etapa:
        guardias_base = guardias_base.filter(tramo_horario__etapas__id=f_etapa)
    if f_profesor:
        guardias_base = guardias_base.filter(profesor_id=f_profesor)
    if f_tipo:
        guardias_base = guardias_base.filter(tipo_guardia__icontains=f_tipo)

    # --- LISTADO OPTIMIZADO Y ORDENADO ---
    guardias_completas = guardias_base.annotate(
        orden_dia=Case(
            When(tramo_horario__dia_semana='L', then=Value(1)),
            When(tramo_horario__dia_semana='M', then=Value(2)),
            When(tramo_horario__dia_semana='X', then=Value(3)),
            When(tramo_horario__dia_semana='J', then=Value(4)),
            When(tramo_horario__dia_semana='V', then=Value(5)),
            When(tramo_horario__dia_semana='S', then=Value(6)),
            When(tramo_horario__dia_semana='D', then=Value(7)),
            output_field=IntegerField(),
        )
    ).order_by('orden_dia', 'tramo_horario__hora_inicio', '-prioridad', 'profesor__nombre')

    # --- PAGINACIÓN ---
    paginator = Paginator(guardias_completas.distinct(), 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Conservar filtros en la paginación
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_params = query_params.urlencode()

    contexto = {
        'page_obj': page_obj,
        'url_params': url_params,
        'form': form,
        'is_edit': bool(guardia_instancia),
        'centro': centro,
        'dias_choices': TramoHorario.DIAS_CHOICES,
        'etapas_list': Etapa.objects.filter(centro=centro),
        'profesores_list': Profesor.objects.filter(centro=centro),
        'current_filters': request.GET,
    }
    return render(request, 'gestionar_guardias.html', contexto)


@login_required
def gestionar_profesores(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro antes de gestionar el profesorado.")
        return redirect('centro_datos')

    # --- LÓGICA DE EDICIÓN (GET) ---
    profesor_edit_id = request.GET.get('edit')
    profesor_instancia = None
    if profesor_edit_id:
        profesor_instancia = get_object_or_404(Profesor, id=profesor_edit_id, centro=centro)

    # --- LÓGICA DE PROCESAMIENTO (POST) ---
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete':
            profesor_id = request.POST.get('profesor_id')
            profesor_a_borrar = get_object_or_404(Profesor, id=profesor_id, centro=centro)
            profesor_a_borrar.delete()
            messages.success(request, "Profesor eliminado correctamente.")
            return redirect('gestionar_profesores')

        elif action == 'save':
            form = ProfesorForm(request.POST, instance=profesor_instancia, centro=centro)
            if form.is_valid():
                nuevo_profesor = form.save(commit=False)
                nuevo_profesor.centro = centro
                try:
                    nuevo_profesor.save()
                    mensaje = "Datos del profesor actualizados con éxito." if profesor_instancia else "Profesor registrado con éxito."
                    messages.success(request, mensaje)
                    return redirect('gestionar_profesores')
                except IntegrityError:
                    messages.error(request,
                                   "Error al guardar. Es posible que el usuario ya esté vinculado a otro profesor.")
            else:
                messages.error(request, "Revisa los errores en el formulario.")
    else:
        form = ProfesorForm(instance=profesor_instancia, centro=centro)

    # --- CAPTURA DE FILTROS AVANZADOS (GET) ---
    f_texto = request.GET.get('f_texto', '')
    f_rol = request.GET.get('f_rol', '')

    profesores_base = Profesor.objects.filter(centro=centro)

    if f_texto:
        profesores_base = profesores_base.filter(
            Q(nombre__icontains=f_texto) |
            Q(apellidos__icontains=f_texto) |
            Q(abreviatura__icontains=f_texto)
        )
    if f_rol:
        profesores_base = profesores_base.filter(rol=f_rol)

    # --- LISTADO ORDENADO ---
    profesores_completos = profesores_base.order_by('apellidos', 'nombre')

    # --- PAGINACIÓN ---
    paginator = Paginator(profesores_completos, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Conservar filtros en la paginación
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    url_params = query_params.urlencode()

    contexto = {
        'page_obj': page_obj,
        'url_params': url_params,
        'form': form,
        'is_edit': bool(profesor_instancia),
        'centro': centro,
        'roles_choices': Profesor.ROLES_CHOICES,
        'current_filters': request.GET,
    }
    return render(request, 'gestionar_profesores.html', contexto)