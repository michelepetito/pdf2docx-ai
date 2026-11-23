"""MuPDF must never run concurrently in threads inside the same process."""
import threading

PDF_LOCK=threading.RLock()
