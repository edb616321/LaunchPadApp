"""
Audio Diagnostic - Tests MPV playback in different modes to isolate crackling cause.
Run this OUTSIDE of CCL to test.
"""
import os
import sys
import time
import threading

os.environ["PATH"] = r"C:\Users\edb616321\AppData\Local\Programs\mpv.net" + os.pathsep + os.environ["PATH"]
import mpv

TEST_FILE = r"D:\For_Review\Keep Going.mp3"

def test_standalone_wasapi():
    """Test 1: Pure MPV, no Tk, WASAPI shared mode"""
    print("\n=== TEST 1: Standalone MPV + WASAPI (shared) ===")
    print("Playing for 8 seconds... Listen for crackling.")
    p = mpv.MPV(
        vo='null',
        ao='wasapi',
        audio_buffer=0.5,
        volume=100,
        volume_max=150,
    )
    p.play(TEST_FILE)
    p.wait_until_playing()
    time.sleep(8)
    p.stop()
    p.terminate()
    input("Did it crackle? (y/n): ")

def test_standalone_wasapi_exclusive():
    """Test 2: Pure MPV, no Tk, WASAPI exclusive mode"""
    print("\n=== TEST 2: Standalone MPV + WASAPI (exclusive) ===")
    print("Playing for 8 seconds... Listen for crackling.")
    p = mpv.MPV(
        vo='null',
        ao='wasapi',
        audio_exclusive='yes',
        audio_buffer=0.5,
        volume=100,
        volume_max=150,
    )
    p.play(TEST_FILE)
    p.wait_until_playing()
    time.sleep(8)
    p.stop()
    p.terminate()
    input("Did it crackle? (y/n): ")

def test_standalone_sdl():
    """Test 3: Pure MPV, no Tk, SDL audio"""
    print("\n=== TEST 3: Standalone MPV + SDL audio ===")
    print("Playing for 8 seconds... Listen for crackling.")
    p = mpv.MPV(
        vo='null',
        ao='sdl',
        audio_buffer=0.5,
        volume=100,
        volume_max=150,
    )
    p.play(TEST_FILE)
    p.wait_until_playing()
    time.sleep(8)
    p.stop()
    p.terminate()
    input("Did it crackle? (y/n): ")

def test_embedded_tk_with_observers():
    """Test 4: MPV embedded in Tk WITH time-pos observer (the current CCL setup)"""
    import tkinter as tk
    print("\n=== TEST 4: Embedded in Tk + property observers (CURRENT CCL SETUP) ===")
    print("Playing for 10 seconds... This simulates what CCL does.")

    root = tk.Tk()
    root.geometry("400x200")
    root.title("Audio Diag - Test 4")

    frame = tk.Frame(root, bg='black', width=400, height=150)
    frame.pack(fill='both', expand=True)

    label = tk.Label(root, text="Starting...", font=("Segoe UI", 14))
    label.pack()

    frame.update_idletasks()
    wid = frame.winfo_id()

    update_count = [0]

    p = mpv.MPV(
        wid=str(int(wid)),
        hwdec='auto-safe',
        vo='gpu',
        ao='wasapi',
        audio_buffer=0.2,
        volume_max=150,
        gapless_audio='weak',
        audio_channels='stereo',
        demuxer_max_bytes=10*1024*1024,
        demuxer_readahead_secs=10,
        keep_open=True,
        idle=True,
        osd_level=0,
        input_default_bindings=False,
        input_vo_keyboard=False,
    )

    # This is what CCL does - observe time-pos and update UI on EVERY tick
    @p.property_observer('time-pos')
    def time_observer(_name, value):
        if value is not None:
            update_count[0] += 1
            try:
                root.after(0, lambda v=value: label.configure(
                    text=f"Time: {v:.1f}s | UI updates: {update_count[0]}"
                ))
            except:
                pass

    p.play(TEST_FILE)

    def close_after():
        time.sleep(10)
        try:
            p.stop()
            p.terminate()
            root.after(0, root.destroy)
        except:
            pass

    threading.Thread(target=close_after, daemon=True).start()
    root.mainloop()
    print(f"Total UI updates in 10s: {update_count[0]} ({update_count[0]/10:.0f}/sec)")
    input("Did it crackle? (y/n): ")

def test_embedded_tk_throttled():
    """Test 5: MPV embedded in Tk with THROTTLED updates (proposed fix)"""
    import tkinter as tk
    print("\n=== TEST 5: Embedded in Tk + THROTTLED observers (PROPOSED FIX) ===")
    print("Playing for 10 seconds... This uses a 250ms timer instead of per-frame observer.")

    root = tk.Tk()
    root.geometry("400x200")
    root.title("Audio Diag - Test 5")

    frame = tk.Frame(root, bg='black', width=400, height=150)
    frame.pack(fill='both', expand=True)

    label = tk.Label(root, text="Starting...", font=("Segoe UI", 14))
    label.pack()

    frame.update_idletasks()
    wid = frame.winfo_id()

    update_count = [0]

    p = mpv.MPV(
        wid=str(int(wid)),
        hwdec='auto-safe',
        vo='gpu',
        ao='wasapi',
        audio_buffer=0.5,
        volume_max=150,
        gapless_audio='weak',
        demuxer_max_bytes=50*1024*1024,
        demuxer_readahead_secs=30,
        keep_open=True,
        idle=True,
        osd_level=0,
        input_default_bindings=False,
        input_vo_keyboard=False,
    )

    # NO property observer for time-pos! Use periodic timer instead.
    def poll_time():
        try:
            pos = p.time_pos
            dur = p.duration
            if pos is not None:
                update_count[0] += 1
                label.configure(text=f"Time: {pos:.1f}s | Polls: {update_count[0]}")
        except:
            pass
        root.after(250, poll_time)  # 4 updates/sec instead of 60

    p.play(TEST_FILE)
    root.after(500, poll_time)

    def close_after():
        time.sleep(10)
        try:
            p.stop()
            p.terminate()
            root.after(0, root.destroy)
        except:
            pass

    threading.Thread(target=close_after, daemon=True).start()
    root.mainloop()
    print(f"Total UI updates in 10s: {update_count[0]} ({update_count[0]/10:.0f}/sec)")
    input("Did it crackle? (y/n): ")

def test_vo_null_audio_only():
    """Test 6: Embedded in Tk but vo=null for audio files (no GPU rendering)"""
    import tkinter as tk
    print("\n=== TEST 6: Tk window + vo=null (audio-only optimization) ===")
    print("Playing for 8 seconds... No video rendering overhead.")

    root = tk.Tk()
    root.geometry("400x200")
    root.title("Audio Diag - Test 6")

    label = tk.Label(root, text="Playing with vo=null...", font=("Segoe UI", 14))
    label.pack(expand=True)

    p = mpv.MPV(
        vo='null',
        ao='wasapi',
        audio_buffer=0.5,
        volume_max=150,
    )

    def poll_time():
        try:
            pos = p.time_pos
            if pos is not None:
                label.configure(text=f"Time: {pos:.1f}s (vo=null)")
        except:
            pass
        root.after(250, poll_time)

    p.play(TEST_FILE)
    root.after(500, poll_time)

    def close_after():
        time.sleep(8)
        try:
            p.stop()
            p.terminate()
            root.after(0, root.destroy)
        except:
            pass

    threading.Thread(target=close_after, daemon=True).start()
    root.mainloop()
    input("Did it crackle? (y/n): ")


if __name__ == "__main__":
    print("=" * 60)
    print("QUICKPLAYER AUDIO DIAGNOSTIC")
    print("=" * 60)
    print(f"Test file: {TEST_FILE}")
    print(f"File exists: {os.path.exists(TEST_FILE)}")

    if len(sys.argv) > 1:
        test_num = int(sys.argv[1])
        tests = {
            1: test_standalone_wasapi,
            2: test_standalone_wasapi_exclusive,
            3: test_standalone_sdl,
            4: test_embedded_tk_with_observers,
            5: test_embedded_tk_throttled,
            6: test_vo_null_audio_only,
        }
        if test_num in tests:
            tests[test_num]()
        else:
            print(f"Unknown test {test_num}. Use 1-6.")
    else:
        print("\nUsage: python audio_diag.py <test_number>")
        print("  1 = Standalone WASAPI (no Tk)")
        print("  2 = Standalone WASAPI exclusive (no Tk)")
        print("  3 = Standalone SDL audio (no Tk)")
        print("  4 = Embedded Tk + observers (CURRENT CCL - likely crackles)")
        print("  5 = Embedded Tk + THROTTLED timer (PROPOSED FIX)")
        print("  6 = Tk window + vo=null (audio-only, no GPU)")
        print("\nRun tests 1, then 4, then 5 to isolate the problem.")
        print("If 1 is clean but 4 crackles -> Tk embedding is the cause")
        print("If 1 also crackles -> MPV/driver issue")
