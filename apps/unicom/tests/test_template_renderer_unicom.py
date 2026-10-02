import pytest

from unicom.services.template_renderer import render_template


def test_renders_variables_and_unprotects_tinymce_placeholders():
    # TinyMCE wraps Jinja placeholders in protected comments; ensure they are restored and rendered.
    protected = "<!-- mce:protected %7B%7B%20variables.name%20%7D%7D -->"
    template = f"<p>Hello {protected}</p>"
    result = render_template(template, variables={"name": "Ada"})
    assert result.html == "<p>Hello Ada</p>"
    assert result.errors == []
    assert result.variables["name"] == "Ada"


def test_merges_existing_variables_from_base_context():
    template = "{{ variables.a }} {{ variables.b }}"
    result = render_template(
        template,
        base_context={"variables": {"a": "first"}},
        variables={"b": "second"},
    )
    assert result.html == "first second"
    assert result.variables == {"a": "first", "b": "second"}


def test_reports_template_errors_and_preserves_original_html():
    template = "<p>{{ missing_value }}</p>"
    result = render_template(template)
    assert template in result.html  # Fallback to original on error
    assert result.errors  # StrictUndefined should surface an error
