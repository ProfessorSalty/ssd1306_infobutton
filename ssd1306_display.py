import subprocess
import math
import asyncio
import time

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from RPi import GPIO


def round_down(n, decimals=0):
    multiplier = 10 ** decimals
    return math.floor(n * multiplier) / multiplier


def get_shell_output(cmd: str):
    return subprocess.check_output(cmd, shell=True)


class InfoButton:
    def __init__(self, info_btn_pin=20, display_duration=5, hold_time=1, time_to_restart=3, time_to_shutdown=3,
                 time_to_cancel=3):
        serial = i2c(port=1, address=0x3c)
        self.device = ssd1306(serial, height=32, rotate=2)

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
                    held_time = round(time.time() - self.hold_start_time) + self.hold_time
                    self._on_hold(held_time)

            elif GPIO.input(self.pin) == 1 and self.pressed and not self.held:
                self.pressed = False
                self._on_short_release()
            elif GPIO.input(self.pin) == 1 and self.held:
                self.pressed = False
                self.held = False
                held_time = round(time.time() - self.hold_start_time) + self.hold_time
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

    @property()
    def cpu(self):
        return get_shell_output("top -bn1 | grep load | awk '{printf \"CPU: %3d%%\", $(NF-2)*100/4}'")

    @property()
    def memory(self):
        return get_shell_output("free -m | awk 'NR==2{printf \"MEM: %3d%%\", $3*100/$2 }'")

    @property()
    def hostname(self):
        return get_shell_output("hostname")

    @property()
    def ip_address(self):
        return get_shell_output("hostname -I | cut -d\' \' -f1")

    @property()
    def uptime(self):
        return get_shell_output("uptime -p")

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
            self._display_msg(middle_row="Release to restart" + dots)
        else:
            self._display_msg(middle_row=dots)

    def _on_press(self):
        self.hold_display = False
        self.release_display = False
        self.press_display = True

    def _on_short_release(self):
        self._display_msg(top_row=self.hostname, middle_row=self.ip_address,
                          bottom_row="CPU: %s | MEM: %S".format(self.cpu, self.memory))

    def _on_long_release(self, held_time):
        self.hold_display = False
        self.release_display = True
        self.press_display = False
        if held_time >= self.time_to_cancel:
            self._display_msg(middle_row="Cancelling shutdown...")
        elif held_time >= self.time_to_shutdown:
            self._display_msg(middle_row="Shutting down...")
        elif held_time >= self.time_to_restart:
            self._display_msg(middle_row="Restarting...")
        else:
            self._display_msg(top_row=self.hostname, middle_row=self.ip_address,
                              bottom_row="CPU: %s | MEM: %S".format(self.cpu, self.memory))
        self._set_delay(self.display_duration)

    def _display_msg(self, top_row: str = '', middle_row: str = '', bottom_row: str = ''):
        if self.display_task is not None:
            self.display_task.cancel()
        self._reset_tasks()
        with canvas(self.device) as draw:
            draw.text((0, 0), top_row, fill="white")
            draw.text((0, 12), middle_row, fill="white")
            draw.text((0, 24), bottom_row, fill="white")

    def _clear_screen(self):
        with canvas(self.device) as draw:
            draw.rectangle(self.device.bounding_box, fill="black")

    def _reset_timer(self):
        self.display_timer = 0

    def _set_delay(self, display_duration: int):
        self.pending_task = asyncio.create_task(asyncio.sleep(display_duration))

    def _reset(self):
        self._clear_screen()
        self._reset_tasks()
        self.hold_display = False
        self.release_display = False
        self.press_display = False
        self.presses = 0


def main():
    if __name__ == '__main__':
        InfoButton()
