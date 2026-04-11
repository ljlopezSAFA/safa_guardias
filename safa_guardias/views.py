import csv
import io
from datetime import datetime, timedelta, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from .decorators import rol_requerido, solo_directivos
from .forms import *
from .utils import obtener_centro_usuario


# Create your views here.
@login_required  # NUEVO: Protegemos la vista
def pagina_inicio(request):
    centro = obtener_centro_usuario(request)

    # Si no tiene centro (y no es superadmin), lo mandamos a un error
    if not centro and not request.user.is_superuser:
        messages.error(request, "Tu usuario no tiene un centro escolar asignado.")
        return redirect('logout')  # O a una página de error genérica

    ahora = timezone.localtime(timezone.now())
    fecha_hoy = ahora.date()
    hora_actual = ahora.time()

    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_hoy.weekday()]

    # CORREGIDO: Filtramos el tramo por el centro actual
    tramo_actual = TramoHorario.objects.filter(
        centro=centro,  # <--- Aislamos los datos
        dia_semana=dia_sem,
        hora_inicio__lte=hora_actual,
        hora_fin__gte=hora_actual
    ).first()

    # CORREGIDO: Pasamos el centro a las funciones externas (tendrás que actualizar estas funciones también)
    if tramo_actual:
        generar_guardias_del_dia(fecha_hoy, centro)

    # CORREGIDO: Filtramos por centro
    guardias_pendientes = RegistroGuardia.objects.filter(
        centro=centro,  # <--- Aislamos los datos
        fecha=fecha_hoy,
        tramo_horario=tramo_actual
    ).select_related('profesor_ausente', 'grupo', 'aula') if tramo_actual else []

    disponibles = obtener_profesores_disponibles(tramo_actual, fecha_hoy, centro) if tramo_actual else []

    context = {
        'tramo_actual': tramo_actual,
        'guardias_pendientes': guardias_pendientes,
        'profesores_disponibles': disponibles,
        'hora_servidor_iso': ahora.isoformat(),
        'conteo_pendientes': len([g for g in guardias_pendientes if g.estado == 'PENT']) if tramo_actual else 0
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

    etapas = Grupo.ETAPAS_CHOICES
    grupos = Grupo.objects.filter(centro=centro).order_by('etapa', 'curso', 'nombre')
    profesores = Profesor.objects.filter(centro=centro).order_by('apellidos')
    materias_todas = Materia.objects.filter(centro=centro)

    grupo_id = request.GET.get('grupo')
    profesor_id = request.GET.get('profesor')
    etapa_seleccionada = request.GET.get('etapa')

    # Sacamos las horas únicas para pintar las filas de la tabla
    tramos = TramoHorario.objects.filter(centro=centro).order_by('hora_inicio')
    horas_filas = []
    seen_horas = set()
    for t in tramos:
        if (t.hora_inicio, t.hora_fin) not in seen_horas:
            horas_filas.append(t)
            seen_horas.add((t.hora_inicio, t.hora_fin))

    dias_semana = ['L', 'M', 'X', 'J', 'V']
    horario_tabla = []
    entidad_nombre = ""

    num_clases = 0
    num_guardias = 0
    total_horas = 0

    if profesor_id:
        # 1. Ya comprobamos aquí que el profe es de este centro (Seguridad lista)
        p = get_object_or_404(Profesor, id=profesor_id, centro=centro)
        entidad_nombre = f"Horario de: {p.apellidos}, {p.nombre}"

        # 2. Eliminamos "centro=centro" de aquí.
        clases = Horario.objects.filter(profesor=p).select_related('materia', 'aula', 'grupo', 'tramo_horario')
        guardias = HorarioGuardia.objects.filter(profesor=p).select_related('tramo_horario')

        num_clases = clases.values('tramo_horario').distinct().count()
        num_guardias = guardias.values('tramo_horario').distinct().count()
        total_horas = num_clases + num_guardias

        for tramo in horas_filas:
            fila = {'tramo': tramo, 'celdas': []}
            for dia in dias_semana:
                c_celda = [c for c in clases if
                           c.tramo_horario.hora_inicio == tramo.hora_inicio and c.tramo_horario.dia_semana == dia]
                g_celda = [g for g in guardias if
                           g.tramo_horario.hora_inicio == tramo.hora_inicio and g.tramo_horario.dia_semana == dia]
                fila['celdas'].append({'clases': c_celda, 'guardias': g_celda})
            horario_tabla.append(fila)

    elif grupo_id:
        # 1. Comprobamos que el grupo es de este centro
        g = get_object_or_404(Grupo, id=grupo_id, centro=centro)
        entidad_nombre = f"Horario de: {g.curso} {g.nombre}"

        # 2. Eliminamos "centro=centro" de aquí
        clases = Horario.objects.filter(grupo=g).select_related('materia', 'profesor', 'aula', 'tramo_horario')

        for tramo in horas_filas:
            fila = {'tramo': tramo, 'celdas': []}
            for dia in dias_semana:
                c_celda = [c for c in clases if
                           c.tramo_horario.hora_inicio == tramo.hora_inicio and c.tramo_horario.dia_semana == dia]
                fila['celdas'].append({'clases': c_celda, 'guardias': []})
            horario_tabla.append(fila)

    return render(request, 'visor_horarios.html', {
        'etapas': etapas,
        'grupos': grupos,
        'profesores': profesores,
        'materias_todas': materias_todas,
        'horario_tabla': horario_tabla,
        'dias_semana': dias_semana,
        'grupo_seleccionado': int(grupo_id) if grupo_id and grupo_id.isdigit() else None,
        'profesor_seleccionado': int(profesor_id) if profesor_id and profesor_id.isdigit() else None,
        'etapa_seleccionada': etapa_seleccionada,
        'entidad_nombre': entidad_nombre,
        'num_clases': num_clases,
        'num_guardias': num_guardias,
        'total_horas': total_horas,
    })


@login_required
def visor_guardias(request):
    centro = obtener_centro_usuario(request)

    tramos_referencia = TramoHorario.objects.filter(centro=centro).values('hora_inicio',
                                                                          'hora_fin').distinct().order_by('hora_inicio')

    dias = ['L', 'M', 'X', 'J', 'V']
    cuadrante = []

    for tramo in tramos_referencia:
        fila = {
            'inicio': tramo['hora_inicio'],
            'fin': tramo['hora_fin'],
            'columnas': []
        }

        for dia in dias:
            # CORREGIDO: Filtramos a través del profesor para asegurar el centro
            guardias_celda = HorarioGuardia.objects.filter(
                profesor__centro=centro,  # <--- EL TRUCO ESTÁ AQUÍ
                tramo_horario__hora_inicio=tramo['hora_inicio'],
                tramo_horario__dia_semana=dia
            ).select_related('profesor')

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
        # ¡IMPORTANTE! Pasamos centro=centro aquí
        form = BajaProfesorForm(request.POST, instance=baja, centro=centro)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.centro = centro
            obj.save()

            messages.success(request, f"Baja {'actualizada' if pk else 'registrada'} correctamente.")
            return redirect('gestion_ausencias')
    else:
        # ¡Y AQUÍ TAMBIÉN! Para cuando cargamos el formulario vacío
        form = BajaProfesorForm(instance=baja, centro=centro)

    return render(request, 'formulario_ausencias.html',
                  {'form': form, 'titulo': titulo, 'icono': 'bi-person-dash-fill', 'color': 'danger'})


@login_required
def eliminar_baja(request, pk):
    centro = obtener_centro_usuario(request)
    baja = get_object_or_404(BajaProfesor, pk=pk, centro=centro)
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
        # ¡Añadimos centro=centro!
        form = SalidaExcursionForm(request.POST, instance=salida, centro=centro)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.centro = centro
            obj.save()
            form.save_m2m()

            messages.success(request, f"Excursión {'actualizada' if pk else 'programada'} correctamente.")
            return redirect('gestion_ausencias')
    else:
        # ¡Añadimos centro=centro!
        form = SalidaExcursionForm(instance=salida, centro=centro)

    return render(request, 'formulario_ausencias.html',
                  {'form': form, 'titulo': titulo, 'icono': 'bi-bus-front-fill', 'color': 'success'})


@login_required
def eliminar_salida(request, pk):
    centro = obtener_centro_usuario(request)
    salida = get_object_or_404(SalidaExcursion, pk=pk, centro=centro)
    salida.delete()
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
@login_required
def gestionar_ausencia_puntual(request, pk=None):
    centro = obtener_centro_usuario(request)
    ausencia = get_object_or_404(AusenciaPuntual, pk=pk, centro=centro) if pk else None

    if request.method == 'POST':
        # ¡Añadimos centro=centro!
        form = AusenciaPuntualForm(request.POST, instance=ausencia, centro=centro)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.centro = centro
            obj.save()

            messages.success(request, "Ausencia puntual registrada.")
            return redirect('gestion_ausencias')
    else:
        # ¡Añadimos centro=centro!
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


# --- VISTAS ---

@login_required
def gestion_guardias_global(request):
    centro = obtener_centro_usuario(request)

    fecha_str = request.GET.get('fecha')
    tramo_id = request.GET.get('tramo')

    if fecha_str:
        try:
            fecha_consulta = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_consulta = timezone.localtime().date()
    else:
        fecha_consulta = timezone.localtime().date()

    dias_map = {0: 'L', 1: 'M', 2: 'X', 3: 'J', 4: 'V', 5: 'S', 6: 'D'}
    dia_sem = dias_map[fecha_consulta.weekday()]

    # Tramos del día para este centro
    tramos_del_dia = TramoHorario.objects.filter(centro=centro, dia_semana=dia_sem).order_by('hora_inicio')

    tramo_seleccionado = None
    if tramo_id:
        tramo_seleccionado = tramos_del_dia.filter(id=tramo_id).first()

    if not tramo_seleccionado and tramos_del_dia.exists():
        tramo_seleccionado = tramos_del_dia.first()

    # Función que asumo tienes en otro lado para generar los registros vacíos
    generar_guardias_del_dia(fecha_consulta, centro)

    # Guardias de ese centro (filtradas por el centro del profesor ausente)
    guardias_dia = RegistroGuardia.objects.filter(
        profesor_ausente__centro=centro,  # CORREGIDO
        fecha=fecha_consulta
    ).select_related('profesor_ausente', 'grupo', 'tramo_horario')

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
    if request.method == 'POST':
        form = GestorUsuarioForm(request.POST)
        if form.is_valid():
            try:
                # Transacción atómica: Si falla algo, revierte los cambios (no crea un User fantasma)
                with transaction.atomic():
                    # 1. Crear el usuario (Django cifra la contraseña automáticamente con create_user)
                    nuevo_user = User.objects.create_user(
                        username=form.cleaned_data['username'],
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password']
                    )

                    tipo = form.cleaned_data['tipo']

                    # 2. Lógica según la opción elegida
                    if tipo == 'existente':
                        profesor = form.cleaned_data['profesor_existente']
                        profesor.usuario = nuevo_user
                        # Sincronizamos el email del perfil si no lo tenía
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
                return redirect('crear_cuenta_usuario')  # Recargar el formulario limpio

            except IntegrityError:
                messages.error(request, "Hubo un error de integridad (Posiblemente el email o username ya existan).")
            except Exception as e:
                messages.error(request, f"Error crítico al guardar: {e}")
    else:
        form = GestorUsuarioForm()

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
@solo_directivos
def generar_tramos_masivos(request):
    centro = obtener_centro_usuario(request)
    if not centro:
        messages.error(request, "Selecciona un centro en la barra superior antes de generar tramos.")
        return redirect('centro_datos')

    if request.method == 'POST':
        form = GeneradorTramosForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            if datos['borrar_anteriores']:
                TramoHorario.objects.filter(centro=centro).delete()

            dias_semana = ['L', 'M', 'X', 'J', 'V']
            tramos_creados = 0
            hoy = date.today()
            inicio_jornada = datetime.combine(hoy, datos['hora_inicio_jornada'])
            fin_jornada = datetime.combine(hoy, datos['hora_fin_jornada'])
            inicio_recreo = datetime.combine(hoy, datos['hora_inicio_recreo'])
            fin_recreo = datetime.combine(hoy, datos['hora_fin_recreo'])
            duracion = timedelta(minutes=datos['duracion_minutos'])

            for dia in dias_semana:
                hora_actual = inicio_jornada
                while hora_actual < fin_jornada:
                    if hora_actual == inicio_recreo:
                        TramoHorario.objects.create(
                            centro=centro, dia_semana=dia,
                            hora_inicio=hora_actual.time(), hora_fin=fin_recreo.time(),
                            descripcion="Recreo"
                        )
                        tramos_creados += 1
                        hora_actual = fin_recreo
                        continue

                    hora_fin_clase = hora_actual + duracion
                    if hora_fin_clase > fin_jornada:
                        hora_fin_clase = fin_jornada

                    TramoHorario.objects.create(
                        centro=centro, dia_semana=dia,
                        hora_inicio=hora_actual.time(), hora_fin=hora_fin_clase.time()
                    )
                    tramos_creados += 1
                    hora_actual = hora_fin_clase

            messages.success(request, f"¡Éxito! {tramos_creados} tramos generados.")
            return redirect('centro_datos')
    else:
        form = GeneradorTramosForm()
    return render(request, 'generador_tramos.html', {'form': form, 'centro': centro})