from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"


    def ready(self):
        # Upstream assumes apps live at BASE_DIR/unibot. Use Django's template
        # discovery for this project's apps/ layout and project overrides.
        from django.template.loader import get_template
        from unibot.models import Bot, Tool

        def source(name):
            return get_template(f"unibot/{name}").template.source

        Bot.get_default_code = staticmethod(lambda: source("default_bot.py"))
        Tool.get_default_code = staticmethod(lambda: source("default_tool.py"))
        Bot.get_template_readme = classmethod(lambda cls: source("BOT_TEMPLATES_README.md"))
        Tool.get_template_readme = classmethod(lambda cls: source("TOOL_TEMPLATES_README.md"))
