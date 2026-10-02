from __future__ import annotations

from datetime import datetime
from typing import Iterable, List

import pytz
from django import forms
from django.utils import timezone

from unicom.models import Channel
from unicrm.models import Segment, MailingList, Communication
from unicrm.templates.unicrm.unibot.lead_search_v2_tool import (
    ALLOWED_EMAIL_STATUS,
    ALLOWED_INDUSTRIES,
    ALLOWED_SENIORITY,
)


class CommunicationComposeForm(forms.Form):
    segment = forms.ModelChoiceField(
        queryset=Segment.objects.none(),
        label='Recipient segment',
        help_text='Which contacts should receive this communication.'
    )
    mailing_list = forms.ModelChoiceField(
        queryset=MailingList.objects.none(),
        label='Mailing list',
        required=False,
        help_text='Optional mailing list to target; combined with the segment if both are provided.'
    )
    channel = forms.ModelChoiceField(
        queryset=Channel.objects.none(),
        label='Channel',
        help_text='Channel used to deliver the emails.'
    )
    subject_template = forms.CharField(
        label='Subject',
        max_length=255,
        required=False,
        help_text='Optional Jinja2 subject template. Leave blank to use a generic fallback.'
    )
    content = forms.CharField(
        label='Email content',
        widget=forms.Textarea,
        required=False,
        help_text='Editable HTML body rendered for every contact.'
    )
    follow_up_for = forms.ModelChoiceField(
        queryset=Communication.objects.none(),
        label='Follow-up for',
        required=False,
        help_text='Optional parent communication this one follows up on.',
    )
    exclude_follow_up_siblings = forms.BooleanField(
        label='Exclude contacts already in other follow-ups',
        required=False,
        initial=True,
        help_text='Prevent contacts targeted by other follow-up branches of the same parent from receiving this communication.',
    )
    skip_antispam_guards = forms.BooleanField(
        label='Skip anti-spam guards',
        required=False,
        help_text='Send even if cooldown/unengaged limits would normally skip a contact.',
    )
    auto_enroll_new_contacts = forms.BooleanField(
        label='Auto-send to new segment members',
        required=False,
        help_text='When checked, any contact who later joins this segment will automatically receive this communication.'
    )
    send_at = forms.CharField(required=False)
    timezone = forms.CharField(required=False)

    def __init__(
        self,
        *args,
        segment_queryset: Iterable[Segment] | None = None,
        mailing_list_queryset: Iterable[MailingList] | None = None,
        channel_queryset: Iterable[Channel] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields['segment'].queryset = segment_queryset or Segment.objects.all()
        self.fields['mailing_list'].queryset = mailing_list_queryset or MailingList.objects.all()
        self.fields['channel'].queryset = channel_queryset or Channel.objects.filter(active=True)
        self.fields['follow_up_for'].queryset = Communication.objects.order_by('-created_at')
        self.cleaned_schedule_utc = None
        self.cleaned_schedule_local = None

        if not self.is_bound:
            channel_qs = self.fields['channel'].queryset
            if channel_qs.count() == 1:
                default_channel = channel_qs.first()
                if default_channel:
                    self.initial['channel'] = str(default_channel.pk)
                    self.fields['channel'].initial = str(default_channel.pk)

    def clean_content(self) -> str:
        content = (self.cleaned_data.get('content') or '').strip()
        if not content:
            raise forms.ValidationError('Please provide the email content before sending.')
        return content

    def clean(self):
        cleaned = super().clean()
        follow_up_for = cleaned.get('follow_up_for')
        segment = cleaned.get('segment')
        auto_enroll = cleaned.get('auto_enroll_new_contacts')
        skip_guards = cleaned.get('skip_antispam_guards')

        send_at_raw = (cleaned.get('send_at') or '').strip()
        timezone_name = (cleaned.get('timezone') or 'UTC').strip() or 'UTC'

        if send_at_raw:
            try:
                naive_dt = datetime.strptime(send_at_raw, '%Y-%m-%dT%H:%M')
            except ValueError:
                self.add_error('send_at', 'Invalid date/time format.')
                return cleaned

            try:
                tz = pytz.timezone(timezone_name)
            except pytz.exceptions.UnknownTimeZoneError:
                tz = pytz.UTC

            local_dt = tz.localize(naive_dt)
            # Store for access after validation
            self.cleaned_schedule_local = local_dt

            utc_dt = local_dt.astimezone(pytz.UTC)
            if utc_dt <= timezone.now():
                self.add_error('send_at', 'Please choose a future time or leave blank to send now.')
            else:
                self.cleaned_schedule_utc = utc_dt
        else:
            self.cleaned_schedule_utc = None
            self.cleaned_schedule_local = None

        if segment and getattr(segment, 'for_followup', False) and not follow_up_for:
            self.add_error('follow_up_for', 'This segment references a previous communication; please choose one.')

        # Follow-ups should be evergreen by default
        if follow_up_for and not auto_enroll:
            cleaned['auto_enroll_new_contacts'] = True

        # Allow skipping guards only for explicit opt-in; no extra validation needed here.
        if skip_guards is None:
            cleaned['skip_antispam_guards'] = False

        if cleaned.get('exclude_follow_up_siblings') is None:
            cleaned['exclude_follow_up_siblings'] = True

        return cleaned


class LeadSearchAdminForm(forms.Form):
    # These inputs are populated via Tagify; stored as comma/NOT separated strings.
    position = forms.CharField(label='Position', required=False, widget=forms.HiddenInput())
    departments = forms.CharField(label='Departments', required=False, widget=forms.HiddenInput())
    seniority = forms.CharField(label='Seniority', required=False, widget=forms.HiddenInput())
    contact_location = forms.CharField(label='Contact location', required=False, widget=forms.HiddenInput())
    industries = forms.CharField(label='Industries', required=False, widget=forms.HiddenInput())
    company_size_ranges = forms.MultipleChoiceField(
        label='Company size ranges',
        choices=[
            ("1 - 10", "1 - 10"),
            ("11 - 20", "11 - 20"),
            ("21 - 50", "21 - 50"),
            ("51 - 100", "51 - 100"),
            ("101 - 200", "101 - 200"),
            ("201 - 500", "201 - 500"),
            ("501 - 1000", "501 - 1000"),
            ("1001 - 2000", "1001 - 2000"),
            ("2001 - 5000", "2001 - 5000"),
            ("5001 - 10000", "5001 - 10000"),
            ("10000", "10000+"),
        ],
        required=False,
    )
    company_locations = forms.CharField(
        label='Company locations',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Comma or newline separated; you can use NOT/! to exclude values.',
    )
    company_domain = forms.CharField(label='Company domain(s)', required=False, widget=forms.HiddenInput())
    company_name = forms.CharField(label='Company name(s)', required=False, widget=forms.HiddenInput())
    founded_from = forms.IntegerField(label='Founded from (year)', required=False, min_value=0)
    founded_to = forms.IntegerField(label='Founded to (year)', required=False, min_value=0)
    company_types = forms.CharField(label='Company types', required=False, widget=forms.HiddenInput())
    company_keywords = forms.CharField(label='Company keywords', required=False, widget=forms.HiddenInput())
    technologies = forms.CharField(label='Technologies', required=False, widget=forms.HiddenInput())
    contact_names = forms.CharField(label='Contact names', required=False, widget=forms.HiddenInput())
    contact_keywords = forms.CharField(label='Contact keywords', required=False, widget=forms.HiddenInput())

    email_status = forms.ChoiceField(
        label='Email status',
        choices=[(opt, opt.title()) for opt in ALLOWED_EMAIL_STATUS],
        required=False,
        initial='all',
    )

    company_size_min = forms.IntegerField(label='Company size min', required=False, min_value=0)
    company_size_max = forms.IntegerField(label='Company size max', required=False, min_value=0)
    page_size = forms.IntegerField(label='Page size', required=False, initial=20, min_value=1)
    page_number = forms.IntegerField(label='Page number', required=False, initial=1, min_value=1)
    request_type = forms.ChoiceField(
        label='Result scope',
        choices=[('excluded', 'Exclude saved'), ('included', 'Saved only'), ('all', 'All')],
        required=False,
        initial='excluded',
        help_text='Matches GetProspect requestType. Default: exclude saved.',
    )

    def _split_list(self, value: str) -> List[str]:
        if not value:
            return []
        parts: List[str] = []
        for line in value.replace('\r', '').split('\n'):
            for chunk in line.split(','):
                cleaned = chunk.strip()
                if cleaned:
                    parts.append(cleaned)
        return parts

    def clean_email_status(self) -> str:
        value = (self.cleaned_data.get('email_status') or 'all').strip().lower()
        return value if value in ALLOWED_EMAIL_STATUS else 'all'

    def clean_company_locations(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('company_locations'))

    def clean_company_name(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('company_name'))

    def clean_company_domain(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('company_domain'))

    def clean_industries(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('industries'))

    def clean_company_keywords(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('company_keywords'))

    def clean_contact_keywords(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('contact_keywords'))

    def clean_contact_names(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('contact_names'))

    def clean_technologies(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('technologies'))

    def clean_departments(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('departments'))

    def clean_company_types(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('company_types'))

    def clean_position(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('position'))

    def clean_contact_location(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('contact_location'))

    def clean_seniority(self) -> List[str]:
        return self._split_list(self.cleaned_data.get('seniority'))

    def clean_page_size(self) -> int:
        value = self.cleaned_data.get('page_size') or 20
        if value <= 0:
            value = 20
        return min(value, 50)

    def clean_page_number(self) -> int:
        value = self.cleaned_data.get('page_number') or 1
        return 1 if value <= 0 else value
