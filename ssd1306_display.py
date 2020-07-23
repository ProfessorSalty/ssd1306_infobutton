import asyncio
import os
import time
import re
from subprocess import Popen, PIPE, check_output

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont
from RPi import GPIO


class InfoButton:
    def __init__(self, info_btn_pin=20, display_duration=5, hold_time=1, time_to_restart=3, time_to_shutdown=3,
                 time_to_cancel=3, flip=False, font='./PressStart2P-Regular.ttf'):
        this_dir, this_filename = os.path.split(__file__)
        font_path = os.path.join(this_dir, font)

        serial = i2c(port=1, address=0x3c)
        rotation = 2 if flip else 0
        self.device = ssd1306(serial, height=32, rotate=rotation)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(info_btn_pin, GPIO.IN)

        self.display_duration = display_duration
        self.pin = info_btn_pin
        self.hold_time = hold_time
        self.time_to_restart = time_to_restart
        self.time_to_shutdown = time_to_shutdown + time_to_restart
        self.time_to_cancel = time_to_cancel + time_to_shutdown + time_to_restart

        self.wait_timer = None
        self.pressed = False
        self.held = False
        self.press_display = False
        self.hold_display = False
        self.release_display = False
        self.display_task = None
        self.pending_task = None
        self.hold_start_time = 0
        self.press_time = 0
        self.presses = 0
        self.font = ImageFont.truetype(font_path, 6)

        asyncio.run(self._run())

    async def _run(self):
        await asyncio.gather(self._monitor_input(), self._monitor_display())

    async def _monitor_input(self):
        while True:
            if GPIO.input(self.pin) == 0:
                if not self.pressed:
                    self.pressed = True
                    self._on_press()
                    self.press_time = time.time()
                elif not self.held and time.time() - self.press_time > self.hold_time:
                    self.held = True
                    self.hold_start_time = self.press_time
                elif self.held:
                    held_time = round(
                        time.time() - self.hold_start_time) + self.hold_time
                    self._on_hold(held_time)

            elif GPIO.input(self.pin) == 1 and self.pressed and not self.held:
                self.pressed = False
                self._on_short_release()
            elif GPIO.input(self.pin) == 1 and self.held:
                self.pressed = False
                self.held = False
                held_time = round(
                    time.time() - self.hold_start_time) + self.hold_time
                self._on_long_release(held_time)
            await asyncio.sleep(0.001)

    async def _monitor_display(self):
        while True:
            self._update_task()
            if self.display_task is not None:
                try:
                    await self.display_task
                except asyncio.CancelledError:
                    pass
                else:
                    self._reset()
            await asyncio.sleep(0.001)

    @property
    def cpu(self) -> float:
        top = Popen(["top", "-bn1"], stdout=PIPE)
        grep = check_output(["grep", "Cpu"], stdin=top.stdout).decode()
        try:
            cpu = float(
                re.search(r'Cpu\(s\):\s+\d+.\d+\sus,\s+(?P<cpu>\d+.\d+)', grep).group('cpu'))
        except AttributeError:
            cpu = 0
        return cpu

    @property
    def memory(self) -> float:
        free = check_output(["free", "-m"]).decode().split('\n')
        mem = free[1]
        try:
            total, used = re.search(r'Mem:\s+(\d+)\s+(\d+)', mem).groups()
            pmem = (float(used) / float(total)) * 100
        except AttributeError:
            pmem = 0
        return pmem

    @property
    def hostname(self) -> str:
        return check_output("hostname").decode()

    @property
    def ip_address(self) -> str:
        return check_output(["hostname", "-I"]).decode()

    @property
    def uptime(self) -> str:
        return check_output(["uptime", "-p"]).decode()

    def _update_task(self):
        if (self.display_task is None or self.display_task.cancelled) and self.pending_task is not None:
            self.display_task = self.pending_task
            self.pending_task = None

    def _reset_tasks(self):
        self.display_task = None
        self.pending_task = None

    def _on_hold(self, held_time):
        dots = ". " * (held_time % 3)
        self.hold_display = True
        self.release_display = False
        self.press_display = False
        self.presses = 0
        if held_time >= self.time_to_cancel:
            self._display_msg(middle_row="Release to cancel" + dots)
        elif held_time >= self.time_to_shutdown:
            self._display_msg(middle_row="Release to shutdown" + dots)
        elif held_time >= self.time_to_restart:
            self._display_msg(middle_row="Release to reboot" + dots)
        else:
            self._display_msg(middle_row=dots)

    def _on_press(self):
        self.hold_display = False
        self.release_display = False
        self.press_display = True

    def _display_main_msg(self):
        self._display_msg(top_row=self.hostname, middle_row=self.ip_address,
                          bottom_row="C {:6.2f}% | M {:6.2f}%".format(self.cpu, self.memory))

    def _on_short_release(self):
        self._display_main_msg()
        self._set_delay()

    def _on_long_release(self, held_time):
        self.hold_display = False
        self.release_display = True
        self.press_display = False
        if held_time >= self.time_to_cancel:
            self._display_msg(middle_row="Cancelling shutdown...")
        elif held_time >= self.time_to_shutdown:
            self._display_msg(middle_row="Shutting down...")
            self._shutdown()
        elif held_time >= self.time_to_restart:
            self._display_msg(middle_row="Rebooting...")
            self._reboot()
        else:
            self._display_main_msg()
        self._set_delay()

    def _display_msg(self, top_row: str = '', middle_row: str = '', bottom_row: str = ''):
        if self.display_task is not None:
            self.display_task.cancel()
        self._reset_tasks()
        with canvas(self.device) as draw:
            draw.text((0, 0), top_row, fill="white", font=self.font)
            draw.text((0, 12), middle_row, fill="white", font=self.font)
            draw.text((0, 24), bottom_row, fill="white", font=self.font)

    def _clear_screen(self):
        with canvas(self.device) as draw:
            draw.rectangle(self.device.bounding_box, fill="black")

    def _reset_timer(self):
        self.display_timer = 0

    def _set_delay(self):
        self.pending_task = asyncio.create_task(
            asyncio.sleep(self.display_duration))

    def _shutdown(self):
        check_output(["sudo", "shutdown", "now"])

    def _reboot(self):
        check_output(["sudo", "reboot", "now"])

    def _reset(self):
        self._clear_screen()
        self._reset_tasks()
        self.hold_display = False
        self.release_display = False
        self.press_display = False
        self.presses = 0
