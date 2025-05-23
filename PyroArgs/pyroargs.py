# PyroArgs/pyroargs.py
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from pyrogram import Client
from pyrogram.filters import Filter, command, all
from pyrogram.handlers import MessageHandler

from . import errors
from .parser import get_command_and_args, parse_command
from .types import Message
from .types.command import Command
from .types.commandRegistry import CommandRegistry
from .types.events import Events
from .utils import DataHolder

F = TypeVar('F', bound=Callable[..., Any])


class PyroArgs:
    def __init__(
            self,
            bot: Client,
            prefixes: Union[List[str], Tuple[str], str] = ['/'],
            log_file: str = None
    ) -> None:
        # Переменные класса
        self.bot: Client = bot
        self.prefixes: Union[List[str], Tuple[str], str] = prefixes
        self.events: Events = Events(log_file)
        self.registry: CommandRegistry = CommandRegistry()
        self.permission_checker_func: Callable[[
            Message, int], bool] = None

        # Сохраняем объекты для доступа в плагинах
        DataHolder.ClientObj = self.bot
        DataHolder.PyroArgsObj = self

        # Логи
        self.setup_logs = self.events.logger.setup_logs
        self.before_use_command_message = self.events.logger.before_use_command_message  # noqa
        self.after_use_command_message = self.events.logger.after_use_command_message  # noqa
        self.missing_argument_error_message = self.events.logger.missing_argument_error_message  # noqa
        self.argument_type_error_message = self.events.logger.argument_type_error_message  # noqa
        self.command_error_message = self.events.logger.command_error_message  # noqa
        self.permissions_error_message = self.events.logger.permissions_error_message  # noqa

    def command(
        self,
        name: str = None,
        description: str = None,
        usage: str = None,
        example: str = None,
        permissions_level: int = 0,
        aliases: List[str] = None,
        command_meta_data: Any = None,
        category: str = 'General',
        filters: Filter = None,
        group: int = 0
    ) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            # ** Параметры команды **
            command_name = name or func.__name__
            command_aliases = aliases or []
            __all_names__ = [command_name, *command_aliases]
            if self.bot.me.is_bot:
                all_names = __all_names__ + [f'{cmd}@{self.bot.me.username}' for cmd in __all_names__]
            else:
                all_names = __all_names__

            # ** Обработчик команды **
            async def handler(client: Client, message: Message) -> None:
                message.command_meta_data = command_meta_data

                # ** Парсинг команды **
                cmd_text = message.text or message.caption
                _, args = get_command_and_args(cmd_text, self.prefixes)

                # ** Проверка прав **
                if not await self.__has_permission(
                    command_name,
                    message,
                    permissions_level
                ):
                    return

                # ** Исключения **
                parsed_args = await self.__parse_arguments(func, args, message)
                if not parsed_args:
                    return  # noqa  Ошибка уже обрабатывается внутри __parse_arguments

                # ** Выполнение команды **
                await self.__execute_command(
                    func,
                    message,
                    command_name,
                    args,
                    parsed_args
                )

            # ** Регистрация команды **
            self.__register_command(
                handler,
                all_names,
                filters or all,
                group,
                command_name,
                description or func.__doc__,
                usage,
                example,
                permissions_level,
                aliases,
                command_meta_data,
                category
            )
            return func

        return decorator

    async def __has_permission(
            self,
            command_name: str,
            message: Message,
            permissions_level: int
    ) -> bool:
        if self.permission_checker_func and not await self.permission_checker_func(message, permissions_level):  # noqa
            error = errors.CommandPermissionError(
                command=command_name,
                message=message,
                permission_level=permissions_level
            )
            await self.events._trigger_command_permission_error(message, error)
            return False
        return True

    async def __parse_arguments(
            self,
            func: Callable,
            args: str,
            message: Message
    ) -> Optional[Tuple[List, Dict]]:
        try:
            result_args, result_kwargs = parse_command(func, args)
            return result_args, result_kwargs
        except SyntaxError as e:
            raise e
        except errors.MissingArgumentError as e:
            await self.events._trigger_missing_argument_error(message, e)
        except errors.ArgumentTypeError as e:
            await self.events._trigger_argument_type_error(message, e)
        except Exception as e:
            print(
                (
                    '\n'
                    '!!!!!!!!!      PYROARGS CRITICAL ERROR      !!!!!!!!!\n'
                    '!!                                                 !!\n'
                    '!!            PLEASE REPORT THIS ERROR:            !!\n'
                    '!!  https://github.com/vo0ov/PYPI-PyroArgs/issues  !!\n'
                    '!!                                                 !!\n'
                    '!!!!!!!!!      PYROARGS CRITICAL ERROR      !!!!!!!!!\n'
                    '\n'
                )
            )
            raise SystemError(e)
        return None

    async def __execute_command(
            self,
            func: Callable,
            message: Message,
            command_name: str,
            args: str,
            parsed_args: Tuple[List, Dict]
    ) -> None:
        result_args, result_kwargs = parsed_args
        try:
            await self.events._trigger_before_use_command(
                message=message,
                command=command_name,
                args=result_args,
                kwargs=result_kwargs
            )
            response = await func(message, *result_args, **result_kwargs)
            await self.events._trigger_after_use_command(
                message=message,
                command=command_name,
                args=result_args,
                kwargs=result_kwargs
            )
            return response
        except Exception as e:
            error = errors.CommandError(
                command=command_name,
                message=message,
                parsed_args=result_args,
                parsed_kwargs=result_kwargs,
                error_message=str(e),
                original_error=e
            )
            await self.events._trigger_command_error(message, error)
            raise e

    def __register_command(
            self,
            handler,
            all_names,
            filters,
            group,
            command_name,
            description,
            usage,
            example,
            permissions_level,
            aliases,
            command_meta_data,
            category
    ):
        cmd = Command(
            command_name,
            description,
            usage,
            example,
            permissions_level,
            aliases,
            command_meta_data
        )
        self.registry.add_command(cmd, category or 'Other')
        self.bot.add_handler(
            MessageHandler(
                handler,
                command(all_names, self.prefixes) & filters
            ),
            group
        )

    def permissions_checker(
            self,
            func: Callable[[Message, int], bool]
    ) -> Callable[[Message, int], bool]:
        self.permission_checker_func = func
        return func

# Hello, @Dogifnf! You are the first one to install this library. :3
