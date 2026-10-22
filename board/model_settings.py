"""Identity of the local GGUF service, selected by its environment file."""
import os

MODEL_PATH = os.environ.get('MODEL_PATH', '/opt/orangepi-rpg-aichat/models')
MODEL_ID = os.environ.get('MODEL_ID', 'local-gguf')
MODEL_LABEL = os.environ.get('MODEL_LABEL', 'Local GGUF')
MODEL_PRECISION = os.environ.get('MODEL_PRECISION', 'Q4_K_M')
MODEL_BACKEND = 'gguf'
BACKEND_LABEL = 'llama.cpp / ARM CPU'
THINKING_SUPPORTED = os.environ.get('MODEL_THINKING', '0') == '1'
CONTEXT_LENGTH = int(os.environ.get('MODEL_CONTEXT', '4096'))
if not 512 <= CONTEXT_LENGTH <= 4096:
    raise ValueError('The verified context range is 512..4096')
