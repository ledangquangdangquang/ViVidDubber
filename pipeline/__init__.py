import threading

# Loading a model touches process-wide torch state (transformers' from_pretrained builds modules on the meta
# device and swaps the default dtype), so a model built in another thread meanwhile ends up with empty meta
# tensors. Hold this around every model load; inference may overlap freely.
MODEL_LOAD_LOCK = threading.Lock()
