from django.test import SimpleTestCase

from unibot.services.llm_handler import build_openai_tools


class _ToolStub:
    def __init__(self, definition):
        self.definition = definition

    def get_definition(self, **_context):
        return {**self.definition}


class OpenAIToolSchemaTests(SimpleTestCase):
    def _build_parameters(self, parameters):
        tool = _ToolStub({
            "name": "schema_test",
            "description": "Schema test.",
            "parameters": parameters,
            "run": lambda **_kwargs: None,
        })
        schemas, _tool_map, _auto_params = build_openai_tools([tool])
        return schemas[0]["function"]["parameters"]

    def test_preserves_valid_nested_required_properties(self):
        parameters = self._build_parameters({
            "viewport": {
                "type": "object",
                "properties": {
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
                "required": ["width", "height"],
                "additionalProperties": False,
            },
        })

        viewport = parameters["properties"]["viewport"]
        self.assertEqual(viewport["required"], ["width", "height"])
        self.assertFalse(viewport["additionalProperties"])

    def test_flat_schema_requires_properties_with_defaults_in_strict_mode(self):
        parameters = self._build_parameters({
            "query": {"type": "string", "description": "Search query."},
            "limit": {"type": "integer", "default": 10},
        })

        self.assertEqual(
            parameters["required"],
            ["query", "limit", "progress_updates_for_user"],
        )
        self.assertEqual(
            parameters["properties"]["limit"],
            {"type": "integer", "default": 10},
        )

    def test_rejects_non_array_nested_required(self):
        with self.assertRaisesRegex(ValueError, "must define 'required' as a list"):
            self._build_parameters({
                "options": {
                    "type": "object",
                    "properties": {"enabled": {"type": "boolean"}},
                    "required": True,
                },
            })

    def test_rejects_unknown_nested_required_property(self):
        with self.assertRaisesRegex(ValueError, "requires unknown properties: missing"):
            self._build_parameters({
                "options": {
                    "type": "object",
                    "properties": {"enabled": {"type": "boolean"}},
                    "required": ["missing"],
                },
            })

    def test_rejects_optional_nested_property_in_strict_mode(self):
        with self.assertRaisesRegex(ValueError, "must require every property.*missing: disabled"):
            self._build_parameters({
                "options": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "disabled": {"type": ["boolean", "null"]},
                    },
                    "required": ["enabled"],
                },
            })
