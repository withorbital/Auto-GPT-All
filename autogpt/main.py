"""The application entry point.  Can be invoked by a CLI or any other front end application."""
import logging
import sys
from pathlib import Path
import os
from colorama import Fore, Style

from autogpt.agent import Agent
from autogpt.commands.command import CommandRegistry
from autogpt.config import Config, check_openai_api_key
from autogpt.configurator import create_config
from autogpt.logs import logger
from autogpt.memory.vector import get_memory
from autogpt.memory.vector.memory_item import MemoryItem
from autogpt.plugins import scan_plugins
from autogpt.prompts.prompt import DEFAULT_TRIGGERING_PROMPT, construct_main_ai_config
from autogpt.utils import (
    get_current_git_branch,
    get_latest_bulletin,
    get_legal_warning,
    markdown_to_ansi_style,
)
from autogpt.workspace import Workspace
from scripts.install_plugin_deps import install_plugin_dependencies
import csv

COMMAND_CATEGORIES = [
    "autogpt.commands.analyze_code",
    "autogpt.commands.audio_text",
    "autogpt.commands.execute_code",
    "autogpt.commands.file_operations",
    "autogpt.commands.git_operations",
    "autogpt.commands.google_search",
    "autogpt.commands.image_gen",
    "autogpt.commands.improve_code",
    "autogpt.commands.web_selenium",
    "autogpt.commands.write_tests",
    "autogpt.app",
    "autogpt.commands.task_statuses",
]

def read_csv(filename):
    companies = []
    with open(filename, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header row
        for row in reader:
            companies.append(row[0])
    return companies

def run_auto_gpt_loop(
    continuous: bool,
    continuous_limit: int,
    ai_settings: str,
    prompt_settings: str,
    skip_reprompt: bool,
    speak: bool,
    debug: bool,
    gpt3only: bool,
    gpt4only: bool,
    memory_type: str,
    browser_name: str,
    allow_downloads: bool,
    skip_news: bool,
    workspace_directory: str,
    install_plugin_deps: bool,
):
    print("Running Auto-GPT")
    workspace_directory = Path(__file__).parent / "auto_gpt_workspace"
    
    #read csv file and run auto-gpt in a loop for every company name in csv file
    input_file = f"{workspace_directory}/data/companies.csv"
    companies = read_csv(input_file)
    
    print("Companies length: ", len(companies))

    goalsTemplate = """
    ai_goals:
     - company name is {company_name}
     - find if they provide free lunch/food/snacks to employees
     - you can get this information from careers website
     - or you can get this information from glassdoor reviews
     - or you can get this information from indeed reviews
     - if you can find in any above sources that company provides free lunch/food/snacks to employees, then update false
     - Find the description where you find the information
     - send the company name, true/false, description, reference link to slack
     - write the output to ouput.tsv file with company_name,true/false,description,reference_link
    ai_name: dataGPT
    ai_role: Can read indeed, glassdoor and news articles to find if a company provides free food to its employees
    """

    for company in companies:
        print("Running Auto-GPT for company: ", company)
        # Configure logging before we do anything else.
        logger.set_level(logging.DEBUG if debug else logging.INFO)
        logger.speak_mode = speak

        goal = goalsTemplate.format(company_name=company)
        
        with open(f"{workspace_directory}/output.tsv", 'w') as f:
            f.write("")
            f.close()

        #write to ai_settings.yaml file
        with open(f"ai_settings.yaml", "w") as f:
            f.write(goal)

        cfg = Config()
        # TODO: fill in llm values here
        check_openai_api_key()

        create_config(
            cfg,
            True,
            10,
            ai_settings,
            prompt_settings,
            True,
            speak,
            debug,
            gpt3only,
            gpt4only,
            memory_type,
            browser_name,
            allow_downloads,
            skip_news,
        )

        if cfg.continuous_mode:
            for line in get_legal_warning().split("\n"):
                logger.warn(markdown_to_ansi_style(line), "LEGAL:", Fore.RED)

        if not cfg.skip_news:
            motd, is_new_motd = get_latest_bulletin()
            if motd:
                motd = markdown_to_ansi_style(motd)
                for motd_line in motd.split("\n"):
                    logger.info(motd_line, "NEWS:", Fore.GREEN)
                if is_new_motd and not cfg.chat_messages_enabled:
                    input(
                        Fore.MAGENTA
                        + Style.BRIGHT
                        + "NEWS: Bulletin was updated! Press Enter to continue..."
                        + Style.RESET_ALL
                    )

            git_branch = get_current_git_branch()
            if git_branch and git_branch != "stable":
                logger.typewriter_log(
                    "WARNING: ",
                    Fore.RED,
                    f"You are running on `{git_branch}` branch "
                    "- this is not a supported branch.",
                )
            if sys.version_info < (3, 10):
                logger.typewriter_log(
                    "WARNING: ",
                    Fore.RED,
                    "You are running on an older version of Python. "
                    "Some people have observed problems with certain "
                    "parts of Auto-GPT with this version. "
                    "Please consider upgrading to Python 3.10 or higher.",
                )

        if install_plugin_deps:
            install_plugin_dependencies()

        # TODO: have this directory live outside the repository (e.g. in a user's
        #   home directory) and have it come in as a command line argument or part of
        #   the env file.
        if workspace_directory is None:
            workspace_directory = Path(__file__).parent / "auto_gpt_workspace"
        else:
            workspace_directory = Path(workspace_directory)
        # TODO: pass in the ai_settings file and the env file and have them cloned into
        #   the workspace directory so we can bind them to the agent.
        workspace_directory = Workspace.make_workspace(workspace_directory)
        cfg.workspace_path = str(workspace_directory)

        # HACK: doing this here to collect some globals that depend on the workspace.
        file_logger_path = workspace_directory / "file_logger.txt"
        if not file_logger_path.exists():
            with file_logger_path.open(mode="w", encoding="utf-8") as f:
                f.write("File Operation Logger ")

        cfg.file_logger_path = str(file_logger_path)

        cfg.set_plugins(scan_plugins(cfg, cfg.debug_mode))
        # Create a CommandRegistry instance and scan default folder
        command_registry = CommandRegistry()

        logger.debug(
            f"The following command categories are disabled: {cfg.disabled_command_categories}"
        )
        enabled_command_categories = [
            x for x in COMMAND_CATEGORIES if x not in cfg.disabled_command_categories
        ]

        logger.debug(
            f"The following command categories are enabled: {enabled_command_categories}"
        )

        for command_category in enabled_command_categories:
            command_registry.import_commands(command_category)

        ai_name = ""
        ai_config = construct_main_ai_config()
        ai_config.command_registry = command_registry
        if ai_config.ai_name:
            ai_name = ai_config.ai_name
        # print(prompt)
        # Initialize variables
        next_action_count = 0

        # add chat plugins capable of report to logger
        if cfg.chat_messages_enabled:
            for plugin in cfg.plugins:
                if hasattr(plugin, "can_handle_report") and plugin.can_handle_report():
                    logger.info(f"Loaded plugin into logger: {plugin.__class__.__name__}")
                    logger.chat_plugins.append(plugin)

        # Initialize memory and make sure it is empty.
        # this is particularly important for indexing and referencing pinecone memory
        memory = get_memory(cfg, init=True)
        # memory.add(item=MemoryItem.from_text(text="company_name is" + company, source_type="agent_history", how_to_summarize="donot summarize this, just return the same text" ))
        print("Memory length: ", memory.__len__())
        logger.typewriter_log(
            "Using memory of type:", Fore.GREEN, f"{memory.__class__.__name__}"
        )
        logger.typewriter_log("Using Browser:", Fore.GREEN, cfg.selenium_web_browser)
        system_prompt = ai_config.construct_full_prompt()
        if cfg.debug_mode:
            logger.typewriter_log("Prompt:", Fore.GREEN, system_prompt)

        agent = Agent(
            ai_name=ai_name,
            memory=memory,
            next_action_count=next_action_count,
            command_registry=command_registry,
            config=ai_config,
            system_prompt=system_prompt,
            triggering_prompt=DEFAULT_TRIGGERING_PROMPT,
            workspace_directory=workspace_directory,
        )
        try:
            agent.start_interaction_loop()
        except:
            print("NameError: Task Complete")
            pass

        with open(f"{workspace_directory}/output.tsv", "w+") as f:
            line = f.readline()
            with open(f"{workspace_directory}/companies_lunch.tsv", "a") as f2:
                f2.write(f"{company}\t{line}\n")
                f2.close()
            f.close()

        os.remove(f"{workspace_directory}/output.tsv")

def run_auto_gpt(
    continuous: bool,
    continuous_limit: int,
    ai_settings: str,
    prompt_settings: str,
    skip_reprompt: bool,
    speak: bool,
    debug: bool,
    gpt3only: bool,
    gpt4only: bool,
    memory_type: str,
    browser_name: str,
    allow_downloads: bool,
    skip_news: bool,
    workspace_directory: str,
    install_plugin_deps: bool,
):
    print("Running Auto-GPT")
    # Configure logging before we do anything else.
    logger.set_level(logging.DEBUG if debug else logging.INFO)
    logger.speak_mode = speak

    cfg = Config()
    # TODO: fill in llm values here
    check_openai_api_key()

    create_config(
        cfg,
        continuous,
        continuous_limit,
        ai_settings,
        prompt_settings,
        skip_reprompt,
        speak,
        debug,
        gpt3only,
        gpt4only,
        memory_type,
        browser_name,
        allow_downloads,
        skip_news,
    )

    if cfg.continuous_mode:
        for line in get_legal_warning().split("\n"):
            logger.warn(markdown_to_ansi_style(line), "LEGAL:", Fore.RED)

    if not cfg.skip_news:
        motd, is_new_motd = get_latest_bulletin()
        if motd:
            motd = markdown_to_ansi_style(motd)
            for motd_line in motd.split("\n"):
                logger.info(motd_line, "NEWS:", Fore.GREEN)
            if is_new_motd and not cfg.chat_messages_enabled:
                input(
                    Fore.MAGENTA
                    + Style.BRIGHT
                    + "NEWS: Bulletin was updated! Press Enter to continue..."
                    + Style.RESET_ALL
                )

        git_branch = get_current_git_branch()
        if git_branch and git_branch != "stable":
            logger.typewriter_log(
                "WARNING: ",
                Fore.RED,
                f"You are running on `{git_branch}` branch "
                "- this is not a supported branch.",
            )
        if sys.version_info < (3, 10):
            logger.typewriter_log(
                "WARNING: ",
                Fore.RED,
                "You are running on an older version of Python. "
                "Some people have observed problems with certain "
                "parts of Auto-GPT with this version. "
                "Please consider upgrading to Python 3.10 or higher.",
            )

    if install_plugin_deps:
        install_plugin_dependencies()

    # TODO: have this directory live outside the repository (e.g. in a user's
    #   home directory) and have it come in as a command line argument or part of
    #   the env file.
    if workspace_directory is None:
        workspace_directory = Path(__file__).parent / "auto_gpt_workspace"
    else:
        workspace_directory = Path(workspace_directory)
    # TODO: pass in the ai_settings file and the env file and have them cloned into
    #   the workspace directory so we can bind them to the agent.
    workspace_directory = Workspace.make_workspace(workspace_directory)
    cfg.workspace_path = str(workspace_directory)

    # HACK: doing this here to collect some globals that depend on the workspace.
    file_logger_path = workspace_directory / "file_logger.txt"
    if not file_logger_path.exists():
        with file_logger_path.open(mode="w", encoding="utf-8") as f:
            f.write("File Operation Logger ")

    cfg.file_logger_path = str(file_logger_path)

    cfg.set_plugins(scan_plugins(cfg, cfg.debug_mode))
    # Create a CommandRegistry instance and scan default folder
    command_registry = CommandRegistry()

    logger.debug(
        f"The following command categories are disabled: {cfg.disabled_command_categories}"
    )
    enabled_command_categories = [
        x for x in COMMAND_CATEGORIES if x not in cfg.disabled_command_categories
    ]

    logger.debug(
        f"The following command categories are enabled: {enabled_command_categories}"
    )

    for command_category in enabled_command_categories:
        command_registry.import_commands(command_category)

    ai_name = ""
    ai_config = construct_main_ai_config()
    ai_config.command_registry = command_registry
    if ai_config.ai_name:
        ai_name = ai_config.ai_name
    # print(prompt)
    # Initialize variables
    next_action_count = 0

    # add chat plugins capable of report to logger
    if cfg.chat_messages_enabled:
        for plugin in cfg.plugins:
            if hasattr(plugin, "can_handle_report") and plugin.can_handle_report():
                logger.info(f"Loaded plugin into logger: {plugin.__class__.__name__}")
                logger.chat_plugins.append(plugin)

    # Initialize memory and make sure it is empty.
    # this is particularly important for indexing and referencing pinecone memory
    memory = get_memory(cfg, init=True)
    logger.typewriter_log(
        "Using memory of type:", Fore.GREEN, f"{memory.__class__.__name__}"
    )
    logger.typewriter_log("Using Browser:", Fore.GREEN, cfg.selenium_web_browser)
    system_prompt = ai_config.construct_full_prompt()
    if cfg.debug_mode:
        logger.typewriter_log("Prompt:", Fore.GREEN, system_prompt)

    agent = Agent(
        ai_name=ai_name,
        memory=memory,
        next_action_count=next_action_count,
        command_registry=command_registry,
        config=ai_config,
        system_prompt=system_prompt,
        triggering_prompt=DEFAULT_TRIGGERING_PROMPT,
        workspace_directory=workspace_directory,
    )
    agent.start_interaction_loop()
