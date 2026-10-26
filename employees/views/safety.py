"""
Safety module views.
Roles:
    Manager    → full access
    Accountant → view + add (report events)
    Viewer     → view only
"""
from datetime import date as date_today, timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..decorators import role_required
from ..models import (
    Employee, Hazard, Mine, PPEIssuance, SafetyIncident,
    SafetyInspection, SafetyTraining,
)
from ..safety_forms import (
    HazardForm, PPEIssuanceForm, SafetyIncidentForm,
    SafetyInspectionForm, SafetyTrainingForm,
)
from .notifications import notify_managers


# =====================================================================
# SAFETY HUB — the landing page
# =====================================================================
@role_required('Manager', 'Accountant', 'Viewer')
def safety_hub(request):
    today = date_today.today()
    this_month_start = today.replace(day=1)

    # Star metrics
    last_incident = SafetyIncident.objects.order_by('-date').first()
    days_since_incident = (today - last_incident.date).days if last_incident else None

    last_lti = SafetyIncident.objects.filter(
        severity__in=['Serious', 'Critical', 'Fatal']
    ).order_by('-date').first()
    days_since_lti = (today - last_lti.date).days if last_lti else None

    # Counts
    open_hazards_qs = Hazard.objects.filter(status__in=['Open', 'In Progress'])
    open_hazards_count = open_hazards_qs.count()
    critical_hazards_count = open_hazards_qs.filter(
        risk_level__in=['Critical', 'High']
    ).count()

    incidents_this_month = SafetyIncident.objects.filter(date__gte=this_month_start).count()
    hazards_this_month = Hazard.objects.filter(date_observed__gte=this_month_start).count()

    # Warnings
    ppe_expiring = PPEIssuance.objects.filter(
        replacement_due__isnull=False,
        replacement_due__gte=today,
        replacement_due__lte=today + timedelta(days=30),
        returned=False,
    ).select_related('employee').order_by('replacement_due')[:10]

    training_expiring = SafetyTraining.objects.filter(
        expiry_date__isnull=False,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=30),
    ).select_related('employee').order_by('expiry_date')[:10]

    inspections_upcoming = SafetyInspection.objects.filter(
        follow_up_required=True,
        follow_up_deadline__isnull=False,
        follow_up_deadline__gte=today,
        follow_up_deadline__lte=today + timedelta(days=7),
    ).order_by('follow_up_deadline')[:10]

    recent_incidents = SafetyIncident.objects.select_related(
        'mine', 'employee'
    ).order_by('-date')[:5]

    return render(request, 'safety/hub.html', {
        'days_since_incident': days_since_incident,
        'days_since_lti': days_since_lti,
        'open_hazards_count': open_hazards_count,
        'critical_hazards_count': critical_hazards_count,
        'incidents_this_month': incidents_this_month,
        'hazards_this_month': hazards_this_month,
        'ppe_expiring': ppe_expiring,
        'training_expiring': training_expiring,
        'inspections_upcoming': inspections_upcoming,
        'recent_incidents': recent_incidents,
        'today': today,
    })


# =====================================================================
# SAFETY INCIDENTS
# =====================================================================
@role_required('Manager', 'Accountant', 'Viewer')
def incident_list(request):
    status_filter = request.GET.get('status', '')
    severity_filter = request.GET.get('severity', '')
    type_filter = request.GET.get('type', '')
    mine_filter = request.GET.get('mine', '')

    incidents = SafetyIncident.objects.select_related('mine', 'employee')
    if status_filter:
        incidents = incidents.filter(status=status_filter)
    if severity_filter:
        incidents = incidents.filter(severity=severity_filter)
    if type_filter:
        incidents = incidents.filter(incident_type=type_filter)
    if mine_filter:
        incidents = incidents.filter(mine_id=mine_filter)

    return render(request, 'safety/incidents/list.html', {
        'incidents': incidents,
        'status_filter': status_filter,
        'severity_filter': severity_filter,
        'type_filter': type_filter,
        'mine_filter': mine_filter,
        'mines': Mine.objects.filter(voided=False),
        'status_choices': SafetyIncident.STATUS_CHOICES,
        'severity_choices': SafetyIncident.SEVERITY_CHOICES,
        'type_choices': SafetyIncident.INCIDENT_TYPE_CHOICES,
    })


@role_required('Manager', 'Accountant', 'Viewer')
def incident_detail(request, pk):
    incident = get_object_or_404(SafetyIncident, pk=pk)
    return render(request, 'safety/incidents/detail.html', {'incident': incident})


@role_required('Manager', 'Accountant')
def incident_add(request):
    if request.method == 'POST':
        form = SafetyIncidentForm(request.POST, request.FILES)
        if form.is_valid():
            incident = form.save(commit=False)
            incident.reported_by = request.user
            incident.save()

            if incident.severity in ('Serious', 'Critical', 'Fatal'):
                notify_managers(
                    f'⚠️ {incident.severity.upper()} incident {incident.incident_no} '
                    f'reported at {incident.mine.name}.',
                    link=f'/safety/incidents/{incident.pk}/',
                )
            else:
                notify_managers(
                    f'New incident {incident.incident_no} reported at {incident.mine.name}.',
                    link=f'/safety/incidents/{incident.pk}/',
                )

            messages.success(request, f'Incident {incident.incident_no} recorded.')
            return redirect('incident_detail', pk=incident.pk)
    else:
        initial = {
            'date': date_today.today(),
            'time': timezone.localtime().time().replace(second=0, microsecond=0),
            'status': 'Reported',
        }
        last = SafetyIncident.objects.order_by('-created_at').first()
        if last:
            initial['mine'] = last.mine
            initial['shift'] = last.shift
        form = SafetyIncidentForm(initial=initial)

    return render(request, 'safety/incidents/form.html', {
        'form': form,
        'title': 'Report Safety Incident',
    })


@role_required('Manager')
def incident_edit(request, pk):
    incident = get_object_or_404(SafetyIncident, pk=pk)
    if request.method == 'POST':
        form = SafetyIncidentForm(request.POST, request.FILES, instance=incident)
        if form.is_valid():
            inc = form.save(commit=False)
            if inc.status in ('Investigating', 'Action Pending', 'Resolved', 'Closed') and not inc.investigated_by:
                inc.investigated_by = request.user
            if inc.status in ('Resolved', 'Closed') and not inc.resolved_at:
                inc.resolved_at = timezone.now()
            inc.save()
            messages.success(request, f'Incident {incident.incident_no} updated.')
            return redirect('incident_detail', pk=incident.pk)
    else:
        form = SafetyIncidentForm(instance=incident)

    return render(request, 'safety/incidents/form.html', {
        'form': form,
        'title': f'Edit {incident.incident_no}',
        'incident': incident,
    })


@role_required('Manager')
def incident_close(request, pk):
    incident = get_object_or_404(SafetyIncident, pk=pk)

    if incident.status == 'Closed':
        messages.warning(request, 'This incident is already closed.')
        return redirect('incident_detail', pk=incident.pk)

    if request.method == 'POST':
        notes = request.POST.get('closure_notes', '').strip()
        if notes:
            incident.corrective_action = (
                (incident.corrective_action or '') + '\n\n' + notes
            ).strip()
        incident.status = 'Closed'
        incident.resolved_at = timezone.now()
        incident.investigated_by = request.user
        incident.save()
        messages.success(request, f'Incident {incident.incident_no} closed.')
        return redirect('incident_detail', pk=incident.pk)

    return render(request, 'safety/incidents/close.html', {'incident': incident})


# =====================================================================
# HAZARDS
# =====================================================================
@role_required('Manager', 'Accountant', 'Viewer')
def hazard_list(request):
    status_filter = request.GET.get('status', '')
    risk_filter = request.GET.get('risk', '')
    mine_filter = request.GET.get('mine', '')

    hazards = Hazard.objects.select_related('mine', 'assigned_to')
    if status_filter:
        hazards = hazards.filter(status=status_filter)
    if risk_filter:
        hazards = hazards.filter(risk_level=risk_filter)
    if mine_filter:
        hazards = hazards.filter(mine_id=mine_filter)

    return render(request, 'safety/hazards/list.html', {
        'hazards': hazards,
        'status_filter': status_filter,
        'risk_filter': risk_filter,
        'mine_filter': mine_filter,
        'mines': Mine.objects.filter(voided=False),
        'status_choices': Hazard.STATUS_CHOICES,
        'risk_choices': Hazard.RISK_LEVEL_CHOICES,
    })


@role_required('Manager', 'Accountant', 'Viewer')
def hazard_detail(request, pk):
    hazard = get_object_or_404(Hazard, pk=pk)
    return render(request, 'safety/hazards/detail.html', {'hazard': hazard})


@role_required('Manager', 'Accountant')
def hazard_add(request):
    if request.method == 'POST':
        form = HazardForm(request.POST, request.FILES)
        if form.is_valid():
            hazard = form.save(commit=False)
            hazard.observed_by = request.user
            hazard.save()

            if hazard.risk_level in ('Critical', 'High'):
                notify_managers(
                    f'⚠️ {hazard.risk_level.upper()} RISK hazard {hazard.hazard_no} '
                    f'identified at {hazard.mine.name}.',
                    link=f'/safety/hazards/{hazard.pk}/',
                )
            else:
                notify_managers(
                    f'New hazard {hazard.hazard_no} identified at {hazard.mine.name}.',
                    link=f'/safety/hazards/{hazard.pk}/',
                )

            messages.success(request, f'Hazard {hazard.hazard_no} recorded.')
            return redirect('hazard_detail', pk=hazard.pk)
    else:
        initial = {'date_observed': date_today.today(), 'status': 'Open'}
        form = HazardForm(initial=initial)

    return render(request, 'safety/hazards/form.html', {
        'form': form, 'title': 'Report Hazard',
    })


@role_required('Manager')
def hazard_edit(request, pk):
    hazard = get_object_or_404(Hazard, pk=pk)
    if request.method == 'POST':
        form = HazardForm(request.POST, request.FILES, instance=hazard)
        if form.is_valid():
            h = form.save(commit=False)
            if h.status == 'Resolved' and not h.resolved_at:
                h.resolved_at = timezone.now()
            h.save()
            messages.success(request, f'Hazard {hazard.hazard_no} updated.')
            return redirect('hazard_detail', pk=hazard.pk)
    else:
        form = HazardForm(instance=hazard)
    return render(request, 'safety/hazards/form.html', {
        'form': form, 'title': f'Edit {hazard.hazard_no}', 'hazard': hazard,
    })


@role_required('Manager')
def hazard_resolve(request, pk):
    hazard = get_object_or_404(Hazard, pk=pk)
    if hazard.status in ('Resolved', 'Closed'):
        messages.warning(request, 'This hazard is already resolved.')
        return redirect('hazard_detail', pk=hazard.pk)

    if request.method == 'POST':
        notes = request.POST.get('resolution_notes', '').strip()
        if not notes:
            messages.error(request, 'Please describe how the hazard was resolved.')
            return redirect('hazard_resolve', pk=hazard.pk)
        hazard.action_taken = ((hazard.action_taken or '') + '\n\n' + notes).strip()
        hazard.status = 'Resolved'
        hazard.resolved_at = timezone.now()
        hazard.save()
        messages.success(request, f'Hazard {hazard.hazard_no} marked as resolved.')
        return redirect('hazard_detail', pk=hazard.pk)

    return render(request, 'safety/hazards/resolve.html', {'hazard': hazard})


# =====================================================================
# INSPECTIONS
# =====================================================================
@role_required('Manager', 'Accountant', 'Viewer')
def inspection_list(request):
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    mine_filter = request.GET.get('mine', '')

    inspections = SafetyInspection.objects.select_related('mine')
    if status_filter:
        inspections = inspections.filter(overall_status=status_filter)
    if type_filter:
        inspections = inspections.filter(inspection_type=type_filter)
    if mine_filter:
        inspections = inspections.filter(mine_id=mine_filter)

    return render(request, 'safety/inspections/list.html', {
        'inspections': inspections,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'mine_filter': mine_filter,
        'mines': Mine.objects.filter(voided=False),
        'status_choices': SafetyInspection.OVERALL_STATUS_CHOICES,
        'type_choices': SafetyInspection.INSPECTION_TYPE_CHOICES,
    })


@role_required('Manager', 'Accountant', 'Viewer')
def inspection_detail(request, pk):
    inspection = get_object_or_404(SafetyInspection, pk=pk)
    return render(request, 'safety/inspections/detail.html', {'inspection': inspection})


@role_required('Manager', 'Accountant')
def inspection_add(request):
    if request.method == 'POST':
        form = SafetyInspectionForm(request.POST, request.FILES)
        if form.is_valid():
            inspection = form.save(commit=False)
            inspection.conducted_by = request.user
            inspection.save()
            messages.success(request, f'Inspection {inspection.inspection_no} recorded.')
            return redirect('inspection_detail', pk=inspection.pk)
    else:
        initial = {'date': date_today.today()}
        form = SafetyInspectionForm(initial=initial)
    return render(request, 'safety/inspections/form.html', {
        'form': form, 'title': 'Record Inspection',
    })


@role_required('Manager')
def inspection_edit(request, pk):
    inspection = get_object_or_404(SafetyInspection, pk=pk)
    if request.method == 'POST':
        form = SafetyInspectionForm(request.POST, request.FILES, instance=inspection)
        if form.is_valid():
            form.save()
            messages.success(request, f'Inspection {inspection.inspection_no} updated.')
            return redirect('inspection_detail', pk=inspection.pk)
    else:
        form = SafetyInspectionForm(instance=inspection)
    return render(request, 'safety/inspections/form.html', {
        'form': form, 'title': f'Edit {inspection.inspection_no}', 'inspection': inspection,
    })


# =====================================================================
# PPE ISSUANCE
# =====================================================================
@role_required('Manager', 'Accountant', 'Viewer')
def ppe_list(request):
    type_filter = request.GET.get('type', '')
    returned_filter = request.GET.get('returned', '')
    employee_filter = request.GET.get('employee', '')

    issuances = PPEIssuance.objects.select_related('employee', 'issued_by')
    if type_filter:
        issuances = issuances.filter(ppe_type=type_filter)
    if returned_filter == 'no':
        issuances = issuances.filter(returned=False)
    elif returned_filter == 'yes':
        issuances = issuances.filter(returned=True)
    if employee_filter:
        issuances = issuances.filter(employee_id=employee_filter)

    return render(request, 'safety/ppe/list.html', {
        'issuances': issuances,
        'type_filter': type_filter,
        'returned_filter': returned_filter,
        'employee_filter': employee_filter,
        'employees': Employee.objects.filter(voided=False, status='Active'),
        'type_choices': PPEIssuance.PPE_TYPE_CHOICES,
    })


@role_required('Manager', 'Accountant')
def ppe_add(request):
    if request.method == 'POST':
        form = PPEIssuanceForm(request.POST, request.FILES)
        if form.is_valid():
            issuance = form.save(commit=False)
            issuance.issued_by = request.user
            issuance.save()
            messages.success(
                request,
                f'{issuance.get_ppe_type_display()} issued to '
                f'{issuance.employee.first_name} {issuance.employee.last_name}.'
            )
            return redirect('ppe_list')
    else:
        initial = {'date_issued': date_today.today()}
        form = PPEIssuanceForm(initial=initial)
    return render(request, 'safety/ppe/form.html', {
        'form': form, 'title': 'Issue PPE',
    })


@role_required('Manager')
def ppe_edit(request, pk):
    issuance = get_object_or_404(PPEIssuance, pk=pk)
    if request.method == 'POST':
        form = PPEIssuanceForm(request.POST, request.FILES, instance=issuance)
        if form.is_valid():
            form.save()
            messages.success(request, 'PPE record updated.')
            return redirect('ppe_list')
    else:
        form = PPEIssuanceForm(instance=issuance)
    return render(request, 'safety/ppe/form.html', {
        'form': form, 'title': 'Edit PPE Record', 'issuance': issuance,
    })


@role_required('Manager')
def ppe_return(request, pk):
    issuance = get_object_or_404(PPEIssuance, pk=pk)
    if issuance.returned:
        messages.warning(request, 'This item has already been marked as returned.')
        return redirect('ppe_list')

    if request.method == 'POST':
        issuance.returned = True
        issuance.returned_date = date_today.today()
        notes = request.POST.get('return_notes', '').strip()
        if notes:
            issuance.notes = ((issuance.notes or '') + '\n\n' + notes).strip()
        issuance.save()
        messages.success(request, f'{issuance.get_ppe_type_display()} marked as returned.')
        return redirect('ppe_list')

    return render(request, 'safety/ppe/return.html', {'issuance': issuance})


# =====================================================================
# SAFETY TRAINING
# =====================================================================
@role_required('Manager', 'Accountant', 'Viewer')
def training_list(request):
    type_filter = request.GET.get('type', '')
    employee_filter = request.GET.get('employee', '')
    expiring_filter = request.GET.get('expiring', '')

    trainings = SafetyTraining.objects.select_related('employee')
    if type_filter:
        trainings = trainings.filter(training_type=type_filter)
    if employee_filter:
        trainings = trainings.filter(employee_id=employee_filter)
    if expiring_filter == 'soon':
        today = date_today.today()
        trainings = trainings.filter(
            expiry_date__isnull=False,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        )
    elif expiring_filter == 'expired':
        trainings = trainings.filter(expiry_date__lt=date_today.today())

    return render(request, 'safety/trainings/list.html', {
        'trainings': trainings,
        'type_filter': type_filter,
        'employee_filter': employee_filter,
        'expiring_filter': expiring_filter,
        'employees': Employee.objects.filter(voided=False, status='Active'),
        'type_choices': SafetyTraining.TRAINING_TYPE_CHOICES,
    })


@role_required('Manager', 'Accountant')
def training_add(request):
    if request.method == 'POST':
        form = SafetyTrainingForm(request.POST, request.FILES)
        if form.is_valid():
            training = form.save(commit=False)
            training.recorded_by = request.user
            training.save()
            messages.success(
                request,
                f'Training "{training.training_type}" recorded for '
                f'{training.employee.first_name} {training.employee.last_name}.'
            )
            return redirect('training_list')
    else:
        initial = {'training_date': date_today.today()}
        form = SafetyTrainingForm(initial=initial)
    return render(request, 'safety/trainings/form.html', {
        'form': form, 'title': 'Record Safety Training',
    })


@role_required('Manager')
def training_edit(request, pk):
    training = get_object_or_404(SafetyTraining, pk=pk)
    if request.method == 'POST':
        form = SafetyTrainingForm(request.POST, request.FILES, instance=training)
        if form.is_valid():
            form.save()
            messages.success(request, 'Training record updated.')
            return redirect('training_list')
    else:
        form = SafetyTrainingForm(instance=training)
    return render(request, 'safety/trainings/form.html', {
        'form': form, 'title': 'Edit Training Record', 'training': training,
    })