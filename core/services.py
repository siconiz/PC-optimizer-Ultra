"""Windows services that are safe to pause while a game runs; they are started again when it closes.
Nothing is disabled permanently, and Xbox services are never touched (Game Pass games need them)."""
import win32service, win32serviceutil

SERVICES = {  # name: (title, why it helps / what pauses)
    "WSearch": ("Windows Search indexing", "Stops file indexing from using the disk during games. Search still works "
                "with the existing index."),
    "DiagTrack": ("Telemetry (Connected User Experiences)", "Stops diagnostic data uploads during games."),
    "Spooler": ("Print Spooler", "Printing is unavailable while the game runs."),
    "MapsBroker": ("Downloaded Maps Manager", "Only used by the Maps app."),
    "lfsvc": ("Geolocation", "Apps cannot get your location while the game runs."),
    "Fax": ("Fax", "Rarely used."),
}

def _running(name):
    try:
        return win32serviceutil.QueryServiceStatus(name)[1] == win32service.SERVICE_RUNNING
    except Exception:
        return False

def pause(names):
    """Stops the chosen services that are running; returns the ones it stopped (to start them again later)."""
    stopped = []
    for n in names:
        if n in SERVICES and _running(n):
            try:
                win32serviceutil.StopService(n)
                stopped.append(n)
            except Exception:
                pass
    return stopped

def resume(names):
    for n in names:
        try:
            win32serviceutil.StartService(n)
        except Exception:
            pass
