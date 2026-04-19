
import time


# main clean gpu cpu 

# ---------------------------------------------------------------------------
# Resource cleanup helper
# ---------------------------------------------------------------------------
def cleanup_resources():
    """Clear RAM/GPU caches before running tests."""
    import gc

    print("\n[CLEANUP] Freeing resources...")

    # Python garbage collection
    gc.collect()
    time.sleep(1)

    # Print resource status before starting
    pass



cleanup_resources()