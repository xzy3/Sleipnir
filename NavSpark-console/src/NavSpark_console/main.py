import asyncio
from enum import Enum

import serial
from serial.tools.list_ports import comports
import serial_asyncio
import attr
from toolz.itertoolz import nth

from prompt_toolkit.application import Application, get_app_or_none
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import (
    VSplit,
    HSplit,
    Window,
    Float,
    FloatContainer,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import LayoutDimension, D
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import (
    SearchToolbar,
    TextArea,
    Button,
    Dialog,
    Label,
    RadioList,
)

from NavSpark_console.protocol import NavSparkRawProtocol


class baud_settings(Enum):
    b115200 = 115200
    b57600 = 57600
    b8400 = 8400
    b9200 = 9200
    b600 = 600
    b800 = 800
    b400 = 400

    def __str__(self):
        return f"{self.value}"


class byte_size_settings(Enum):
    EIGHT_BITS = serial.EIGHTBITS
    FIVE_BITS = serial.FIVEBITS
    SIX_BITS = serial.SIXBITS
    SEVEN_BITS = serial.SEVENBITS

    def __str__(self):
        return f"{self.value}"


class parity_settings(Enum):
    none = serial.PARITY_NONE
    even = serial.PARITY_EVEN
    odd = serial.PARITY_ODD
    mark = serial.PARITY_MARK
    space = serial.PARITY_SPACE

    def __str__(self):
        return f"{self.value}"


class stopbits_settings(Enum):
    one = serial.STOPBITS_ONE
    one_point_five = serial.STOPBITS_ONE_POINT_FIVE
    two = serial.STOPBITS_TWO

    def __str__(self):
        return f"{self.value}"


@attr.s(auto_attribs=True)
class SelectComPortDialog:
    title: str = "Configure Serial Port"
    future: asyncio.Future = attr.ib(factory=asyncio.Future)
    port: str = None
    baud: int = 115200
    byte_size: int = 8
    parity: str = "None"
    stop_bits: str = "1"

    def __attrs_post_init__(self):
        ports = comports()
        ports_rl = RadioList([(p, p.name) for p in ports])
        baud_rl = RadioList([(b, str(b)) for b in baud_settings])
        byte_size_rl = RadioList([(b, str(b)) for b in byte_size_settings])
        parity_rl = RadioList([(p, str(p)) for p in parity_settings])
        stop_bits_rl = RadioList([(s, str(s)) for s in stopbits_settings])

        rl_container = HSplit(
            [
                Label("ports"),
                ports_rl,
                Label("baud"),
                baud_rl,
                Label("byte size"),
                byte_size_rl,
                Label("parity"),
                parity_rl,
                Label("stop bits"),
                stop_bits_rl,
            ]
        )

        def label_text():
            port = ports_rl.current_value
            baud = baud_rl.current_value
            byte_size = byte_size_rl.current_value
            parity = parity_rl.current_value
            stop_bits = stop_bits_rl.current_value
            return f"{port.name}, {baud} {byte_size}{parity}{stop_bits}"

        def accept():
            self.future.set_result(
                {
                    "port": ports_rl.current_value,
                    "baudrate": baud_rl.current_value,
                    "bytesize": byte_size_rl.current_value,
                    "parity": parity_rl.current_value,
                    "stopbits": stop_bits_rl.current_value,
                }
            )

        def cancel():
            self.future.set_result("cancel")

        ok_button = Button(text="OK", handler=accept)
        cancel_button = Button(text="Cancel", handler=cancel)

        self.dialog = Dialog(
            title=self.title,
            body=HSplit([Label(label_text), rl_container]),
            buttons=[ok_button, cancel_button],
            width=D(preferred=80),
            modal=True,
        )

    def __pt_container__(self):
        return self.dialog


async def console_app(loop):
    def get_statusbar_text():
        return [
            ("class:status", "Press "),
            ("class:status.key", "Ctrl-C"),
            ("class:status", " to exit, "),
            ("class:status.key", "/"),
            ("class:status", " to search"),
        ]

    search_field = SearchToolbar(
        text_if_not_searching=[("class:not-searching", "Press '/' to start searching.")]
    )

    text_area = TextArea(
        text="hi",
        read_only=True,
        scrollbar=True,
        line_numbers=True,
        search_field=search_field,
    )

    root_container = FloatContainer(
        content=HSplit(
            [
                Window(
                    content=FormattedTextControl(get_statusbar_text),
                    height=LayoutDimension.exact(1),
                    style="class:status",
                ),
                text_area,
                search_field,
            ]
        ),
        floats=[],
    )

    bindings = KeyBindings()

    def show_dialog(app, dialog):
        async def dlg():
            float_ = Float(content=dialog)
            root_container.floats.insert(0, float_)

            focus_before = app.layout.current_window
            app.layout.focus(dialog)
            result = await dialog.future
            app.layout.focus(focus_before)

            if float_ in root_container.floats:
                root_container.floats.remove(float_)
            return result

        asyncio.create_task(dlg())

    @bindings.add("c-c")
    def _(event):
        "Quit."
        event.app.exit()

    @bindings.add("c-o")
    def _(event):
        "open a port"
        v = show_dialog(event.app, SelectComPortDialog())

    style = Style.from_dict(
        {
            "status": "reverse",
            "status.position": "#aaaa00",
            "status.key": "#ffaa00",
            "not-searching": "#888888",
        }
    )

    application = Application(
        layout=Layout(root_container, focused_element=text_area),
        key_bindings=bindings,
        enable_page_navigation_bindings=True,
        mouse_support=True,
        style=style,
        full_screen=True,
    )

    result = await application.run_async(set_exception_handler=False)
    loop.stop()


def loop_exception_handler(loop, context):
    loop.default_exception_handler(context)
    print(context.get("exception"))

    app = get_app_or_none()
    if app:
        app.exit()

    tasks = [t for t in asyncio.all_tasks() if t is not acyncio.current_task()]
    for t in tasks:
        t.cancel()

    asyncio.run_coroutine_threadsafe(asyncio.wait_for(tasks, None), loop)
    loop.stop()


def main():
    loop = asyncio.get_event_loop()
    # loop.set_exception_handler(loop_exception_handler)

    # coro = serial_asyncio.create_serial_connection(loop, NavSparkRawProtocol, "loop://")
    # transport,protocol = loop.run_until_complete(coro)
    app = loop.run_until_complete(console_app(loop))

    loop.run_forever()
    loop.close()
