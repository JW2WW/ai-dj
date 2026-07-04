"""Windows service wrapper for AI DJ (optional).

Install: python windows_service.py install
Start:   python windows_service.py start
Stop:    python windows_service.py stop
Remove:  python windows_service.py remove

Requires: pip install pywin32
"""
import sys
import os
from pathlib import Path

try:
    import servicemanager
    import win32serviceutil
    import win32service
    import win32event
except ImportError:
    print("Error: pywin32 not installed. Run: pip install pywin32")
    sys.exit(1)

from playback_controller import PlaybackController


class AIdjService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AIdjRadio"
    _svc_display_name_ = "AI DJ Radio Station"
    _svc_description_ = "Self-hosted radio station with AI commentary, news, and markets"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

        self.music_dir = Path(r"C:\Users\AI\Desktop\mp3s")
        self.db_path = Path(__file__).parent / "data" / "ai_dj.db"
        self.tts_cache_dir = Path(__file__).parent / "data" / "tts_cache"
        self.controller = None

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )

        self.controller = PlaybackController(
            self.music_dir, self.db_path, self.tts_cache_dir
        )
        self.controller.start()

        # Keep service running until stop event is set
        while True:
            rc = win32event.WaitForSingleObject(self.stop_event, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                break

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.controller:
            self.controller.stop()
        win32event.SetEvent(self.stop_event)
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)


def main():
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(AIdjService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(AIdjService)


if __name__ == "__main__":
    main()
