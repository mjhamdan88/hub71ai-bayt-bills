import pytest

from unicom.services.template_renderer import (
    compute_crm_variables,
    extract_variable_keys,
)


@pytest.mark.django_db
def test_extract_variable_keys_and_compute_crm_variable(settings):
    try:
        from unicrm.models import Contact, TemplateVariable
    except Exception:
        pytest.skip("unicrm not installed")

    contact = Contact.objects.create(email="crm@test.com", first_name="Crm", last_name="User")
    tv = TemplateVariable.objects.create(
        key="contact_first_name_test",
        label="First name",
        description="Test variable",
        code="""
def compute(contact):
    return contact.first_name
""",
        is_active=True,
    )

    html = "<p>Hello {{ variables.contact_first_name_test }}</p>"
    keys = extract_variable_keys(html)
    assert "contact_first_name_test" in keys

    values = compute_crm_variables(keys, contact.email)
    assert values.get("contact_first_name_test") == "Crm"

    # Clean up
    tv.delete()
    contact.delete()


@pytest.mark.django_db
def test_compute_crm_variables_no_contact():
    values = compute_crm_variables({"missing"}, "nope@example.com")
    assert values == {}


@pytest.mark.django_db
def test_compute_crm_variables_creates_contact_if_missing(settings):
    try:
        from unicrm.models import Contact, TemplateVariable
    except Exception:
        pytest.skip("unicrm not installed")

    email = "autocreate@test.com"
    Contact.objects.filter(email=email).delete()

    tv = TemplateVariable.objects.create(
        key="contact_email_test",
        label="Email",
        description="Test variable",
        code="""
def compute(contact):
    return contact.email
""",
        is_active=True,
    )

    html = "<p>{{ variables.contact_email_test }}</p>"
    keys = extract_variable_keys(html)
    values = compute_crm_variables(keys, email)
    assert values.get("contact_email_test") == email
    assert Contact.objects.filter(email__iexact=email).exists()

    tv.delete()
    Contact.objects.filter(email=email).delete()
