from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from RPi import GPIO
import asyncio
import time 

def round_down(n, decimals=0):
    multiplier = 10 ** decimals
    return math.floor(n * multiplier) / multiplier

class InfoButton:
    def __init__(self, info_btn_pin = 20, display_duration = 5, hold_time = 1):
        serial = i2c(port=1, address=0x3c)
        self.device = ssd1306(serial, height=32, rotate=2)
        
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(info_btn_pin, GPIO.IN)
        
        self.wait_timer = None
        self.display_duration = display_duration
        self.pin = info_btn_pin
        self.pressed = False
        self.held = False
        self.press_display = False
        self.hold_display = False
        self.release_display = False
        self.hold_start_time = 0
        self.press_time = 0
        self.hold_time = hold_time
        self.display_task = None
        self.pending_task = None
        self.presses = 0
        
        asyncio.run(self._run())
        
    async def _run(self):
        await asyncio.gather(self._monitor_input(), self._monitor_display())
        
    async def _monitor_input(self):
        while True:
            if GPIO.input(self.pin) == 0:
                if self.pressed == False:
                    self.pressed = True
                    self.on_press()
                    self.press_time = time.time()
                elif self.held == False and time.time() - self.press_time > self.hold_time:
                    self.held = True
                    self.hold_start_time = self.press_time
                elif self.held == True:
                    held_time = round(time.time() - self.hold_start_time) + self.hold_time
                    self.on_hold(held_time)
                
            elif GPIO.input(self.pin) == 1 and self.pressed == True and self.held == False:
                self.pressed = False
                self.on_short_release()
            elif GPIO.input(self.pin) == 1 and self.held == True:
                self.pressed = False
                self.held = False
                held_time = round(time.time() - self.hold_start_time) + self.hold_time 
                self.on_long_release(held_time)
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
                    self.reset()
            await asyncio.sleep(0.001)
        
    def _update_task(self):
        if (self.display_task is None or self.display_task.cancelled) and self.pending_task is not None:
            self.display_task = self.pending_task
            self.pending_task = None
    
    def reset_tasks(self):
        self.display_task = None
        self.pending_task = None
                
    def on_hold(self, held_time):
        self.hold_display = True
        self.release_display = False
        self.press_display = False
        self.presses = 0
        self.set_display("Holding for {}s".format(held_time))
    
    def on_press(self):
        self.hold_display = False
        self.release_display = False
        self.press_display = True
        
        
    def on_short_release(self):
        self.set_display_delayed("Pressed {} times".format(self.presses), self.display_duration)
        if self.press_display:
             self.presses = (self.presses + 1) % 3
        
        
    def on_long_release(self, held_time):
        self.hold_display = False
        self.release_display = True
        self.press_display = False
        self.set_display_delayed("Released after {}s".format(held_time), self.display_duration)
        
    def display_msg(self, msg: str):
        with canvas(self.device) as draw:
            draw.text((5,1), msg, fill="white")
            
    def clear_screen(self):
        with canvas(self.device) as draw:
            draw.rectangle(self.device.bounding_box, fill="black")
            
    def reset_timer(self):
        self.display_timer = 0
        
    def set_display(self, msg: str):
        if self.display_task is not None:
            self.display_task.cancel()
        self.reset_tasks()
        self.display_msg(msg)
        
    def set_display_delayed(self, msg: str, display_duration):        
        if self.display_task is not None:
            self.display_task.cancel()
        self.display_msg(msg)
        self.pending_task = asyncio.create_task(asyncio.sleep(display_duration))
           
    def reset(self):
        self.clear_screen()
        self.reset_tasks()
        self.hold_display = False
        self.release_display = False
        self.press_display = False
        self.presses = 0
        
btn = InfoButton()


        
