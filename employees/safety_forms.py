"""
Forms for the Safety Module.
Used by views in employees/views/safety.py (Batch 3).
"""
from django import forms

from .forms import clear_zeros
from .models import (
    Hazard, PPEIssuance, SafetyIncident, SafetyInspection, SafetyTraining,
)


# =====================================================================
# SAFETY INCIDENT
# =====================================================================
class SafetyIncidentForm(forms.ModelForm):
    class Meta:
        model = SafetyIncident
        fields = [
            'date', 'time', 'mine', 'shift', 'location',
            'incident_type', 'severity',
            'description', 'employee', 'witnesses',
            'immediate_action', 'root_cause', 'corrective_action',
            'photo',
            'status', 'reported_to_government', 'cost',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Tunnel 3, 50m from entrance',
            }),
            'incident_type': forms.Select(attrs={'class': 'form-control'}),
            'severity': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'What happened? Full narrative.',
            }),
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'witnesses': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Names of witnesses, one per line',
            }),
            'immediate_action': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'First aid, evacuation, area barricaded, etc.',
            }),
            'root_cause': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Filled during investigation',
            }),
            'corrective_action': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Steps to prevent recurrence',
            }),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'reported_to_government': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].required = False
        self.fields['time'].required = False
        self.fields['location'].required = False
        self.fields['shift'].required = False
        self.fields['witnesses'].required = False
        self.fields['immediate_action'].required = False
        self.fields['root_cause'].required = False
        self.fields['corrective_action'].required = False
        self.fields['photo'].required = False
        self.fields['cost'].required = False
        clear_zeros(self, ['cost'])


# =====================================================================
# HAZARD
# =====================================================================
class HazardForm(forms.ModelForm):
    class Meta:
        model = Hazard
        fields = [
            'date_observed', 'mine', 'shift', 'location',
            'hazard_type', 'risk_level', 'description', 'photo',
            'action_taken', 'status', 'assigned_to', 'due_date',
        ]
        widgets = {
            'date_observed': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'shift': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'hazard_type': forms.Select(attrs={'class': 'form-control'}),
            'risk_level': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'What did you see? Be specific.',
            }),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'action_taken': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Barrier / warning put in place',
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['shift'].required = False
        self.fields['photo'].required = False
        self.fields['action_taken'].required = False
        self.fields['assigned_to'].required = False
        self.fields['due_date'].required = False


# =====================================================================
# SAFETY INSPECTION
# =====================================================================
class SafetyInspectionForm(forms.ModelForm):
    class Meta:
        model = SafetyInspection
        fields = [
            'date', 'mine', 'location', 'inspection_type',
            'inspector', 'findings', 'issues_count', 'overall_status',
            'follow_up_required', 'follow_up_deadline', 'follow_up_notes',
            'photo',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'mine': forms.Select(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Specific area if not whole mine',
            }),
            'inspection_type': forms.Select(attrs={'class': 'form-control'}),
            'inspector': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Who conducted the inspection',
            }),
            'findings': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'What was checked and what was found',
            }),
            'issues_count': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '0',
            }),
            'overall_status': forms.Select(attrs={'class': 'form-control'}),
            'follow_up_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'follow_up_deadline': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'follow_up_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].required = False
        self.fields['follow_up_deadline'].required = False
        self.fields['follow_up_notes'].required = False
        self.fields['photo'].required = False
        clear_zeros(self, ['issues_count'])


# =====================================================================
# PPE ISSUANCE
# =====================================================================
class PPEIssuanceForm(forms.ModelForm):
    class Meta:
        model = PPEIssuance
        fields = [
            'employee', 'date_issued', 'ppe_type', 'quantity',
            'size', 'condition', 'replacement_due',
            'returned', 'returned_date', 'notes',
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'date_issued': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'ppe_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '1'}),
            'size': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Large, 42, Universal',
            }),
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'replacement_due': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'returned': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'returned_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['size'].required = False
        self.fields['replacement_due'].required = False
        self.fields['returned_date'].required = False
        self.fields['notes'].required = False
        clear_zeros(self, ['quantity'])


# =====================================================================
# SAFETY TRAINING
# =====================================================================
class SafetyTrainingForm(forms.ModelForm):
    class Meta:
        model = SafetyTraining
        fields = [
            'employee', 'training_type', 'training_date', 'expiry_date',
            'trainer_name', 'trainer_company', 'duration_hours',
            'certificate_no', 'certificate_photo', 'passed', 'notes',
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-control'}),
            'training_type': forms.Select(attrs={'class': 'form-control'}),
            'training_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'trainer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'trainer_company': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Training provider / institute',
            }),
            'duration_hours': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.5', 'placeholder': '0',
            }),
            'certificate_no': forms.TextInput(attrs={'class': 'form-control'}),
            'certificate_photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'passed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['expiry_date'].required = False
        self.fields['trainer_name'].required = False
        self.fields['trainer_company'].required = False
        self.fields['certificate_no'].required = False
        self.fields['certificate_photo'].required = False
        self.fields['notes'].required = False
        clear_zeros(self, ['duration_hours'])