import os
import importlib.util
from django.core.management.base import BaseCommand
from django.conf import settings
from unibot.models import Tool, Bot


class Command(BaseCommand):
    help = 'Syncs tools and bots from configured definitions directory with the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        self.sync_tools(dry_run)
        self.sync_bots(dry_run)

    def load_python_file(self, file_path):
        """Load a Python file and return its module."""
        try:
            spec = importlib.util.spec_from_file_location("module", file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error loading {file_path}: {e}')
            )
            return None

    def sync_tools(self, dry_run):
        """Sync tools from configured definitions directory with database."""
        self.stdout.write(self.style.SUCCESS('\n=== Syncing Tools ==='))

        # Get definitions directory from settings, fallback to default
        definitions_dir = getattr(settings, 'UNIBOT_DEFINITIONS_DIR',
                                 os.path.join(settings.BASE_DIR, 'data', 'definitions'))
        tools_dir = os.path.join(definitions_dir, 'tools')
        
        if not os.path.exists(tools_dir):
            self.stdout.write(self.style.ERROR(f'Tools directory not found: {tools_dir}'))
            return
        
        for filename in os.listdir(tools_dir):
            if filename.endswith('.py') and filename != '__init__.py':
                file_path = os.path.join(tools_dir, filename)
                tool_name = filename[:-3]  # Remove .py extension
                
                self.stdout.write(f'\nProcessing tool: {tool_name}')
                
                # Load the Python file
                module = self.load_python_file(file_path)
                if not module:
                    continue
                
                # Read the file content for the code field
                with open(file_path, 'r') as f:
                    file_code = f.read()
                
                # Check if tool_definition exists
                if not hasattr(module, 'tool_definition'):
                    self.stdout.write(
                        self.style.ERROR(f'  No tool_definition found in {filename}')
                    )
                    continue
                
                try:
                    # Check if tool already exists
                    existing_tool = Tool.objects.filter(name=tool_name).first()
                    
                    if existing_tool:
                        # Check if code is different
                        if existing_tool.code != file_code:
                            self.stdout.write(f'  Updating existing tool: {tool_name}')
                            if not dry_run:
                                existing_tool.code = file_code
                                existing_tool.save(update_fields=['code'])
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Tool {tool_name} updated'))
                        else:
                            self.stdout.write(f'  Tool {tool_name} already up-to-date')
                    else:
                        # Create new tool
                        self.stdout.write(f'  Creating new tool: {tool_name}')
                        if not dry_run:
                            Tool.objects.create(
                                name=tool_name,
                                description='',  # Leave empty as requested
                                code=file_code
                            )
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Tool {tool_name} created'))
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  Error processing {tool_name}: {e}')
                    )

    def sync_bots(self, dry_run):
        """Sync bots from configured definitions directory with database."""
        self.stdout.write(self.style.SUCCESS('\n=== Syncing Bots ==='))

        # Get definitions directory from settings, fallback to default
        definitions_dir = getattr(settings, 'UNIBOT_DEFINITIONS_DIR',
                                 os.path.join(settings.BASE_DIR, 'data', 'definitions'))
        bots_dir = os.path.join(definitions_dir, 'bots')
        
        if not os.path.exists(bots_dir):
            self.stdout.write(self.style.ERROR(f'Bots directory not found: {bots_dir}'))
            return
        
        for filename in os.listdir(bots_dir):
            if filename.endswith('.py') and filename != '__init__.py':
                file_path = os.path.join(bots_dir, filename)
                bot_name = filename[:-3]  # Remove .py extension
                bot_category = f"{bot_name}_request"
                
                self.stdout.write(f'\nProcessing bot: {bot_name}')
                
                # Load the Python file to validate it
                module = self.load_python_file(file_path)
                if not module:
                    continue
                
                # Read the file content for the code field
                with open(file_path, 'r') as f:
                    file_code = f.read()
                
                # Check if handle_incoming_message exists
                if not hasattr(module, 'handle_incoming_message'):
                    self.stdout.write(
                        self.style.ERROR(f'  No handle_incoming_message found in {filename}')
                    )
                    continue
                
                # Get bot_tools list if it exists
                bot_tools = getattr(module, 'bot_tools', [])
                
                try:
                    # Check if bot already exists by name
                    existing_bot = Bot.objects.filter(name=bot_name).first()
                    
                    if existing_bot:
                        # Check if code is different
                        if existing_bot.code != file_code:
                            self.stdout.write(f'  Updating existing bot: {bot_name}')
                            if not dry_run:
                                existing_bot.code = file_code
                                existing_bot.save(update_fields=['code'])
                            self.stdout.write(self.style.SUCCESS(f'  ✓ Bot {bot_name} code updated'))
                        else:
                            self.stdout.write(f'  Bot {bot_name} already up-to-date')
                        
                        # Update tool associations
                        self.update_bot_tools(existing_bot, bot_tools, dry_run)
                    else:
                        # Create new bot
                        self.stdout.write(f'  Creating new bot: {bot_name}')
                        if not dry_run:
                            new_bot = Bot.objects.create(
                                name=bot_name,
                                category=bot_category,
                                code=file_code
                            )
                            # Set up tool associations
                            self.update_bot_tools(new_bot, bot_tools, dry_run=False)
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Bot {bot_name} created'))
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  Error processing {bot_name}: {e}')
                    )

    def update_bot_tools(self, bot, tool_names, dry_run):
        """Update the tools associated with a bot."""
        if not tool_names:
            self.stdout.write(f'    No tools specified for bot {bot.name}')
            return
        
        # Find tools by name
        tools_to_associate = []
        missing_tools = []
        
        for tool_name in tool_names:
            tool = Tool.objects.filter(name=tool_name).first()
            if tool:
                tools_to_associate.append(tool)
            else:
                missing_tools.append(tool_name)
        
        if missing_tools:
            self.stdout.write(
                self.style.WARNING(f'    Missing tools for {bot.name}: {missing_tools}')
            )
        
        if tools_to_associate:
            current_tools = set(bot.tools.values_list('name', flat=True))
            new_tools = set(tool.name for tool in tools_to_associate)
            
            if current_tools != new_tools:
                self.stdout.write(f'    Updating tools for {bot.name}: {list(new_tools)}')
                if not dry_run:
                    bot.tools.set(tools_to_associate)
                self.stdout.write(self.style.SUCCESS(f'    ✓ Tools updated for {bot.name}'))
            else:
                self.stdout.write(f'    Tools for {bot.name} already up-to-date')

        # Create a summary
        if not dry_run:
            self.stdout.write(self.style.SUCCESS('\n=== Summary ==='))
            tool_count = Tool.objects.count()
            bot_count = Bot.objects.count()
            self.stdout.write(f'Total tools in database: {tool_count}')
            self.stdout.write(f'Total bots in database: {bot_count}')