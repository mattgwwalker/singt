import math
import numpy
import operator
from enum import Enum

# TODO: Tone would be better re-written so that it accepted commands
# (play, stop, fade-out-over-x-seconds) and stored those commands in
# internal state.  It would have another method, say, execute() which
# copied the appropriate data into the outdata.  The advantage of this
# approach would be fade-outs over periods longer than the frame size,
# and stopping that finished on a zero-crossing, which would stop
# clicks.

class Tone:
    class State(Enum):
        INACTIVE = 0
        PLAYING = 1
        FADING_IN = 2
        FADING_OUT = 3
        STOPPING = 4
        CLICKING = 5
                
    
    def __init__(self, freq, samples_per_second=48000,
                 channels=2, max_level=1, duration=1):
        """Freq in Hz, duration in seconds.  Will extend the duration so that
        a whole number of wavelengths are formed."""

        self._samples_per_second = samples_per_second
        self._freq = freq
        self._state = Tone.State.INACTIVE
        
        # Extend the duration so that the PCM finishes on a
        # zero-crossing.
        duration_wavelength = 1 / freq
        num_wavlengths = math.ceil(duration / duration_wavelength)
        duration = num_wavlengths * duration_wavelength
        
        t = numpy.linspace(
            0,
            duration,
            int(duration * samples_per_second),
            False
        )

        pcm = numpy.sin(freq * t * 2 * numpy.pi)

        if channels == 2:
            two_channels = [[x,x] for x in pcm]
            self._pcm = numpy.array(two_channels, dtype=numpy.float32)
        else:
            self._pcm = pcm

        # Noramlise
        self._pcm *= max_level

        self._pos = 0

    @property
    def inactive(self):
        return self._state == Tone.State.INACTIVE

        
    def reset(self):
        """Resets the position index to zero."""
        self._pos = 0
        self._state = Tone.State.INACTIVE

        
    def play(self):
        if self._state == Tone.State.INACTIVE:
            self._state = Tone.State.PLAYING
            return True
        else:
            return False

        
    def stop(self):
        self._state = Tone.State.STOPPING


    def _create_fade(self, from_, to_, duration):
        # Produce a linear fadeout multiplier
        samples = int(self._samples_per_second * duration)
        self.fade = numpy.linspace(from_, to_, samples)
        
        
    def fadein(self, duration):
        self._state = Tone.State.FADING_IN
        self._fadein_duration = duration
        self._create_fade(0, 1, duration)
        self._fade_pos=0

        
        
    def fadeout(self, duration):
        self._state = State.FADING_OUT
        self._fadeout_duration = duration
        self._create_fade(1, 0, duration)
        self._fade_pos=0

        
    def click(self, duration):
        self._state = State.CLICKING
        self._click_duration = duration


    def _fill(self, outdata, op=None):
        """Op needs to be an in-place operator (see
        https://docs.python.org/3/library/operator.html).  If op is
        None, outdata will be overwritten.
        """
        # Ensure the number of channels is the same
        assert outdata.shape[1] == self._pcm.shape[1]

        # Extract number of samples in outdata
        samples = outdata.shape[0]

        if self._pos+samples <= len(self._pcm):
            # Copy tone in one hit
            data = self._pcm[self._pos:self._pos+samples]
            if op is None:
                outdata[:] = data
            else:
                op(outdata, data)
            self._pos += samples
        else:
            # Need to loop back to the beginning of the tone
            remaining = len(self._pcm)-self._pos
            head = self._pcm[self._pos:len(self._pcm)]
            tail = self._pcm[:samples-remaining]
            if op is None:
                outdata[:remaining] = head
                outdata[remaining:] = tail
            else:
                op(outdata[:remaining], head)
                op(outdata[remaining:], tail)

            self._pos = samples-remaining

            
    def output(self, outdata, op = None):
        """Op needs to be an in-place operator (see
        https://docs.python.org/3/library/operator.html).  If op is
        None, outdata will be overwritten.
        """
        # Ensure the number of channels is the same
        assert outdata.shape[1] == self._pcm.shape[1]
        channels = outdata.shape[1]

        # Extract number of samples in outdata
        samples = outdata.shape[0]

        if self._state == Tone.State.PLAYING:
            self._fill(outdata, op)

        elif self._state == Tone.State.FADING_IN:
            # Adjust multiplier if two channels are needed
            channels = outdata.shape[1]
            if channels == 2:
                fade = numpy.array([[x,x] for x in self.fade])
            elif channels == 1:
                fade = self.fade
            else:
                raise Exception("Unsupported number of output channels")

            # Get the active section of the fade
            fade_length = len(fade) - self._fade_pos
            if fade_length > samples:
                # We can only output a portion of the fade during this
                # call.
                fade_length = samples

            # Apply the fade
            temp = fade[self._fade_pos:self._fade_pos+fade_length]
            self._fill(fade_length, temp, op=operator.imul)

            # Update the position in the fade
            self._fade_pos += fade_length

            # If we've come to the end of the fade, move to "playing".
            if self._fade_pos == len(fade):
                self.state = State.PLAYING

                
        if self._state == Tone.State.STOPPING:
            # Calculate the location of the end of the wavelength
            duration_wavelength = 1 / self._freq
            samples_per_wavelength = int(
                self._samples_per_second * duration_wavelength
            )
            print("samples_per_wavelength:",samples_per_wavelength)
            end_wavelength = (
                math.ceil(self._pos / samples_per_wavelength)
                * samples_per_wavelength
            )
            print("end_wavelength:", end_wavelength)
            print("pos:", self._pos)
            samples_remaining = end_wavelength - self._pos
            print("samples_remaining:", samples_remaining)
            if samples_remaining > samples:
                # We can't stop in the current frame, so just fill as
                # normal
                self._fill(outdata, op)
            else:
                # We can stop in the current frame.
                # Fill up to the stop point and then fill with zeros
                print("Stopping this frame!")
                self._fill(outdata[:samples_remaining], op)
                outdata[samples_remaining:] = numpy.zeros(
                    (samples - samples_remaining,channels),
                    numpy.float32
                )
                self._state = Tone.State.INACTIVE
                
            self._fill(outdata, op)

        


    # def _fade(self, samples, outdata, op, from_, to_):
    #     # Produce a linear fadeout multiplier
    #     faded = numpy.linspace(from_, to_, samples)

    #     # Adjust multiplier if two channels are needed
    #     if outdata.shape[1] == 2:
    #         faded = numpy.array([[x,x] for x in faded])

    #     # Get the samples as if they were being played, multiplying
    #     # them by the fadeout
    #     self.play(samples, faded, op=operator.imul)

    #     # Output the result
    #     if op is None:
    #         outdata[:] = faded
    #     else:
    #         op(outdata, faded)

            
    # def fadein(self, samples, outdata, op=None):
    #     self._fade(samples, outdata, op,
    #                from_=0, to_=1)

        
    # def fadeout(self, samples, outdata, op=None):
    #     self._fade(samples, outdata, op,
    #                from_=1, to_=0)
    #     # Reset the position index
    #     self.reset()


if __name__ == "__main__":
    import sounddevice as sd
    import threading
    import queue
    import wave

    samples_per_second = 48000

    class ProcessState(Enum):
        RESET = 0
        FADEIN = 10
        PLAY = 20
        PLAYING = 25
        FADEOUT = 30
        FADEIN2 = 40
        STOP = 50
        STOPPING = 55
        
    class Variables:
        def __init__(self):
            self.process_state = ProcessState.RESET
            
            self.frequency = 375 # Hz
            self.tone = Tone(self.frequency, max_level=0.5)

    # Create an instance of the class holding variables to be sotred
    # between calls of the callback
    v = Variables()
            
    # Threading event on which to wait
    event = threading.Event()

    # Queue to store output data for writing later
    q = queue.Queue()

    def callback(outdata, samples, time, status):
        global v
        
        if status:
            print(status)

        # Transitions
        # ===========

        if v.process_state == ProcessState.RESET:
            v.process_state = ProcessState.PLAY

        elif v.process_state == ProcessState.FADEIN:
            pass

        elif v.process_state == ProcessState.PLAY: 
            v.process_state = ProcessState.PLAYING
            v.state_started = time.currentTime

        elif v.process_state == ProcessState.PLAYING:
            duration = time.currentTime - v.state_started
            if duration > 2:
                v.process_state = ProcessState.STOP

        elif v.process_state == ProcessState.STOP:
            v.process_state = ProcessState.STOPPING
            
        elif v.process_state == ProcessState.STOPPING:
            if v.tone.inactive:
                raise sd.CallbackStop

        # Actions
        # =======

        if v.process_state == ProcessState.RESET:
            # Actively fill the output buffer to avoid artefacts.
            outdata.fill(0)

        elif v.process_state == ProcessState.FADEIN:
            # Actively fill the output buffer to avoid artefacts.
            outdata.fill(0)

            fadein_duration = 0.1 # seconds
            v.tone.fadein(fadein_duration)
            v.tone.output(outdata)
            
        elif v.process_state == ProcessState.PLAY:
            print("play")
            v.tone.play()
            v.tone.output(outdata)
            
        elif v.process_state == ProcessState.PLAYING:
            print("playing")
            v.tone.output(outdata)

        elif v.process_state == ProcessState.STOP:
            print("stop")
            v.tone.stop()
            v.tone.output(outdata)

        elif v.process_state == ProcessState.STOPPING:
            print("stopping")
            v.tone.output(outdata)

            
        # Store output
        # ============
        q.put(outdata.copy())

            
    # Open an output stream
    stream = sd.OutputStream(
        samplerate=samples_per_second,
        dtype=numpy.float32,
        callback=callback,
        finished_callback=event.set)

    with stream:
        event.wait()

        
    # Save output as wave file
    print("Writing wave file")
    wave_file = wave.open("out.wav", "wb")
    wave_file.setnchannels(2) #FIXME
    wave_file.setsampwidth(2)
    wave_file.setframerate(samples_per_second)
    while True:
        try:
            data = q.get_nowait()
        except:
            break
        data = data * (2**15-1)
        data = data.astype(numpy.int16)
        wave_file.writeframes(data)
    wave_file.close()

        
    print("Finished.")
    
