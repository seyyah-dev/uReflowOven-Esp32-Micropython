import machine
import ujson
import uos

import lvgl as lv
import lvesp32

from ili9341 import ili9341
from xpt2046 import xpt2046


machine.freq(240000000)

with open('config.json', 'r') as f:
    config = ujson.load(f)

TOUCH_CALI_FILE = config.get('touch_cali_file')
TEMP_HAS_CALIBRATED = config.get('has_calibrated')

tft_setup = config.get('tft_pins')
TFT_MISO = tft_setup.get('miso')
TFT_MOSI = tft_setup.get('mosi')
TFT_SCK = tft_setup.get('sck')
TFT_CS = tft_setup.get('cs')
TFT_DC = tft_setup.get('dc')
TFT_RST = tft_setup.get('rst')
TFT_ACC = tft_setup.get('acc')
TFT_LED = tft_setup.get('led')
TFT_ACC_ACTIVE_LOW = tft_setup.get('acc_active_low')
TFT_LED_ACTIVE_LOW = tft_setup.get('led_active_low')
TFT_IS_PORTRAIT = tft_setup.get('is_portrait')

max31855_setup = config.get('max31855_pins')
TEMP_HWSPI = max31855_setup.get('hwspi')
TEMP_CS = max31855_setup.get('cs')
TEMP_SCK = max31855_setup.get('sck')
TEMP_MISO = max31855_setup.get('miso')
TEMP_OFFSET = config.get('temp_offset')

OVEN_PIN = config.get('oven_pin')

BUZZER_PIN = config.get('buzzer_pin')

DEFAULT_ALLOY = config.get('default_alloy')

disp = ili9341(
    miso=TFT_MISO,
    mosi=TFT_MOSI,
    clk=TFT_SCK,
    cs=TFT_CS,
    dc=TFT_DC,
    rst=TFT_RST,
    power=TFT_ACC,
    backlight=TFT_LED,
    backlight_on=0 if TFT_LED_ACTIVE_LOW else 1,
    power_on=0 if TFT_ACC_ACTIVE_LOW else 1,
    width=240 if TFT_IS_PORTRAIT else 320,
    height=320 if TFT_IS_PORTRAIT else 240,
    rot=ili9341.PORTRAIT if TFT_IS_PORTRAIT else ili9341.LANDSCAPE
)

touch_setup = config.get('touch_pins')
TOUCH_CS = touch_setup.get('cs')
TOUCH_INTERRUPT = touch_setup.get('interrupt')

if TOUCH_CALI_FILE not in uos.listdir():
    touch = xpt2046(
        cs=TOUCH_CS,
        transpose=TFT_IS_PORTRAIT,
    )

    from touch_cali import TouchCali

    touch_cali = TouchCali(touch, config)
    touch_cali.start()

elif not TEMP_HAS_CALIBRATED:
    from temp_cali import TempCali

    temp_cali = TempCali(config)
    temp_cali.start()

else:
    with open(TOUCH_CALI_FILE, 'r') as f:
        param = ujson.load(f)
        touch_x0 = param['cal_x0']
        touch_x1 = param['cal_x1']
        touch_y0 = param['cal_y0']
        touch_y1 = param['cal_y1']

    touch = xpt2046(
        cs=TOUCH_CS,
        transpose=TFT_IS_PORTRAIT,
        cal_x0=touch_x0,
        cal_x1=touch_x1,
        cal_y0=touch_y0,
        cal_y1=touch_y1,
    )

    import gc
    import utime
    import _thread
    from buzzer import Buzzer
    from gui import GUI
    from load_profiles import LoadProfiles
    from max31855 import MAX31855
    from oven_control import OvenControl

    reflow_profiles = LoadProfiles(DEFAULT_ALLOY)

    gui = GUI(reflow_profiles, config)

    temp_sensor = MAX31855(hwspi=TEMP_HWSPI,
                           cs=TEMP_CS,
                           miso=TEMP_MISO,
                           sck=TEMP_SCK,
                           offset=TEMP_OFFSET)

    oven = machine.Pin(OVEN_PIN, machine.Pin.OUT, value=0)

    buzzer = Buzzer(BUZZER_PIN)

    timer = machine.Timer(0)

    def measure_temp():
        while True:
            try:
                temp_sensor.read_temp()
            except Exception:
                print('Error occurs when measuring temperature.')
            gui.temp_update(temp_sensor.get_temp())
            utime.sleep_ms(500)


    def buzzer_activate():
        while True:
            if buzzer.song:
                buzzer.play_song(buzzer.song)
                gc.collect()
            else:
                pass


    _thread.stack_size(7 * 1024)
    temp_th = _thread.start_new_thread(measure_temp, ())
    buzzer_th = _thread.start_new_thread(buzzer_activate, ())

    oven_control = OvenControl(oven, temp_sensor, reflow_profiles, gui, buzzer, timer, config)
