# Using PIO for PWM to pulse LED brightness
#
# Refer: https://github.com/raspberrypi/pico-micropython-examples/tree/master/pio/pio_pwm.py
# Refer: https://hackspace.raspberrypi.org/articles/flashing-lights-with-micropython-and-programmable-i-o-part-2
from machine import Pin, Timer
from rp2 import PIO, StateMachine, asm_pio
from time import sleep

@asm_pio(sideset_init=PIO.OUT_LOW)
def pwm_prog():
    '''
    PWM PIO function
    
    Input Shift Reg (ISR) holds the Countdown reset value.
    Y = The countdown value.
    X = Point in countdown to set pin HIGH.

    ISR needs to be primed prior to starting the SM.
    Putting a value into the TX FIFO, sets X (the cycle time control.)
    
    Flow:
        Load X from TX FIFO, if a value is available. pin=LOW.
        Reload Y from ISR. (ISR needs to be pre-loaded before starting the PIO SM.)
        Loop
        When Y == X then pin=HIGH
        Decrement Y and keep looping until Y=0
        Goto start (when Y=0)#
        
    Uses sideset pins. I.e. setting pins as a concurrent side effect of executing an instruction.
    Sideset pins are specified with sideset_base rather than set_base.
    '''
    # "pull(noblock).side(0)" - Takes data from TX FIFO and places in Output Shift Reg (OSR).
    #    "noblock" - Doesn't wait. If no value available just continue.
    #    ".side(0)" - But still sets side pin (LED=off)
    pull(noblock)   .side(0)   # Read new X value if available. TX FIFO -> OSR. Set pin=LOW.
    mov(x, osr)                # OSR -> X
    mov(y, isr)                # ISR -> Y. ISR pre-loaded with countdown start value, before SM started
    label("pwmloop")
    jmp(x_not_y, "skip")       # Time to set pin=HIGH?
    nop()          .side(1)    # Yes, then set pin=HIGH
    label("skip")              # No, then keep counting down
    jmp(y_dec, "pwmloop")      # Dec Y, Jump if Y!=0
    # If Y=0 loop back to start

class PIOPWM:
    '''
    Class to manage the PWM PIO state machine and set the duty cycle
    '''

    def __init__(self, sm_id, pin, max_count, count_freq):
        self._sm = StateMachine(sm_id, pwm_prog, freq=2*count_freq, sideset_base=Pin(pin))
        # pre-load ISR with loop count
        self._sm.put(max_count)
        self._sm.exec("pull()")
        self._sm.exec("mov(isr, osr)")
        self._max_count = max_count
        self._sm.active(1)

    def set(self, value):
        # Min value = -1. (never turn on)
        value = max(value, -1)
        value = min(value, self._max_count)
        self._sm.put(value)

def tick(timer):
    '''
    Timer callback to run through a single LED fade in & fade out cycle
    '''
    global pwm
    # Fade in
    for i in range(256):
        pwm.set(i**2)
    # Fade out
    for i in range(256, -1, -1):
        pwm.set(i**2)

pwm = PIOPWM(0, 25, max_count=(1 << 16) - 1, count_freq=10_000_000)

# 4sec period. Need to allow enough time to complete fading cycle.
Timer().init(freq=0.25, mode=Timer.PERIODIC, callback=tick)