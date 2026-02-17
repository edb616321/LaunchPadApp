"""Quick A/B audio test - run outside CCL. Tests 4 configs for 6 seconds each."""
import os, sys, time
os.environ["PATH"] = r"C:\Users\edb616321\AppData\Local\Programs\mpv.net" + os.pathsep + os.environ["PATH"]
import mpv

FILE = r"D:\For_Review\1 PM.mp3"

configs = {
    "1-WASAPI-bare": dict(vo='null', ao='wasapi'),
    "2-WASAPI-current": dict(vo='null', ao='wasapi', audio_buffer=1.0, audio_stream_silence='yes',
                              audio_samplerate=48000, audio_format='float', video_sync='audio'),
    "3-WASAPI-no-resample": dict(vo='null', ao='wasapi', audio_buffer=1.0, audio_stream_silence='yes'),
    "4-SDL": dict(vo='null', ao='sdl', audio_buffer=1.0),
}

pick = sys.argv[1] if len(sys.argv) > 1 else None
if not pick:
    print("Usage: python audio_test.py <1|2|3|4|all>")
    for k, v in configs.items():
        print(f"  {k}: {v}")
    sys.exit(0)

to_test = configs if pick == "all" else {k: v for k, v in configs.items() if k.startswith(pick)}

for name, opts in to_test.items():
    print(f"\n>>> {name}: {opts}")
    print("    Playing 6 seconds... LISTEN carefully.")
    p = mpv.MPV(**opts)
    p.play(FILE)
    try:
        p.wait_until_playing()
    except:
        time.sleep(1)
    time.sleep(6)
    p.stop()
    p.terminate()
    print("    Done.")
    if pick == "all":
        time.sleep(1)
