from django.test import TestCase

from unicrm.models import (
    Company,
    Contact,
    MailingList,
    Subscription,
    TemplateVariable,
)
from unicrm.services.template_renderer import (
    build_contact_context,
    render_template_for_contact,
)


class TemplateRendererTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme Inc.', domain='acme.com')
        self.contact = Contact.objects.create(
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com',
            company=self.company,
            attributes={'nickname': 'Johnny'},
        )
        self.mailing_list = MailingList.objects.create(name='Newsletter', public_name='Newsletter', slug='newsletter')
        Subscription.objects.create(contact=self.contact, mailing_list=self.mailing_list)

        TemplateVariable.objects.create(
            key='contact_full_name',
            label='Full Name',
            description='Concatenated first and last name',
            code="""
def compute(contact):
    return f"{contact.first_name} {contact.last_name}".strip()
""",
        )

    def test_build_contact_context_includes_company_and_subscriptions(self):
        context = build_contact_context(self.contact)
        self.assertEqual(context['email'], 'john.doe@example.com')
        self.assertEqual(context['company']['name'], 'Acme Inc.')
        self.assertEqual(len(context['subscriptions']), 1)
        subscription = context['subscriptions'][0]
        self.assertTrue(subscription['is_active'])
        self.assertEqual(subscription['mailing_list']['slug'], 'newsletter')

    def test_render_template_for_contact_substitutes_variables(self):
        template_html = """
            <p>Hello {{ variables.contact_full_name }}!</p>
            <p>We see you work at {{ contact.company.name or 'Unknown' }}.</p>
        """
        result = render_template_for_contact(
            template_html,
            contact=self.contact,
        )
        self.assertIn('Hello John Doe', result.html)
        self.assertIn('work at Acme Inc.', result.html)
        self.assertEqual(result.variables['contact_full_name'], 'John Doe')
        self.assertFalse(result.errors)

    def test_render_template_for_contact_reports_missing_variables(self):
        template_html = "<p>{{ variables.undefined_value }}</p>"
        result = render_template_for_contact(
            template_html,
            contact=self.contact,
        )
        # Falls back to original HTML when rendering fails.
        self.assertEqual(result.html.strip(), template_html)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('undefined_value', result.errors[0])
